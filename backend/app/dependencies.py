"""FastAPI dependencies: how routes get their collaborators.

Routes ask for an `Extractor` via `Depends(get_extractor)` instead of creating one.
Tests replace it with `app.dependency_overrides[get_extractor] = ...`.
"""

from app.extraction.base import Extractor
from app.extraction.fake import FakeExtractor


def get_extractor() -> Extractor:
    # Walking skeleton: the real Claude extractor replaces this in a later step.
    return FakeExtractor()
