"""Tests for POST /api/scan: input rules, which path runs, and error mapping.

The extractor is always a FakeExtractor (see conftest.py), so these run offline.
"""

import pytest
from fastapi.testclient import TestClient

from app.extraction.base import ExtractionError, LLMExtraction
from app.extraction.fake import FakeExtractor
from app.schemas import MAX_CAPTION_CHARS

GLOWLAB = LLMExtraction(
    product="vitamin C serum",
    brand="GlowLab",
    store_url="glowlab.co",
    store_url_source="in_caption",
    mentions_link_in_bio=False,
    discount_code="GLOW20",
    confidence="high",
    notes="",
)


def test_caption_runs_the_extractor(client: TestClient, fake_extractor: FakeExtractor) -> None:
    fake_extractor.result = GLOWLAB

    response = client.post("/api/scan", json={"caption": "  Obsessed w this serum, code GLOW20 at glowlab.co  "})

    assert response.status_code == 200
    extraction = response.json()["extraction"]
    assert extraction["store_url"] == "glowlab.co"
    assert extraction["store_url_source"] == "in_caption"
    assert extraction["discount_code"] == "GLOW20"
    # Surrounding whitespace is stripped before the caption reaches the extractor.
    assert fake_extractor.calls == ["Obsessed w this serum, code GLOW20 at glowlab.co"]


def test_store_url_only_skips_the_extractor(client: TestClient, fake_extractor: FakeExtractor) -> None:
    response = client.post("/api/scan", json={"store_url": "glowlab.co"})

    assert response.status_code == 200
    extraction = response.json()["extraction"]
    assert extraction["store_url"] == "glowlab.co"
    assert extraction["store_url_source"] == "user_provided"
    assert extraction["confidence"] == "high"
    assert fake_extractor.calls == []  # no LLM call: instant and free


def test_user_store_url_beats_the_extracted_one(client: TestClient, fake_extractor: FakeExtractor) -> None:
    fake_extractor.result = GLOWLAB

    response = client.post("/api/scan", json={"caption": "serum at glowlab.co", "store_url": "glowlab-official.com"})

    extraction = response.json()["extraction"]
    assert extraction["store_url"] == "glowlab-official.com"
    assert extraction["store_url_source"] == "user_provided"
    assert extraction["product"] == "vitamin C serum"  # still extracted from the caption


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"caption": ""},
        {"caption": "   ", "store_url": "  "},
        {"video_url": "https://www.tiktok.com/@anna/video/7301234567890123456"},  # a link alone isn't enough
        {"caption": "x" * (MAX_CAPTION_CHARS + 1)},
        {"caption": "hi", "video_url": "not a url"},
    ],
)
def test_invalid_input_returns_422(client: TestClient, payload: dict) -> None:
    assert client.post("/api/scan", json=payload).status_code == 422


def test_extractor_failure_returns_502(client: TestClient, fake_extractor: FakeExtractor) -> None:
    fake_extractor.error = ExtractionError("The extraction service is unavailable.")

    response = client.post("/api/scan", json={"caption": "serum at glowlab.co"})

    assert response.status_code == 502
    assert response.json()["detail"] == "The extraction service is unavailable."
