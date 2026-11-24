"""The real extractor: Claude Sonnet 5.5 with structured outputs.

Why these settings (see docs/DECISIONS.md, 2026-11-23):
- `messages.parse(output_format=LLMExtraction)`: the API constrains the reply to
  our JSON schema, and the SDK validates it into the Pydantic model. Much sturdier
  than asking for JSON in the prompt and hoping.
- effort "low": extraction is a simple task; less thinking = lower cost and latency.
- Stable (non-beta) API only. A refusal comes back as HTTP 200 with
  stop_reason "refusal", so we check stop_reason before trusting the content.
"""

import logging
import os
import time
from collections.abc import Callable

import anthropic
from pydantic import ValidationError

from app.extraction.base import ExtractionError, ExtractorNotConfigured, LLMExtraction
from app.extraction.prompt import SYSTEM_PROMPT, build_user_message

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
# Room for low-effort thinking plus a small JSON reply. Hitting it means something odd happened.
MAX_TOKENS = 4096
TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2  # the SDK retries 408/409/429/5xx and connection errors with backoff


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
            self._client = anthropic.AsyncAnthropic(timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
        return self._client

    async def extract(self, caption: str) -> LLMExtraction:
        client = self._get_client()
        started = time.perf_counter()
        try:
            response = await client.messages.parse(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_message(caption)}],
                output_format=LLMExtraction,
                output_config={"effort": "low"},
            )
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
        logger.info(
            "extraction model=%s stop=%s in=%s out=%s %.2fs",
            response.model, response.stop_reason, response.usage.input_tokens, response.usage.output_tokens, seconds,
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
