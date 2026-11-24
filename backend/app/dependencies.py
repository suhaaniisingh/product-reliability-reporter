"""FastAPI dependencies: how routes get their collaborators.

Routes ask for an `Extractor` via `Depends(get_extractor)` instead of creating one.
Tests replace it with `app.dependency_overrides[get_extractor] = ...`, so no test
reaches the real LLM.
"""

from functools import lru_cache

from app.extraction.base import Extractor
from app.extraction.claude import ClaudeExtractor


@lru_cache
def get_extractor() -> Extractor:
    # One shared instance, so the HTTP connection pool inside the SDK client is reused.
    return ClaudeExtractor()
