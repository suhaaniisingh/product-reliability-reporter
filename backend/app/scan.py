"""Orchestrates one scan: decides which steps run and combines their results.

Kept separate from the HTTP route so it can be tested (and later reused by the
Chrome extension's flow or a job queue) without going through FastAPI.
"""

from app.extraction.base import Extractor
from app.extraction.domain_check import DomainResolver
from app.extraction.postprocess import apply_rules
from app.extraction.video_url import parse_video_url
from app.schemas import Confidence, Extraction, ScanRequest, ScanResponse, StoreUrlSource, TrustReport
from app.scoring import score_signals
from app.signals.base import Signal, Store
from app.signals.runner import run_signals


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


async def _trust_report(extraction: Extraction, signals: list[Signal]) -> TrustReport | None:
    if extraction.store_url is None:
        return None  # nothing to check
    results = await run_signals(signals, Store.from_url(extraction.store_url))
    return TrustReport(**score_signals(results, extraction.store_url_source).model_dump(), signals=results)


async def run_scan(
    request: ScanRequest, extractor: Extractor, resolver: DomainResolver, signals: list[Signal]
) -> ScanResponse:
    video = parse_video_url(str(request.video_url)) if request.video_url is not None else None

    if request.caption is None:
        # Validation guarantees store_url is set here. No LLM call: instant and free.
        assert request.store_url is not None
        extraction = _from_store_url_only(request.store_url)
    else:
        llm_result = await extractor.extract(request.caption)
        extraction = await apply_rules(llm_result, request.caption, resolver, user_store_url=request.store_url)

    return ScanResponse(video=video, extraction=extraction, trust=await _trust_report(extraction, signals))
