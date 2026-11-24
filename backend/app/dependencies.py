"""FastAPI dependencies: how routes get their collaborators.

Routes ask for an `Extractor` via `Depends(get_extractor)` instead of creating one.
Tests replace these with `app.dependency_overrides[...]`, so no test reaches the
real LLM or real DNS.
"""

from functools import lru_cache

from app.extraction.base import Extractor
from app.extraction.claude import ClaudeExtractor
from app.extraction.domain_check import DnsResolver, DomainResolver


@lru_cache
def get_extractor() -> Extractor:
    # One shared instance, so the HTTP connection pool inside the SDK client is reused.
    return ClaudeExtractor()


def get_domain_resolver() -> DomainResolver:
    return DnsResolver()
