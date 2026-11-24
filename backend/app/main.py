"""Application entry point: creates the FastAPI app and plugs in the routes.

Development (from backend/):  uv run fastapi dev app/main.py
  The web page runs separately on Vite's dev server (see README).

Production-like (one process, one port):
  cd web && npm run build          # compiles the page into web/dist/
  cd backend && uv run fastapi run app/main.py
  FastAPI then serves both the API (/api/...) and the page (/).
"""

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import scan, warmup

# INFO and above reach Cloud Run's logs (Python's default shows only warnings).
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per outbound request is too noisy
logger = logging.getLogger(__name__)

# backend/app/main.py -> repo root -> web/dist
DEFAULT_WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"

# Secrets (ANTHROPIC_API_KEY) live in backend/.env, which git ignores. Real
# environment variables win over the file, so a host's settings take priority.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


def create_app(web_dist: Path | None = DEFAULT_WEB_DIST) -> FastAPI:
    """Build the app. `web_dist` is the compiled web page folder (None = API only).

    Taking it as a parameter lets tests pass in a temporary folder instead of
    depending on a real frontend build.
    """
    app = FastAPI(
        title="Reliability Reporter API",
        description="Extracts the store behind a social video promo and scores how trustworthy it looks, with reasons.",
        version="0.2.0",
    )

    # API routes are registered first, so /api/... always reaches the API,
    # never the static files mounted below.
    app.include_router(scan.router)
    app.include_router(warmup.router)

    if web_dist is not None and (web_dist / "index.html").is_file():
        # html=True serves index.html for "/" (like a normal web server).
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
    elif web_dist is not None:
        logger.warning("No web build at %s; serving the API only. Run `npm run build` in web/.", web_dist)

    return app


app = create_app()
