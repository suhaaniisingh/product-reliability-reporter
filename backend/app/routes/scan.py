"""POST /api/scan: extract what a social video is promoting."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_extractor
from app.extraction.base import ExtractionError, Extractor
from app.scan import run_scan
from app.schemas import ScanRequest, ScanResponse

router = APIRouter(prefix="/api", tags=["scan"])


@router.post(
    "/scan",
    response_model=ScanResponse,
    responses={502: {"description": "The extraction service (LLM provider) failed or returned an unusable result."}},
)
async def scan(request: ScanRequest, extractor: Annotated[Extractor, Depends(get_extractor)]) -> ScanResponse:
    try:
        return await run_scan(request, extractor)
    except ExtractionError as error:
        # 502 Bad Gateway: an upstream service failed. A 500 would suggest a bug in our code.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
