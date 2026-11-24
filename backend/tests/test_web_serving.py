"""Tests for serving the compiled web page from FastAPI.

Uses a fake build folder (pytest's tmp_path) so the tests don't need Node or a
real `npm run build`.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.dependencies import get_signals
from app.main import create_app


def offline_app(**kwargs):  # never run real trust signals (network) in tests
    app = create_app(**kwargs)
    app.dependency_overrides[get_signals] = lambda: []
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
