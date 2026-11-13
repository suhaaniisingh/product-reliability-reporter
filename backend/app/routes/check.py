"""POST /api/check: produce a trust report for a store URL.

Phase 1 (walking skeleton): returns a hardcoded fake report so every layer
(page -> API -> page) can be built and tested before any real signal exists.
"""

from fastapi import APIRouter

from app.schemas import CheckRequest, Report, Signal, Status

router = APIRouter(prefix="/api", tags=["check"])


def build_fake_report(store_url: str) -> Report:
    """Placeholder report matching the draft contract. Replaced signal by signal in Phase 2."""
    return Report(
        store_url=store_url,
        signals={
            "business_age": Signal(status=Status.WARNING, detail="Website created 3 weeks ago"),
            "business_transparency": Signal(status=Status.WARNING, detail="No address or phone listed"),
            "shipping_policy": Signal(status=Status.WARNING, detail="Ships from overseas, 15–30 days"),
            "independent_reviews": Signal(status=Status.UNKNOWN, detail="No independent reviews found"),
            "photo_origin": Signal(status=Status.DANGER, detail="Photos match AliExpress listings"),
        },
    )


@router.post("/check", response_model=Report)
async def check_store(request: CheckRequest) -> Report:
    """Validate the URL (done by FastAPI via CheckRequest) and return a report."""
    return build_fake_report(str(request.url))
