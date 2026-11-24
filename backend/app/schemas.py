"""The API's data contract: the shapes of requests and responses.

Pydantic models do two jobs at once: they validate incoming JSON (rejecting bad
input with a 422 before our code runs) and they describe outgoing JSON (which
also appears in the auto-generated docs at /docs).
"""

from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

# Bounds how much text (and therefore how many LLM tokens) one scan can send.
MAX_CAPTION_CHARS = 5000
MAX_STORE_URL_CHARS = 2048


class Platform(StrEnum):
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    UNKNOWN = "unknown"


class StoreUrlSource(StrEnum):
    """Where `store_url` came from. The page shows this so a guess never looks like a fact."""

    IN_CAPTION = "in_caption"  # the domain appears in the caption text
    USER_PROVIDED = "user_provided"  # the user pasted the store link
    GUESSED_FROM_BRAND = "guessed_from_brand"  # the LLM proposed the brand's official domain
    NONE = "none"


class Confidence(StrEnum):
    """Coarse buckets instead of a 0-1 number: LLM self-reported probabilities are
    poorly calibrated, and three buckets are easy to label and evaluate."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ScanRequest(BaseModel):
    """What the client sends. At least one of `caption` or `store_url` is required.

    `video_url` alone isn't enough: the platforms' public endpoints don't return
    captions (see docs/DECISIONS.md), so a link gives us nothing to extract from.
    """

    caption: str | None = Field(default=None, max_length=MAX_CAPTION_CHARS)
    video_url: HttpUrl | None = None
    # A plain string, not HttpUrl: people paste "glowlab.co" without https://.
    store_url: str | None = Field(default=None, max_length=MAX_STORE_URL_CHARS)

    @field_validator("caption", "store_url", mode="before")
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        """Treat empty or whitespace-only text as "not provided"."""
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def require_caption_or_store_url(self) -> "ScanRequest":
        if self.caption is None and self.store_url is None:
            raise ValueError("Provide the video's caption, the store link, or both.")
        return self


class VideoInfo(BaseModel):
    """What we can read from the video link itself, without any network call."""

    platform: Platform
    video_id: str | None
    creator_handle: str | None


class Extraction(BaseModel):
    """What the scan found out about the promotion."""

    product: str | None
    brand: str | None
    store_url: str | None
    store_url_source: StoreUrlSource
    mentions_link_in_bio: bool
    discount_code: str | None
    confidence: Confidence
    notes: str


class ScanResponse(BaseModel):
    video: VideoInfo | None  # None when no video_url was sent
    extraction: Extraction
