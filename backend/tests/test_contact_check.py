"""contact_check: mail-server lookups (faked), email ownership, phone validity."""

import dns.asyncresolver
import dns.resolver
import pytest

from app.signals.contact_check import DnsMailResolver, check_phone, default_region, email_owner, phones_in_text

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("domain", "region"),
    [("glowlab.ca", "CA"), ("glowlab.co.uk", "GB"), ("glowlab.de", "DE"), ("glowlab.com", "US"), ("glowlab.co", "US"), ("glowlab.io", "US")],
)
def test_default_region(domain: str, region: str) -> None:
    assert default_region(domain) == region


@pytest.mark.parametrize(
    ("address", "owner"),
    [("hello@glowlab.co", "store"), ("help@support.glowlab.co", "store"), ("glowlab@gmail.com", "free_webmail"), ("sales@other-shop.com", "other")],
)
def test_email_owner(address: str, owner: str) -> None:
    assert email_owner(address, "www.glowlab.co") == owner


@pytest.mark.parametrize(
    ("raw", "region", "valid", "country", "line_type"),
    [
        ("1-800-806-6453", "US", True, "US", "toll-free"),
        ("+44 20 7946 0958", "US", True, "GB", "landline"),
        ("+86 138 0013 8000", "CA", True, "CN", "mobile"),
        ("(000) 123-4567", "US", False, None, None),
        ("call me", "US", False, None, None),
    ],
)
def test_check_phone(raw: str, region: str, valid: bool, country: str | None, line_type: str | None) -> None:
    check = check_phone(raw, "/pages/contact", region)

    assert (check.valid, check.country, check.line_type) == (valid, country, line_type)


def test_phones_in_text_skips_non_numbers() -> None:
    text = "Call (416) 979-2000. Order #2024-1234-5678, $19.99, since 2019-05-04. Toll free 1-800-806-6453."

    assert phones_in_text(text, "CA") == ["(416) 979-2000", "1-800-806-6453"]


class Answer(list):
    pass


class MX:
    def __init__(self, exchange: str) -> None:
        self.exchange = exchange


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (Answer([MX("mx1.glowlab.co."), MX("mx2.glowlab.co.")]), True),
        (Answer([MX(".")]), False),  # "null MX": explicitly no mail
        (dns.resolver.NXDOMAIN(), False),  # domain doesn't exist
        (dns.resolver.NoAnswer(), False),  # no mail servers
        (dns.resolver.LifetimeTimeout(), None),  # couldn't tell
    ],
)
async def test_dns_mail_resolver(monkeypatch: pytest.MonkeyPatch, outcome: object, expected: bool | None) -> None:
    async def fake_resolve(self, domain: str, rdtype: str, lifetime: float):
        assert rdtype == "MX"
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(dns.asyncresolver.Resolver, "resolve", fake_resolve)

    assert await DnsMailResolver().receives_mail("glowlab.co") is expected
