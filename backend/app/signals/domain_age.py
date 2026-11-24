"""Domain age via RDAP, the structured (JSON) successor to WHOIS.

How a lookup works:
1. IANA publishes a "bootstrap" file mapping each top-level domain (com, co, shop...)
   to the registry's RDAP server. It's fetched once and cached for a day.
2. We ask that registry for the registrable domain (glowlab.co, not shop.glowlab.co)
   and read the "registration" event's date.

The servers contacted are IANA and the registries IANA lists, never an address
from user input, so the plain HTTP client is used here (not the SSRF-safe one).
"""

import time
from datetime import UTC, date, datetime

import httpx

from app.signals.base import Finding, SignalUnavailable, Store
from app.signals.domains import registrable_domain

BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"
BOOTSTRAP_TTL_SECONDS = 24 * 3600


def describe_age(days: int) -> str:
    if days < 60:
        return f"{days} day{'s' if days != 1 else ''}"
    if days < 730:
        return f"about {round(days / 30.4)} months"
    return f"about {days // 365} years"


class DomainAgeSignal:
    name = "domain_age"
    label = "Domain age"
    timeout_seconds = 6.0

    # Shared across requests in this process: the bootstrap file rarely changes.
    _bootstrap: dict[str, str] = {}
    _bootstrap_loaded_at = 0.0

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, today: date | None = None) -> None:
        self._transport = transport
        self._today = today

    async def _rdap_base(self, client: httpx.AsyncClient, tld: str) -> str | None:
        cls = type(self)
        if not cls._bootstrap or time.monotonic() - cls._bootstrap_loaded_at > BOOTSTRAP_TTL_SECONDS:
            response = await client.get(BOOTSTRAP_URL)
            response.raise_for_status()
            table = {}
            for tlds, urls in response.json()["services"]:
                https = [u for u in urls if u.startswith("https://")] or urls
                for t in tlds:
                    table[t.lower()] = https[0]
            cls._bootstrap, cls._bootstrap_loaded_at = table, time.monotonic()
        return cls._bootstrap.get(tld)

    async def check(self, store: Store) -> Finding:
        domain = registrable_domain(store.domain)
        tld = domain.rsplit(".", 1)[-1]
        async with httpx.AsyncClient(transport=self._transport, timeout=5.0, follow_redirects=True) as client:
            base = await self._rdap_base(client, tld)
            if base is None:
                raise SignalUnavailable(f"no public registration data is published for .{tld} domains.")
            response = await client.get(f"{base.rstrip('/')}/domain/{domain}", headers={"Accept": "application/rdap+json"})
            if response.status_code == 404:
                raise SignalUnavailable(f"no registration record was found for {domain}.")
            response.raise_for_status()

        registered = next(
            (e.get("eventDate") for e in response.json().get("events", []) if e.get("eventAction") == "registration"),
            None,
        )
        if not registered:
            raise SignalUnavailable(f"the registry doesn't publish when {domain} was registered.")
        registered_on = datetime.fromisoformat(registered.replace("Z", "+00:00")).date()
        today = self._today or datetime.now(UTC).date()
        age_days = max(0, (today - registered_on).days)
        return Finding(
            value={"age_days": age_days, "registered_on": registered_on.isoformat(), "domain": domain},
            explanation=f"{domain} was registered {describe_age(age_days)} ago ({registered_on.isoformat()}).",
        )
