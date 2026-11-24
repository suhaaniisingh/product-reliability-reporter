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

from pydantic import BaseModel, Field

from app.schemas import Confidence


class LLMExtraction(BaseModel):
    """What the model must return. The descriptions are sent to the model as part
    of the JSON schema, so they double as instructions."""

    product: str | None = Field(description="The product being promoted, or null if none is clear.")
    brand: str | None = Field(description="The brand or store name, or null if none is named.")
    store_url: str | None = Field(
        description=(
            "The store's domain. If the caption contains it, copy it exactly as written. "
            "If not, but a brand is named, give that brand's official domain if you know it. "
            "Otherwise null."
        )
    )
    store_url_source: Literal["in_caption", "guessed_from_brand", "none"] = Field(
        description="Where store_url came from: in_caption, guessed_from_brand, or none if store_url is null."
    )
    mentions_link_in_bio: bool = Field(description="True if the caption points to a link in the creator's bio or profile.")
    discount_code: str | None = Field(description="A discount code if one is given, else null.")
    confidence: Confidence = Field(
        description="How sure you are that store_url is the store actually being promoted: high, medium, or low."
    )
    notes: str = Field(description="One short sentence explaining anything ambiguous. Empty string if nothing is.")


class ExtractionError(Exception):
    """The extractor couldn't produce a usable result (provider down, refusal, bad output).

    The route turns this into a 502: the failure is upstream, not a bug in our code.
    """


class Extractor(Protocol):
    async def extract(self, caption: str) -> LLMExtraction: ...
