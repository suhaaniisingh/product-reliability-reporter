"""apply_rules: each deterministic check on the LLM's answer, one at a time."""

import pytest

from app.extraction.base import LLMExtraction
from app.extraction.fake import FakeResolver
from app.extraction.postprocess import apply_rules
from app.schemas import Confidence, StoreUrlSource

pytestmark = pytest.mark.anyio


def llm(**overrides: object) -> LLMExtraction:
    fields: dict[str, object] = {
        "product": "vitamin C serum",
        "brand": "GlowLab",
        "store_url": "glowlab.co",
        "store_url_source": "in_caption",
        "mentions_link_in_bio": False,
        "discount_code": None,
        "confidence": "high",
        "notes": "",
    }
    return LLMExtraction.model_validate(fields | overrides)


async def test_in_caption_url_is_kept_and_normalized() -> None:
    result = await apply_rules(llm(), "serum from GlowLab.co, link below", FakeResolver())

    assert (result.store_url, result.store_url_source, result.confidence) == ("https://glowlab.co", StoreUrlSource.IN_CAPTION, Confidence.HIGH)


async def test_in_caption_url_missing_from_the_caption_is_dropped() -> None:
    result = await apply_rules(llm(store_url="glowlab-shop.com"), "serum from glowlab.co", FakeResolver())

    assert (result.store_url, result.store_url_source, result.confidence) == (None, StoreUrlSource.NONE, Confidence.LOW)
    assert "isn't in the caption" in result.notes


@pytest.mark.parametrize("url", ["linktr.ee/glowlab", "https://www.instagram.com/glowlab", "beacons.ai/anna"])
async def test_link_pages_and_social_sites_are_never_stores(url: str) -> None:
    result = await apply_rules(llm(store_url=url), f"everything I use: {url}", FakeResolver())

    assert result.store_url is None
    assert "not a store" in result.notes


async def test_invalid_url_is_dropped() -> None:
    result = await apply_rules(llm(store_url="glowlab dot co"), "glowlab dot co", FakeResolver())

    assert result.store_url is None and result.confidence is Confidence.LOW


async def test_guess_that_exists_is_kept_and_capped_at_medium() -> None:
    resolver = FakeResolver()
    guess = llm(store_url="glowlab.com", store_url_source="guessed_from_brand", confidence="high")

    result = await apply_rules(guess, "obsessed with my GlowLab serum", resolver)

    assert (result.store_url, result.store_url_source, result.confidence) == ("https://glowlab.com", StoreUrlSource.GUESSED_FROM_BRAND, Confidence.MEDIUM)
    assert "guess" in result.notes
    assert resolver.calls == ["glowlab.com"]


async def test_guess_that_does_not_exist_is_dropped() -> None:
    guess = llm(store_url="glowlab-skin-official.com", store_url_source="guessed_from_brand", confidence="medium")

    result = await apply_rules(guess, "GlowLab serum", FakeResolver(missing={"glowlab-skin-official.com"}))

    assert result.store_url is None and result.store_url_source is StoreUrlSource.NONE
    assert "doesn't exist" in result.notes


async def test_guess_that_cannot_be_verified_is_kept_with_a_note() -> None:
    guess = llm(store_url="glowlab.com", store_url_source="guessed_from_brand", confidence="medium")

    result = await apply_rules(guess, "GlowLab serum", FakeResolver(unknown={"glowlab.com"}))

    assert result.store_url == "https://glowlab.com"
    assert "couldn't be verified" in result.notes


async def test_in_caption_urls_are_not_dns_checked() -> None:
    resolver = FakeResolver()

    await apply_rules(llm(), "glowlab.co", resolver)

    assert resolver.calls == []  # only guesses need the existence check


async def test_no_store_always_means_low_confidence() -> None:
    result = await apply_rules(llm(store_url=None, store_url_source="none", confidence="high"), "love this serum", FakeResolver())

    assert result.confidence is Confidence.LOW


async def test_user_link_wins_and_a_mismatch_is_flagged() -> None:
    result = await apply_rules(llm(), "serum at glowlab.co", FakeResolver(), user_store_url="https://glowlab-deals.shop")

    assert (result.store_url, result.store_url_source, result.confidence) == ("https://glowlab-deals.shop", StoreUrlSource.USER_PROVIDED, Confidence.HIGH)
    assert "glowlab.co" in result.notes and "glowlab-deals.shop" in result.notes


async def test_user_link_matching_the_caption_adds_no_warning() -> None:
    result = await apply_rules(llm(), "serum at glowlab.co", FakeResolver(), user_store_url="https://www.glowlab.co/serum")

    assert result.notes == ""


async def test_model_notes_are_kept() -> None:
    result = await apply_rules(llm(notes="Two products shown; used the main one."), "glowlab.co", FakeResolver())

    assert result.notes.startswith("Two products shown")
