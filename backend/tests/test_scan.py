"""Tests for POST /api/scan: input rules, which path runs, and error mapping.

The extractor is always a FakeExtractor (see conftest.py), so these run offline.
"""

import pytest
from fastapi.testclient import TestClient

from app.extraction.base import ExtractionError, ExtractorNotConfigured, LLMExtraction
from app.extraction.fake import FakeExtractor
from app.schemas import MAX_CAPTION_CHARS
from app.signals.fake import FakeSignal

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
    assert extraction["store_url"] == "https://glowlab.co"  # checked against the caption, then normalized
    assert extraction["store_url_source"] == "in_caption"
    assert extraction["discount_code"] == "GLOW20"
    # Surrounding whitespace is stripped before the caption reaches the extractor.
    assert fake_extractor.calls == ["Obsessed w this serum, code GLOW20 at glowlab.co"]


def test_store_url_only_skips_the_extractor(client: TestClient, fake_extractor: FakeExtractor) -> None:
    response = client.post("/api/scan", json={"store_url": "GlowLab.co"})

    assert response.status_code == 200
    extraction = response.json()["extraction"]
    assert extraction["store_url"] == "https://glowlab.co"  # normalized
    assert extraction["store_url_source"] == "user_provided"
    assert extraction["confidence"] == "high"
    assert fake_extractor.calls == []  # no LLM call: instant and free


def test_user_store_url_beats_the_extracted_one(client: TestClient, fake_extractor: FakeExtractor) -> None:
    fake_extractor.result = GLOWLAB

    response = client.post("/api/scan", json={"caption": "serum at glowlab.co", "store_url": "glowlab-official.com"})

    extraction = response.json()["extraction"]
    assert extraction["store_url"] == "https://glowlab-official.com"
    assert extraction["store_url_source"] == "user_provided"
    assert extraction["product"] == "vitamin C serum"  # still extracted from the caption
    assert "glowlab.co" in extraction["notes"]  # the mismatch is flagged, not hidden


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"caption": ""},
        {"caption": "   ", "store_url": "  "},
        {"video_url": "https://www.tiktok.com/@anna/video/7301234567890123456"},  # a link alone isn't enough
        {"caption": "x" * (MAX_CAPTION_CHARS + 1)},
        {"caption": "hi", "video_url": "not a url"},
        {"store_url": "not a website"},
    ],
)
def test_invalid_input_returns_422(client: TestClient, payload: dict) -> None:
    assert client.post("/api/scan", json=payload).status_code == 422


def test_extractor_failure_returns_502(client: TestClient, fake_extractor: FakeExtractor) -> None:
    fake_extractor.error = ExtractionError("The extraction service is unavailable.")

    response = client.post("/api/scan", json={"caption": "serum at glowlab.co"})

    assert response.status_code == 502
    assert response.json()["detail"] == "The extraction service is unavailable."


def test_video_url_is_parsed_without_a_network_call(client: TestClient) -> None:
    response = client.post(
        "/api/scan",
        json={"store_url": "glowlab.co", "video_url": "https://www.tiktok.com/@anna/video/7301234567890123456"},
    )

    assert response.json()["video"] == {"platform": "tiktok", "video_id": "7301234567890123456", "creator_handle": "anna"}


def test_video_is_null_without_a_video_url(client: TestClient) -> None:
    assert client.post("/api/scan", json={"store_url": "glowlab.co"}).json()["video"] is None


def test_missing_api_key_returns_503_but_store_link_scans_still_work(client: TestClient, fake_extractor: FakeExtractor) -> None:
    fake_extractor.error = ExtractorNotConfigured("Extraction isn't configured: set ANTHROPIC_API_KEY in backend/.env.")

    assert client.post("/api/scan", json={"caption": "serum at glowlab.co"}).status_code == 503
    assert client.post("/api/scan", json={"store_url": "glowlab.co"}).status_code == 200


def test_trust_signals_run_on_the_identified_store(client: TestClient, fake_signals: list) -> None:
    signal = FakeSignal(name="domain_age", label="Domain age", value={"age_days": 21}, explanation="Registered 21 days ago.")
    fake_signals.append(signal)

    body = client.post("/api/scan", json={"store_url": "https://www.GlowLab.co/serum"}).json()

    assert signal.calls[0].domain == "glowlab.co"
    assert body["trust"]["signals"] == [{
        "name": "domain_age", "label": "Domain age", "status": "ok", "value": {"age_days": 21},
        "explanation": "Registered 21 days ago.", "source": None, "duration_ms": body["trust"]["signals"][0]["duration_ms"],
    }]


def test_no_store_means_no_trust_report(client: TestClient, fake_signals: list) -> None:
    signal = FakeSignal()
    fake_signals.append(signal)

    body = client.post("/api/scan", json={"caption": "love this serum"}).json()  # the fake extractor finds no store

    assert body["trust"] is None
    assert signal.calls == []


def test_a_failing_signal_never_breaks_the_scan(client: TestClient, fake_signals: list) -> None:
    fake_signals.extend([FakeSignal(name="ok"), FakeSignal(name="broken", error=RuntimeError("boom"))])

    response = client.post("/api/scan", json={"store_url": "glowlab.co"})

    assert response.status_code == 200
    assert [s["status"] for s in response.json()["trust"]["signals"]] == ["ok", "failed"]
