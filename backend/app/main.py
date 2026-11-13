"""Application entry point: creates the FastAPI app and plugs in the routes.

Run locally (from backend/):  uv run fastapi dev app/main.py
"""

from fastapi import FastAPI

from app.routes import check

app = FastAPI(
    title="Trust Checker API",
    description="Evidence-based trust reports for online stores.",
    version="0.1.0",
)

app.include_router(check.router)
