"""Tests for POST /api/check.

TestClient calls the app in-process (no real server or network), so these run fast.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import Status

client = TestClient(app)

EXPECTED_SIGNALS = {
    "business_age",
    "business_transparency",
    "shipping_policy",
    "independent_reviews",
    "photo_origin",
}


def test_valid_url_returns_report() -> None:
    response = client.post("/api/check", json={"url": "https://example-store.com"})

    assert response.status_code == 200
    body = response.json()
    # Pydantic normalizes URLs, adding a trailing slash to a bare domain.
    assert body["store_url"] == "https://example-store.com/"
    assert set(body["signals"]) == EXPECTED_SIGNALS
    for signal in body["signals"].values():
        assert signal["status"] in {s.value for s in Status}
        assert signal["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"url": "not a url"},
        {"url": "ftp://example-store.com"},  # only http/https allowed
        {"url": ""},
        {},  # missing field
    ],
)
def test_invalid_input_returns_422(payload: dict) -> None:
    response = client.post("/api/check", json=payload)

    assert response.status_code == 422
