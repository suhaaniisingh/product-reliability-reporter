"""The real extractor: Claude Sonnet 5.5 with structured outputs.

Why these settings (see docs/DECISIONS.md, 2026-11-23):
- `messages.parse(output_format=LLMExtraction)`: the API constrains the reply to
  our JSON schema, and the SDK validates it into the Pydantic model. Much sturdier
  than asking for JSON in the prompt and hoping.
- effort "low": extraction is a simple task; less thinking = lower cost and latency.
- Stable (non-beta) API only. A refusal comes back as HTTP 200 with
  stop_reason "refusal", so we check stop_reason before trusting the content.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.extraction.base import ExtractionError, ExtractorNotConfigured, LLMExtraction
from app.extraction.prompt import SYSTEM_PROMPT, build_user_message

if TYPE_CHECKING:  # only for type hints; the SDK itself is imported on first use (see _anthropic)
    import anthropic


def _anthropic():
    """Import the Anthropic SDK lazily. It's hundreds of small modules, and on a Cloud
    Run cold start reading them made the server ~20 s slow to answer anything, even
    pages and store-link scans that never call Claude. Now only the first caption
    scan pays that cost."""
    import anthropic

    return anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
# Room for low-effort thinking plus a small JSON reply. Hitting it means something odd happened.
MAX_TOKENS = 4096
TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2  # the SDK retries 408/409/429/5xx and connection errors with backoff


def build_request(caption: str, model: str = MODEL) -> dict:
    """The request body for one caption, minus the answer format.

    Shared by the live extractor and the eval's batch mode, so both send exactly the
    same prompt (and therefore hit the same prompt cache and get the same behaviour).
    """
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        # Cache marker on the system prompt: the rules + answer schema are identical
        # on every call, so calls within 5 minutes read them from the cache at 5% of
        # the input price. (Top-level automatic caching would put the marker after the
        # caption, which differs every time, so nothing would ever be reused.)
        "system": [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": build_user_message(caption)}],
        "output_config": {"effort": "low"},
    }


def build_batch_params(caption: str, model: str = MODEL) -> dict:
    """build_request() plus the JSON answer format, for the Message Batches API
    (which has no parse() helper). Uses the SDK's own schema conversion, so the
    schema is byte-identical to what messages.parse() sends."""
    from anthropic.lib._parse._transform import to_json_output_format  # SDK-internal; tested

    params = build_request(caption, model)
    params["output_config"] = {**params["output_config"], "format": to_json_output_format(LLMExtraction)}
    return params


class ClaudeExtractor:
    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
        model: str = MODEL,
        on_response: Callable[[anthropic.types.Message, float], None] | None = None,
    ) -> None:
        """`client` is injectable so tests can pass one with a mocked HTTP transport.
        `on_response(message, seconds)` lets the eval script collect token usage and latency."""
        self._client = client
        self._model = model
        self._on_response = on_response

    def _get_client(self) -> anthropic.AsyncAnthropic:
        # Created lazily: scans that send only a store link never need a key.
        if self._client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise ExtractorNotConfigured("Extraction isn't configured: set ANTHROPIC_API_KEY in backend/.env.")
            self._client = _anthropic().AsyncAnthropic(timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
        return self._client

    async def extract(self, caption: str) -> LLMExtraction:
        client = self._get_client()
        anthropic = _anthropic()
        started = time.perf_counter()
        try:
            response = await client.messages.parse(**build_request(caption, self._model), output_format=LLMExtraction)
        except anthropic.APITimeoutError as error:
            raise ExtractionError("The extraction service timed out.") from error
        except anthropic.APIConnectionError as error:
            raise ExtractionError("Couldn't reach the extraction service.") from error
        except anthropic.APIStatusError as error:
            logger.warning("Claude API error %s: %s", error.status_code, error.message)
            raise ExtractionError(f"The extraction service returned an error (HTTP {error.status_code}).") from error
        except ValidationError as error:
            # The SDK validates the reply against LLMExtraction inside the call.
            raise ExtractionError("The extraction service returned output in an unexpected shape.") from error

        seconds = time.perf_counter() - started
        usage = response.usage
        logger.info(
            "extraction model=%s stop=%s in=%s cache_write=%s cache_read=%s out=%s %.2fs",
            response.model, response.stop_reason, usage.input_tokens, usage.cache_creation_input_tokens,
            usage.cache_read_input_tokens, usage.output_tokens, seconds,
        )
        if self._on_response is not None:
            self._on_response(response, seconds)

        # Check why the model stopped before trusting the content.
        if response.stop_reason == "refusal":
            raise ExtractionError("The extraction service declined to process this caption.")
        if response.stop_reason == "max_tokens":
            raise ExtractionError("The extraction service's reply was cut off.")
        if response.parsed_output is None:
            raise ExtractionError("The extraction service returned no usable result.")
        return response.parsed_output
