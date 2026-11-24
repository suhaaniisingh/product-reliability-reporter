"""A stand-in extractor for tests (and the walking skeleton): no network, no cost."""

from app.extraction.base import ExtractionError, LLMExtraction
from app.schemas import Confidence

PLACEHOLDER = LLMExtraction(
    product=None,
    brand=None,
    store_url=None,
    store_url_source="none",
    mentions_link_in_bio=False,
    discount_code=None,
    confidence=Confidence.LOW,
    notes="Placeholder result: the real extractor isn't connected yet.",
)


class FakeExtractor:
    """Returns a fixed result (or raises), and records every caption it receives."""

    def __init__(self, result: LLMExtraction = PLACEHOLDER, error: ExtractionError | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def extract(self, caption: str) -> LLMExtraction:
        self.calls.append(caption)
        if self.error is not None:
            raise self.error
        return self.result
