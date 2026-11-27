"""GET /api/warmup: load slow-to-import pieces before the first caption scan needs them.

The web page calls it as soon as it opens, so the first caption scan doesn't pay
for importing the Anthropic SDK and loading the popularity list. The deploy's smoke
test also calls it.

History: it became an endpoint rather than a background thread (measured 2026-11-24) because, with
Cloud Run's request-based billing, an instance only gets CPU while it's handling
a request. A background warm-up thread started at boot took 30 s, because it
only progressed while other requests were running. So the web page calls this
endpoint as soon as it opens: the work happens inside a request (with CPU), while
the visitor is still pasting a caption, and the page itself never waits for it.
Repeat calls return immediately.
"""

import asyncio
import importlib
import logging
import threading
import time

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["warmup"])
logger = logging.getLogger(__name__)

_lock = threading.Lock()
_done = False


def warm_up() -> None:
    global _done
    with _lock:  # concurrent calls wait for the same work instead of repeating it
        if _done:
            return
        started = time.perf_counter()
        importlib.import_module("anthropic")  # ~10 s on a Cloud Run cold start
        from app.signals.popularity import default_tranco

        default_tranco()
        _done = True
        logger.info("warm-up finished in %.1fs", time.perf_counter() - started)


@router.get("/warmup")
async def warmup() -> dict[str, bool]:
    await asyncio.to_thread(warm_up)  # in a thread, so the server keeps answering other requests
    return {"ready": True}
