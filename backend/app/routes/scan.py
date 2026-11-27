"""POST /api/scan: extract what a social video is promoting, then check the store."""

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_domain_resolver, get_extractor, get_rate_limiter, get_signals
from app.extraction.base import ExtractionError, Extractor, ExtractorNotConfigured
from app.extraction.domain_check import DomainResolver
from app.ratelimit import RateLimiter, client_ip
from app.scan import run_scan
from app.schemas import ScanRequest, ScanResponse
from app.signals.base import Signal

router = APIRouter(prefix="/api", tags=["scan"])


@router.post(
    "/scan",
    response_model=ScanResponse,
    responses={
        502: {"description": "The extraction service (LLM provider) failed or returned an unusable result."},
        429: {"description": "This visitor is over a rate limit; see the Retry-After header."},
        503: {"description": "Extraction isn't configured, or today's site-wide caption budget is used up."},
    },
)
async def scan(
    request: ScanRequest,
    http_request: Request,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    extractor: Annotated[Extractor, Depends(get_extractor)],
    resolver: Annotated[DomainResolver, Depends(get_domain_resolver)],
    signals: Annotated[list[Signal], Depends(get_signals)],
) -> ScanResponse:
    # Rate limits come first, before any paid call or outbound request.
    ip = client_ip(
        http_request.headers.get("x-forwarded-for"),
        http_request.client.host if http_request.client else None,
        int(os.environ.get("TRUSTED_PROXY_HOPS", "0")),  # 1 on the server (Caddy sets one entry)
    )
    decision = limiter.check(ip, "caption" if request.caption is not None else "store")
    if not decision.allowed:
        raise HTTPException(decision.status, detail=decision.message, headers={"Retry-After": str(decision.retry_after)})

    try:
        return await run_scan(request, extractor, resolver, signals)
    except ExtractionError as error:
        # 502 Bad Gateway: an upstream service failed. A 500 would suggest a bug in our code.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except ExtractorNotConfigured as error:
        # 503: this server can't do extraction right now; store-link-only scans still work.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
