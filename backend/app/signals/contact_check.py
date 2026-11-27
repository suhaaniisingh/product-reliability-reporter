"""Checks on the contact details a store publishes (approved 2026-11-24).

What we can check for free and deterministically:
- **Email: can its domain receive mail?** A DNS lookup of the domain's mail
  servers (MX records). Catches made-up or misspelled domains.
- **Email: whose address is it?** The store's own domain, a free webmail service,
  or something else. Context only: many honest small shops use Gmail.
- **Phone: is it a possible number?** Google's libphonenumber rules (the
  `phonenumbers` package) give validity, country and line type, offline.

What we deliberately don't do: probing mail servers for a mailbox (unreliable,
and treated as spammer behaviour), paid carrier lookups, or contacting the store.
Even a "real" email can belong to a scammer, so this only filters out fake-looking
details. It doesn't prove trustworthiness.
"""

import asyncio
from dataclasses import dataclass
from typing import Protocol

import dns.asyncresolver
import dns.exception
import dns.resolver
import phonenumbers
from phonenumbers import Leniency, PhoneNumberMatcher, PhoneNumberType

from app.signals.domains import registrable_domain

FREE_WEBMAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.ca", "yahoo.co.uk", "outlook.com", "hotmail.com", "live.com",
    "msn.com", "icloud.com", "me.com", "aol.com", "proton.me", "protonmail.com", "gmx.com", "mail.com", "yandex.com",
    "qq.com", "163.com", "126.com", "zoho.com",
}
# Two-letter domains commonly used as generic names rather than for their country.
_GENERIC_CC = {"co", "io", "ai", "me", "tv", "cc", "ly", "gg", "so", "to", "fm", "am", "ws", "la"}
_LINE_TYPES = {
    PhoneNumberType.MOBILE: "mobile",
    PhoneNumberType.FIXED_LINE: "landline",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "landline or mobile",
    PhoneNumberType.TOLL_FREE: "toll-free",
    PhoneNumberType.VOIP: "internet phone (VoIP)",
}


class MailResolver(Protocol):
    async def receives_mail(self, domain: str) -> bool | None:
        """True = has mail servers, False = definitely can't receive mail, None = couldn't tell."""
        ...


class DnsMailResolver:
    async def receives_mail(self, domain: str) -> bool | None:
        try:
            answer = await dns.asyncresolver.Resolver().resolve(domain, "MX", lifetime=2.0)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return False  # the domain doesn't exist, or publishes no mail servers
        except (dns.exception.Timeout, dns.resolver.NoNameservers, dns.exception.DNSException):
            return None
        # A "null MX" (a single record pointing at ".") explicitly means "no mail here".
        return not all(str(r.exchange) == "." for r in answer)


@dataclass(frozen=True)
class EmailCheck:
    address: str
    found_on: str  # page path, e.g. "/pages/contact"
    owner: str  # "store" | "free_webmail" | "other"
    receives_mail: bool | None


@dataclass(frozen=True)
class PhoneCheck:
    number: str  # as written on the page
    found_on: str
    valid: bool
    country: str | None  # ISO code, e.g. "CA"
    line_type: str | None


def default_region(store_domain: str) -> str:
    """Region for numbers written without a country code: from a country domain
    (.ca -> CA, .co.uk -> GB), otherwise US (+1 numbers are the most common)."""
    last = store_domain.rsplit(".", 1)[-1].lower()
    if len(last) == 2 and last not in _GENERIC_CC:
        return "GB" if last == "uk" else last.upper()
    return "US"


def email_owner(address: str, store_domain: str) -> str:
    domain = address.rsplit("@", 1)[-1].lower()
    if registrable_domain(domain) == registrable_domain(store_domain):
        return "store"
    return "free_webmail" if domain in FREE_WEBMAIL else "other"


async def check_emails(found: dict[str, str], store_domain: str, resolver: MailResolver) -> list[EmailCheck]:
    """`found` maps each address to the page it was found on. Lookups run concurrently."""
    addresses = list(found)[:5]
    domains = sorted({a.rsplit("@", 1)[-1].lower() for a in addresses})
    answers = dict(zip(domains, await asyncio.gather(*(resolver.receives_mail(d) for d in domains)), strict=True))
    return [
        EmailCheck(a, found[a], email_owner(a, store_domain), answers[a.rsplit("@", 1)[-1].lower()]) for a in addresses
    ]


def check_phone(raw: str, found_on: str, region: str) -> PhoneCheck:
    try:
        number = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return PhoneCheck(raw, found_on, False, None, None)
    valid = phonenumbers.is_valid_number(number)
    return PhoneCheck(
        raw,
        found_on,
        valid,
        phonenumbers.region_code_for_number(number) if valid else None,
        _LINE_TYPES.get(phonenumbers.number_type(number)) if valid else None,
    )


def phones_in_text(text: str, region: str) -> list[str]:
    """Only strings that are valid numbers (skips order numbers, prices, dates)."""
    return [m.raw_string for m in PhoneNumberMatcher(text, region, leniency=Leniency.VALID)]
