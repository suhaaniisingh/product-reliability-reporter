"""The extractor interface, shared by the real LLM extractor and the test fake.

The API depends on the `Extractor` protocol, never on a specific LLM SDK. That
gives us three things:
- providers can be swapped (or compared on the eval set) without touching the API,
- tests inject a fake, so they run offline and for free,
- the LLM's output contract (`LLMExtraction`) stays separate from the API's
  response contract (`Extraction`), so code checks what the model said before any
  client sees it (see `postprocess.py`).
"""

from typing import Literal, Protocol

from pydantic import BaseModel


# What the model must return. The rules for each field live in prompt.py, stated once.
# No docstring and no Field descriptions here on purpose: Pydantic would put them in
# the JSON schema, and the schema is sent with every request (paid input tokens).
class LLMExtraction(BaseModel):
    product: str | None
    brand: str | None
    store_url: str | None
    store_url_source: Literal["in_caption", "guessed_from_brand", "none"]
    mentions_link_in_bio: bool
    discount_code: str | None
    confidence: Literal["high", "medium", "low"]  # a Literal, not the Confidence enum, whose docstring would be sent too
    notes: str


class ExtractionError(Exception):
    """The extractor couldn't produce a usable result (provider down, refusal, bad output).

    The route turns this into a 502: the failure is upstream, not a bug in our code.
    """


class ExtractorNotConfigured(Exception):
    """The extractor is missing its setup (e.g. no API key). The route returns a 503."""


class Extractor(Protocol):
    async def extract(self, caption: str) -> LLMExtraction: ...
