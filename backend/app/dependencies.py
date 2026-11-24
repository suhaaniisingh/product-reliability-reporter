"""FastAPI dependencies: how routes get their collaborators.

Routes ask for an `Extractor` via `Depends(get_extractor)` instead of creating one.
Tests replace these with `app.dependency_overrides[...]`, so no test reaches the
real LLM or real DNS.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from app.extraction.base import Extractor
from app.extraction.claude import ClaudeExtractor
from app.extraction.domain_check import DnsResolver, DomainResolver
from app.ratelimit import RateLimiter
from app.signals.base import Signal
from app.signals.domain_age import DomainAgeSignal
from app.signals.fetcher import SafeFetcher
from app.signals.popularity import PopularitySignal, default_tranco
from app.signals.safe_browsing import SafeBrowsingSignal
from app.signals.store_pages import ShopifySignal, StorePageLoader, StorePagesSignal


@lru_cache
def get_extractor() -> Extractor:
    # One shared instance, so the HTTP connection pool inside the SDK client is reused.
    return ClaudeExtractor()


def get_domain_resolver() -> DomainResolver:
    return DnsResolver()


async def get_signals() -> AsyncIterator[list[Signal]]:
    """The five trust signals for one scan. A fresh page fetcher per request keeps
    each scan's robots.txt cache and page loads separate; it's closed afterwards."""
    fetcher = SafeFetcher()
    pages = StorePageLoader(fetcher)
    try:
        yield [
            DomainAgeSignal(),
            SafeBrowsingSignal(),
            StorePagesSignal(pages),
            ShopifySignal(pages),
            PopularitySignal(default_tranco()),
        ]
    finally:
        await fetcher.aclose()


@lru_cache
def get_rate_limiter() -> RateLimiter:
    # One limiter for the whole process, so counts are shared by all requests.
    return RateLimiter()
