"""Checks on the store's own pages: return policy, contact details, Shopify.

One StorePageLoader per scan fetches the pages once (home page, then the
return-policy and contact pages it links to, at most 4 pages in total) through
the SSRF-safe fetcher, respecting robots.txt. Two signals read from it:
- StorePagesSignal: is there a return policy, and an email or phone to contact?
- ShopifySignal: is the store built on Shopify (context only, scores 0)?

Detection is plain pattern matching: free, instant and deterministic. It
can miss unusual layouts. Postal addresses aren't detected (too varied for
patterns); an LLM reading policy pages is in docs/BACKLOG.md.
"""

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from app.signals.base import Finding, SignalUnavailable, Store
from app.signals.domains import registrable_domain
from app.signals.fetcher import FetchBlocked, FetchedPage, FetchFailed, SafeFetcher

MAX_PAGES = 4
_POLICY_WORDS = re.compile(r"\b(refunds?|returns?|exchanges?)\b", re.I)
_POLICY_LINK = re.compile(r"refund|return|exchange", re.I)
_CONTACT_LINK = re.compile(r"contact", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_NOT_EMAIL = re.compile(r"\.(png|jpe?g|gif|webp|svg|css|js)$|example\.(com|org)$|sentry|wixpress", re.I)
# North-American style and international numbers with separators, e.g. (416) 555-0199, +44 20 7946 0958.
_PHONE = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)|\d{2,4})[\s.-]\d{3,4}[\s.-]\d{3,4}(?!\d)")
_SHOPIFY_MARKERS = ("cdn.shopify.com", "shopify.theme", "myshopify.com", "shopify-section", "shopify-payment")


@dataclass
class LoadedPages:
    home: FetchedPage | None = None
    policy: FetchedPage | None = None
    contact: FetchedPage | None = None
    checked: list[str] = field(default_factory=list)
    unavailable: str | None = None  # user-safe reason the pages couldn't be checked


def _visible_text_and_links(html: str) -> tuple[str, list[tuple[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    links = [(a.get("href", ""), a.get_text(" ", strip=True)) for a in soup.find_all("a")]
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return soup.get_text(" ", strip=True), links


def _same_site(url: str, store_domain: str) -> bool:
    host = urlsplit(url).hostname or ""
    return registrable_domain(host) == registrable_domain(store_domain)


def _pick_link(links: list[tuple[str, str]], base: str, store_domain: str, pattern: re.Pattern) -> str | None:
    """The first same-site link whose visible text matches, else whose path matches.

    Only the path is matched, never the query string: Shopify login links look like
    /account/login?return_url=... and must not count as a "returns" page."""
    by_path = None
    for href, text in links:
        if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        target = urljoin(base, href)
        if not _same_site(target, store_domain):
            continue
        if pattern.search(text):
            return target
        if by_path is None and pattern.search(urlsplit(target).path):
            by_path = target
    return by_path


class StorePageLoader:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher
        self._task: asyncio.Task[LoadedPages] | None = None

    async def load(self, store: Store) -> LoadedPages:
        # Both signals call this concurrently; the first call starts the work and the
        # second waits for the same result. shield() stops one signal's timeout from
        # cancelling the work the other signal is still waiting for.
        if self._task is None:
            self._task = asyncio.create_task(self._load(store))
        return await asyncio.shield(self._task)

    async def _get(self, url: str, pages: LoadedPages) -> FetchedPage | None:
        if len(pages.checked) >= MAX_PAGES or not await self._fetcher.allowed_by_robots(url):
            return None
        try:
            page = await self._fetcher.fetch(url)
        except (FetchBlocked, FetchFailed):
            return None
        pages.checked.append(page.url)
        return page if page.status == 200 else None

    async def _load(self, store: Store) -> LoadedPages:
        parts = urlsplit(store.url)
        home_url = f"{parts.scheme}://{parts.hostname}/"
        pages = LoadedPages()
        try:
            if not await self._fetcher.allowed_by_robots(home_url):
                pages.unavailable = "this site asks bots not to visit its pages, so they weren't checked."
                return pages
            home = await self._fetcher.fetch(home_url)
        except FetchBlocked as error:
            pages.unavailable = str(error)
            return pages
        except FetchFailed:
            pages.unavailable = "the store's website couldn't be reached."
            return pages
        pages.checked.append(home.url)
        if home.status != 200:
            pages.unavailable = f"the store's home page returned an error (HTTP {home.status})."
            return pages
        pages.home = home

        _, links = _visible_text_and_links(home.text)
        policy_url = _pick_link(links, home.url, store.domain, _POLICY_LINK)
        contact_url = _pick_link(links, home.url, store.domain, _CONTACT_LINK)
        if is_shopify(home):  # Shopify stores have standard addresses for these pages
            policy_url = policy_url or urljoin(home.url, "/policies/refund-policy")
            contact_url = contact_url or urljoin(home.url, "/pages/contact")

        policy, contact = await asyncio.gather(
            self._get(policy_url, pages) if policy_url else asyncio.sleep(0, None),
            self._get(contact_url, pages) if contact_url else asyncio.sleep(0, None),
        )
        if policy is not None and _POLICY_WORDS.search(_visible_text_and_links(policy.text)[0]):
            pages.policy = policy
        pages.contact = contact
        return pages


def is_shopify(page: FetchedPage) -> bool:
    headers = page.headers
    if "x-shopid" in headers or "x-shopify-stage" in headers or "shopify" in headers.get("powered-by", "").lower():
        return True
    text = page.text.lower()
    return any(marker in text for marker in _SHOPIFY_MARKERS)


def find_contact(pages: list[FetchedPage]) -> dict[str, bool]:
    email = phone = False
    for page in pages:
        text, links = _visible_text_and_links(page.text)
        hrefs = [h for h, _ in links]
        email = email or any(h.lower().startswith("mailto:") for h in hrefs) or any(
            not _NOT_EMAIL.search(m) for m in _EMAIL.findall(text)
        )
        phone = phone or any(h.lower().startswith("tel:") for h in hrefs) or bool(_PHONE.search(text))
    return {"email": email, "phone": phone}


class StorePagesSignal:
    name = "store_pages"
    label = "Store policies and contact"
    timeout_seconds = 12.0

    def __init__(self, loader: StorePageLoader) -> None:
        self._loader = loader

    async def check(self, store: Store) -> Finding:
        pages = await self._loader.load(store)
        if pages.unavailable:
            raise SignalUnavailable(pages.unavailable)
        assert pages.home is not None
        contact = find_contact([p for p in (pages.home, pages.contact) if p is not None])
        has_policy = pages.policy is not None

        policy_text = "Return/refund policy found" if has_policy else "No return or refund policy found on the pages checked"
        found = [kind for kind in ("email", "phone") if contact[kind]]
        contact_text = f"contact {' and '.join(found)} found" if found else "no contact email or phone number found"
        return Finding(
            value={
                "return_policy": has_policy,
                "return_policy_url": pages.policy.url if pages.policy else None,
                "contact_email": contact["email"],
                "contact_phone": contact["phone"],
                "pages_checked": pages.checked,
            },
            explanation=f"{policy_text}; {contact_text}.",
        )


class ShopifySignal:
    name = "shopify"
    label = "Store platform"
    timeout_seconds = 12.0

    def __init__(self, loader: StorePageLoader) -> None:
        self._loader = loader

    async def check(self, store: Store) -> Finding:
        pages = await self._loader.load(store)
        if pages.unavailable:
            raise SignalUnavailable(pages.unavailable)
        assert pages.home is not None
        shopify = is_shopify(pages.home)
        explanation = (
            "Built on Shopify. That's common for honest shops and quickly-made stores alike, so it doesn't change the score."
            if shopify
            else "Not built on Shopify (or the platform couldn't be detected)."
        )
        return Finding(value={"shopify": shopify}, explanation=explanation)
