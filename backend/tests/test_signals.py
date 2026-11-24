"""The five trust signals, each against saved responses / fake websites (offline)."""

import inspect
import json
from datetime import date

import httpx
import pytest

from app.signals.base import SignalStatus, SignalUnavailable, Store
from app.signals.domain_age import DomainAgeSignal, describe_age
from app.signals.domains import registrable_domain
from app.signals.fetcher import SafeFetcher
from app.signals.popularity import PopularitySignal, TrancoList
from app.signals.runner import run_signals
from app.signals.safe_browsing import ATTRIBUTION, SafeBrowsingSignal
from app.signals.store_pages import ShopifySignal, StorePageLoader, StorePagesSignal

pytestmark = pytest.mark.anyio


# ---------- registrable domain ----------

@pytest.mark.parametrize(
    ("host", "domain"),
    [
        ("www.nike.com", "nike.com"),
        ("shop.glowlab.co.uk", "glowlab.co.uk"),
        ("glowlab.myshopify.com", "glowlab.myshopify.com"),  # each Shopify store is its own site
    ],
)
def test_registrable_domain(host: str, domain: str) -> None:
    assert registrable_domain(host) == domain


# ---------- domain age (RDAP) ----------

BOOTSTRAP = {"services": [[["com", "net"], ["https://rdap.verisign.example/com/v1/"]], [["co"], ["https://rdap.nic.co.example/"]]]}


def rdap(events: list[dict]) -> dict:
    return {"objectClassName": "domain", "ldhName": "GLOWLAB.CO", "events": events}


@pytest.fixture(autouse=True)
def fresh_bootstrap_cache() -> None:
    DomainAgeSignal._bootstrap, DomainAgeSignal._bootstrap_loaded_at = {}, 0.0


def rdap_transport(record: dict | None, status: int = 200) -> tuple[httpx.MockTransport, list[str]]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "data.iana.org":
            return httpx.Response(200, json=BOOTSTRAP)
        return httpx.Response(status, json=record or {})

    return httpx.MockTransport(handler), seen


async def test_domain_age_from_the_registration_event() -> None:
    transport, seen = rdap_transport(rdap([{"eventAction": "registration", "eventDate": "2026-11-03T14:00:00Z"}, {"eventAction": "last changed", "eventDate": "2026-11-20T00:00:00Z"}]))
    signal = DomainAgeSignal(transport=transport, today=date(2026, 11, 24))

    finding = await signal.check(Store.from_url("https://shop.glowlab.co/serum"))

    assert finding.value == {"age_days": 21, "registered_on": "2026-11-03", "domain": "glowlab.co"}
    assert finding.explanation == "glowlab.co was registered 21 days ago (2026-11-03)."
    assert seen[-1] == "https://rdap.nic.co.example/domain/glowlab.co"  # registrable domain, registry from IANA


@pytest.mark.parametrize(("days", "text"), [(1, "1 day"), (21, "21 days"), (90, "about 3 months"), (800, "about 2 years"), (11_000, "about 30 years")])
def test_describe_age(days: int, text: str) -> None:
    assert describe_age(days) == text


async def test_unknown_tld_is_unavailable_with_a_reason() -> None:
    transport, _ = rdap_transport(None)

    with pytest.raises(SignalUnavailable, match=r"\.shop domains"):
        await DomainAgeSignal(transport=transport).check(Store.from_url("https://glowlab.shop"))


async def test_unregistered_domain_is_unavailable() -> None:
    transport, _ = rdap_transport(None, status=404)

    with pytest.raises(SignalUnavailable, match="no registration record"):
        await DomainAgeSignal(transport=transport).check(Store.from_url("https://glowlab.co"))


async def test_missing_registration_date_is_unavailable() -> None:
    transport, _ = rdap_transport(rdap([{"eventAction": "expiration", "eventDate": "2027-01-01T00:00:00Z"}]))

    with pytest.raises(SignalUnavailable, match="doesn't publish"):
        await DomainAgeSignal(transport=transport).check(Store.from_url("https://glowlab.co"))


async def test_bootstrap_is_fetched_once() -> None:
    transport, seen = rdap_transport(rdap([{"eventAction": "registration", "eventDate": "2020-01-01T00:00:00Z"}]))
    signal = DomainAgeSignal(transport=transport, today=date(2026, 11, 24))

    await signal.check(Store.from_url("https://a.co"))
    await signal.check(Store.from_url("https://b.co"))

    assert sum("iana" in url for url in seen) == 1


# ---------- Google Safe Browsing ----------

def safe_browsing_transport(matches: list[dict]) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"matches": matches} if matches else {})

    return httpx.MockTransport(handler), seen


async def test_flagged_site_is_reported_with_hedged_wording_and_attribution() -> None:
    match = {"threatType": "SOCIAL_ENGINEERING", "platformType": "ANY_PLATFORM", "threat": {"url": "https://glowlab.co/"}, "cacheDuration": "300s"}
    transport, seen = safe_browsing_transport([match])

    finding = await SafeBrowsingSignal(api_key="test-key", transport=transport).check(Store.from_url("https://glowlab.co/serum"))

    assert finding.value == {"flagged": True, "threat_types": ["SOCIAL_ENGINEERING"]}
    assert "suspected phishing" in finding.explanation and "may be unsafe" in finding.explanation
    assert finding.source == ATTRIBUTION
    request = seen[0]
    assert request.headers["x-goog-api-key"] == "test-key" and "key=" not in str(request.url)  # key never in the URL
    urls = [e["url"] for e in json.loads(request.content)["threatInfo"]["threatEntries"]]
    assert urls == ["https://glowlab.co/", "https://glowlab.co/serum"]  # the exact link and the home page


async def test_clean_site() -> None:
    transport, _ = safe_browsing_transport([])

    finding = await SafeBrowsingSignal(api_key="test-key", transport=transport).check(Store.from_url("https://nike.com"))

    assert finding.value == {"flagged": False, "threat_types": []}
    assert finding.explanation == "Not on Google Safe Browsing's list of unsafe sites."


async def test_no_key_means_unavailable() -> None:
    with pytest.raises(SignalUnavailable, match="not configured"):
        await SafeBrowsingSignal(api_key="").check(Store.from_url("https://nike.com"))


# ---------- store pages + Shopify (fake websites through the safe fetcher) ----------

SHOPIFY_HOME = """<html><head><link href="https://cdn.shopify.com/s/files/theme.css"></head><body>
<a href="/collections/all">Shop</a> <a href="/policies/refund-policy">Refund policy</a> <a href="/pages/contact">Contact us</a>
<script>var x = "hidden@tracking.io";</script></body></html>"""
POLICY = "<html><body><h1>Refund policy</h1><p>Returns accepted within 30 days.</p></body></html>"
CONTACT = '<html><body><p>Email <a href="mailto:hello@glowlab.co">hello@glowlab.co</a> or call (416) 555-0199.</p></body></html>'
BARE_HOME = '<html><body><h1>GLOW SERUM 70% OFF</h1><img src="logo@2x.png"><a href="/products/serum">Buy now</a></body></html>'


class OneAddressResolver:
    async def resolve(self, host: str) -> list[str]:
        return ["93.184.215.14"]


def store_site(pages: dict[str, str], robots: str = "User-agent: *\nAllow: /\n") -> tuple[SafeFetcher, list[str]]:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.raw_path.decode()
        requested.append(path)
        if path == "/robots.txt":
            return httpx.Response(200, text=robots, headers={"content-type": "text/plain"})
        if path in pages:
            return httpx.Response(200, text=pages[path], headers={"content-type": "text/html"})
        return httpx.Response(404, text="not found", headers={"content-type": "text/html"})

    return SafeFetcher(resolver=OneAddressResolver(), transport=httpx.MockTransport(handler)), requested


async def run_page_signals(pages: dict[str, str], **kwargs) -> tuple[list, list[str]]:
    fetcher, requested = store_site(pages, **kwargs)
    loader = StorePageLoader(fetcher)
    results = await run_signals([StorePagesSignal(loader), ShopifySignal(loader)], Store.from_url("https://glowlab.co/products/serum"))
    await fetcher.aclose()
    return results, requested


async def test_shopify_store_with_policy_and_contact() -> None:
    (pages, platform), requested = await run_page_signals({"/": SHOPIFY_HOME, "/policies/refund-policy": POLICY, "/pages/contact": CONTACT})

    assert pages.status is SignalStatus.OK and platform.status is SignalStatus.OK
    assert pages.value["return_policy"] is True and pages.value["return_policy_url"] == "https://glowlab.co/policies/refund-policy"
    assert pages.value["contact_email"] is True and pages.value["contact_phone"] is True
    assert pages.explanation == "Return/refund policy found; contact email and phone found."
    assert platform.value == {"shopify": True}
    assert requested.count("/") == 1  # the home page is fetched once for both signals


async def test_bare_store_has_no_policy_and_no_contact() -> None:
    (pages, platform), _ = await run_page_signals({"/": BARE_HOME})

    assert pages.value["return_policy"] is False
    assert pages.value["contact_email"] is False  # logo@2x.png isn't an email address
    assert pages.value["contact_phone"] is False
    assert pages.explanation == "No return or refund policy found on the pages checked; no contact email or phone number found."
    assert platform.value == {"shopify": False}


async def test_emails_inside_scripts_dont_count() -> None:
    (pages, _), _ = await run_page_signals({"/": SHOPIFY_HOME})  # only email is in a <script>

    assert pages.value["contact_email"] is False


async def test_shopify_standard_policy_address_is_tried_when_not_linked() -> None:
    home = SHOPIFY_HOME.replace('<a href="/policies/refund-policy">Refund policy</a>', "")
    (pages, _), requested = await run_page_signals({"/": home, "/policies/refund-policy": POLICY})

    assert "/policies/refund-policy" in requested
    assert pages.value["return_policy"] is True


async def test_a_policy_link_to_a_missing_page_doesnt_count() -> None:
    (pages, _), _ = await run_page_signals({"/": SHOPIFY_HOME})  # the linked refund page is a 404

    assert pages.value["return_policy"] is False


async def test_query_strings_dont_count_as_policy_links() -> None:
    """Regression (tentree.com, 2026-11-24): /account/login?return_url=... matched "return"."""
    home = (
        '<a href="/account/login?return_url=/account">Sign in</a>'
        '<a href="https://returns.glowlab.co/">returns &amp; exchanges</a>'  # same site, different subdomain
    )
    fetcher, requested = store_site({"/": home, "/account/login": "login page"})
    loader = StorePageLoader(fetcher)

    pages = await loader.load(Store.from_url("https://glowlab.co"))

    assert "/account/login" not in requested
    assert pages.checked[-1] == "https://returns.glowlab.co/"
    await fetcher.aclose()


async def test_robots_txt_blocking_means_not_checked() -> None:
    (pages, platform), requested = await run_page_signals({"/": SHOPIFY_HOME}, robots="User-agent: *\nDisallow: /\n")

    assert pages.status is SignalStatus.FAILED and platform.status is SignalStatus.FAILED
    assert "asks bots not to visit" in pages.explanation
    assert requested == ["/robots.txt"]  # nothing else was fetched


async def test_unreachable_store() -> None:
    (pages, _), _ = await run_page_signals({})  # home page is a 404

    assert pages.status is SignalStatus.FAILED
    assert "HTTP 404" in pages.explanation


# ---------- popularity (Tranco) ----------

TRANCO = TrancoList({"nike.com": 657, "glossier.com": 45_620}, downloaded_on="2026-11-24")


async def test_popular_site_has_its_rank() -> None:
    finding = await PopularitySignal(TRANCO).check(Store.from_url("https://www.nike.com/shoes"))

    assert finding.value == {"rank": 657, "list_size": 2, "domain": "nike.com"}
    assert "rank 657" in finding.explanation and "Tranco" in (finding.source or "")


async def test_unlisted_site_is_explained_as_normal() -> None:
    finding = await PopularitySignal(TRANCO).check(Store.from_url("https://glowlab.co"))

    assert finding.value["rank"] is None
    assert "normal for small shops" in finding.explanation


async def test_missing_list_is_unavailable() -> None:
    with pytest.raises(SignalUnavailable, match="isn't available"):
        await PopularitySignal(None).check(Store.from_url("https://glowlab.co"))


def test_signals_are_async() -> None:
    for cls in (DomainAgeSignal, SafeBrowsingSignal, StorePagesSignal, ShopifySignal, PopularitySignal):
        assert inspect.iscoroutinefunction(cls.check)
