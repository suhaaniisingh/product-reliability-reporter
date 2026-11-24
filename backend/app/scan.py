"""Orchestrates one scan: decides which steps run and combines their results.

Kept separate from the HTTP route so it can be tested (and later reused by the
Chrome extension's flow or a job queue) without going through FastAPI.
"""

from app.extraction.base import Extractor, LLMExtraction
from app.schemas import Confidence, Extraction, ScanRequest, ScanResponse, StoreUrlSource


def _from_store_url_only(store_url: str) -> Extraction:
    return Extraction(
        product=None,
        brand=None,
        store_url=store_url,
        store_url_source=StoreUrlSource.USER_PROVIDED,
        mentions_link_in_bio=False,
        discount_code=None,
        confidence=Confidence.HIGH,
        notes="Store link provided by you; there was no caption to extract from.",
    )


def _from_llm(llm: LLMExtraction) -> Extraction:
    return Extraction(
        product=llm.product,
        brand=llm.brand,
        store_url=llm.store_url,
        store_url_source=StoreUrlSource(llm.store_url_source),
        mentions_link_in_bio=llm.mentions_link_in_bio,
        discount_code=llm.discount_code,
        confidence=llm.confidence,
        notes=llm.notes,
    )


async def run_scan(request: ScanRequest, extractor: Extractor) -> ScanResponse:
    if request.caption is None:
        # Validation guarantees store_url is set here. No LLM call: instant and free.
        assert request.store_url is not None
        return ScanResponse(video=None, extraction=_from_store_url_only(request.store_url))

    extraction = _from_llm(await extractor.extract(request.caption))

    if request.store_url is not None:
        # The user's own link beats anything extracted or guessed.
        extraction.store_url = request.store_url
        extraction.store_url_source = StoreUrlSource.USER_PROVIDED
        extraction.confidence = Confidence.HIGH

    return ScanResponse(video=None, extraction=extraction)
