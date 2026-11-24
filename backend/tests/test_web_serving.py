"""Tests for serving the compiled web page from FastAPI.

Uses a fake build folder (pytest's tmp_path) so the tests don't need Node or a
real `npm run build`.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.dependencies import get_rate_limiter, get_signals
from app.main import create_app
from app.ratelimit import RateLimiter


def offline_app(**kwargs):  # never run real trust signals (network) in tests
    app = create_app(**kwargs)
    app.dependency_overrides[get_signals] = lambda: []
    limiter = RateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    return app


def make_fake_build(folder: Path) -> Path:
    (folder / "index.html").write_text("<html><title>Reliability Reporter</title></html>")
    return folder


def test_page_is_served_at_root(tmp_path: Path) -> None:
    client = TestClient(offline_app(web_dist=make_fake_build(tmp_path)))

    response = client.get("/")

    assert response.status_code == 200
    assert "Reliability Reporter" in response.text


def test_api_still_works_when_page_is_mounted(tmp_path: Path) -> None:
    # Guards against route-ordering bugs where the "/" mount swallows /api requests.
    client = TestClient(offline_app(web_dist=make_fake_build(tmp_path)))

    response = client.post("/api/scan", json={"store_url": "example-store.com"})

    assert response.status_code == 200
    assert response.json()["extraction"]["store_url_source"] == "user_provided"


def test_api_works_without_a_web_build(tmp_path: Path) -> None:
    client = TestClient(offline_app(web_dist=tmp_path / "missing"))

    assert client.post("/api/scan", json={"store_url": "example-store.com"}).status_code == 200
    assert client.get("/").status_code == 404


def test_loading_the_app_does_not_load_the_anthropic_sdk() -> None:
    """Cold-start guard: pages and store-link scans shouldn't wait for the SDK to load."""
    import subprocess
    import sys

    code = "import sys, app.main; print('anthropic' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

    assert result.stdout.strip() == "False"


def test_warmup_endpoint(tmp_path: Path) -> None:
    client = TestClient(offline_app(web_dist=tmp_path / "missing"))

    assert client.get("/api/warmup").json() == {"ready": True}
    assert client.get("/api/warmup").json() == {"ready": True}  # repeat calls are cheap no-ops
