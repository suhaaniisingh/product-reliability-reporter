"""ClaudeExtractor against recorded API responses (tests/fixtures/claude/).

A real SDK client is used, but its HTTP layer is replaced by a mock transport
that returns a saved response. So these tests cover our request settings, the
SDK's parsing and our error handling, with no network and no API key.
"""

import json
from collections.abc import Callable
from pathlib import Path

import anthropic
import httpx2
import pytest

from app.extraction.base import ExtractionError, ExtractorNotConfigured
from app.extraction.claude import MODEL, ClaudeExtractor

# Async tests run through anyio's pytest plugin (installed with FastAPI).
pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).parent / "fixtures" / "claude"


def make_extractor(handler: Callable[[httpx2.Request], httpx2.Response]) -> ClaudeExtractor:
    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return ClaudeExtractor(client=client)


def replay(fixture: str, sent: list[dict] | None = None) -> Callable[[httpx2.Request], httpx2.Response]:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if sent is not None:
            sent.append(json.loads(request.content))
        return httpx2.Response(200, json=json.loads((FIXTURES / fixture).read_text()))

    return handler


async def test_valid_reply_is_parsed_and_request_uses_approved_settings() -> None:
    sent: list[dict] = []
    extractor = make_extractor(replay("explicit_url.json", sent))

    result = await extractor.extract("Obsessed w this serum 😍 code GLOW20 at glowlab.co")

    assert (result.store_url, result.store_url_source, result.discount_code) == ("glowlab.co", "in_caption", "GLOW20")
    body = sent[0]
    assert body["model"] == MODEL == "claude-sonnet-5-5"
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "fallbacks" not in body  # stable API only (fallback removed 2026-11-23)
    # The caption is wrapped in delimiters, marking it as untrusted data.
    assert body["messages"][0]["content"].startswith("<caption>\n")


async def test_guessed_domain_comes_back_marked() -> None:
    result = await make_extractor(replay("guessed_from_brand.json")).extract("new Nike runners are so comfy")

    assert (result.store_url, result.store_url_source, result.confidence) == ("nike.com", "guessed_from_brand", "medium")


@pytest.mark.parametrize(
    ("fixture", "message"),
    [
        ("malformed.json", "unexpected shape"),
        ("refusal.json", "declined"),
        ("max_tokens.json", "cut off"),
    ],
)
async def test_unusable_replies_raise_extraction_error(fixture: str, message: str) -> None:
    with pytest.raises(ExtractionError, match=message):
        await make_extractor(replay(fixture)).extract("some caption")


async def test_server_error_raises_extraction_error() -> None:
    extractor = make_extractor(lambda request: httpx2.Response(529, json={"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}))

    with pytest.raises(ExtractionError, match="HTTP 529"):
        await extractor.extract("some caption")


async def test_timeout_raises_extraction_error() -> None:
    def time_out(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    with pytest.raises(ExtractionError, match="timed out"):
        await make_extractor(time_out).extract("some caption")


async def test_missing_api_key_raises_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ExtractorNotConfigured):
        await ClaudeExtractor().extract("some caption")
