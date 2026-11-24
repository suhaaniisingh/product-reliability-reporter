"""The scorer: approved weights, labels, confidence and caps (pure function, no I/O)."""

import pytest

from app.schemas import Confidence, StoreUrlSource
from app.scoring import score_signals
from app.signals.base import SignalResult, SignalStatus

IN_CAPTION = StoreUrlSource.IN_CAPTION


def ok(name: str, **value: object) -> SignalResult:
    return SignalResult(name=name, label=name, status=SignalStatus.OK, value=dict(value), explanation="", source=None, duration_ms=1)


def failed(name: str, label: str = "Some check") -> SignalResult:
    return SignalResult(name=name, label=label, status=SignalStatus.FAILED, value=None, explanation="", source=None, duration_ms=1)


def store(age_days: int, *, rank: int | None = None, policy: bool = True, email: bool = True, phone: bool = False,
          shopify: bool = False, flagged: bool = False) -> list[SignalResult]:
    return [
        ok("domain_age", age_days=age_days),
        ok("safe_browsing", flagged=flagged, threat_types=["SOCIAL_ENGINEERING"] if flagged else []),
        ok("store_pages", return_policy=policy, contact_email=email, contact_phone=phone),
        ok("shopify", shopify=shopify),
        ok("popularity", rank=rank),
    ]


def test_sanity_example_big_established_brand_scores_about_90() -> None:
    result = score_signals(store(11_000, rank=657), IN_CAPTION)  # e.g. nike.com

    assert (result.score, result.label, result.confidence) == (90, "Higher trust", Confidence.HIGH)


def test_sanity_example_two_week_old_store_with_no_policy_or_contact_scores_0() -> None:
    result = score_signals(store(14, policy=False, email=False, shopify=True), IN_CAPTION)

    assert (result.score, result.label) == (0, "Lower trust")  # 50 - 20 - 10 - 10 - 10 (combination), floored at 0
    assert any(r.signal == "combination" and r.points == -10 for r in result.reasons)


def test_sanity_example_honest_three_year_old_small_shop_scores_70() -> None:
    result = score_signals(store(3 * 365), IN_CAPTION)

    assert (result.score, result.label) == (70, "Higher trust")


def test_sanity_example_honest_brand_new_shop_scores_40_mixed_not_low() -> None:
    result = score_signals(store(10), IN_CAPTION)

    assert (result.score, result.label) == (40, "Mixed signals")
    assert not any(r.signal == "combination" for r in result.reasons)  # has a policy and contact, so no extra penalty


@pytest.mark.parametrize(
    ("days", "points"),
    [(0, -20), (29, -20), (30, -10), (179, -10), (180, 0), (729, 0), (730, 10), (1824, 10), (1825, 15)],
)
def test_domain_age_bands(days: int, points: int) -> None:
    [age_reason] = [r for r in score_signals([ok("domain_age", age_days=days)], IN_CAPTION).reasons if r.signal == "domain_age"]

    assert age_reason.points == points


@pytest.mark.parametrize(("rank", "points"), [(1, 15), (10_000, 15), (10_001, 10), (50_000, 10), (None, 0)])
def test_popularity_bands_never_penalise(rank: int | None, points: int) -> None:
    [reason] = score_signals([ok("popularity", rank=rank)], IN_CAPTION).reasons

    assert reason.points == points


def test_the_score_is_always_50_plus_the_reasons() -> None:
    result = score_signals(store(400, rank=30_000, policy=False, email=False, phone=True), IN_CAPTION)

    assert result.score == 50 + sum(r.points for r in result.reasons)


def test_safe_browsing_listing_caps_the_score_at_10() -> None:
    result = score_signals(store(11_000, rank=657, flagged=True), IN_CAPTION)  # otherwise a 90

    assert (result.score, result.label) == (10, "Lower trust")
    [cap] = [r for r in result.reasons if r.cap is not None]
    assert cap.cap == 10 and "suspected unsafe (phishing or deceptive content)" in cap.text


def test_scores_stay_within_0_and_100() -> None:
    assert score_signals(store(5, policy=False, email=False), IN_CAPTION).score == 0
    assert score_signals(store(11_000, rank=1), IN_CAPTION).score <= 100


def test_one_failed_check_scores_0_and_lowers_confidence_to_medium() -> None:
    signals = store(11_000, rank=657)
    signals[0] = failed("domain_age", "Domain age")

    result = score_signals(signals, IN_CAPTION)

    assert result.confidence is Confidence.MEDIUM
    assert result.score == 75  # 90 without the +15 for age
    assert any(r.text == "Domain age couldn't be checked" and r.points == 0 for r in result.reasons)


def test_two_failed_checks_mean_low_confidence() -> None:
    signals = store(11_000, rank=657)
    signals[2], signals[3] = failed("store_pages"), failed("shopify")

    assert score_signals(signals, IN_CAPTION).confidence is Confidence.LOW


def test_safe_browsing_failing_alone_means_low_confidence() -> None:
    signals = store(11_000, rank=657)
    signals[1] = failed("safe_browsing")

    assert score_signals(signals, IN_CAPTION).confidence is Confidence.LOW


def test_guessed_store_is_capped_at_medium_confidence_with_a_note() -> None:
    result = score_signals(store(11_000, rank=657), StoreUrlSource.GUESSED_FROM_BRAND)

    assert result.confidence is Confidence.MEDIUM
    assert "may link to a different store" in result.notes[0]


def test_shopify_is_context_only() -> None:
    with_shopify = score_signals(store(400, shopify=True), IN_CAPTION)
    without = score_signals(store(400, shopify=False), IN_CAPTION)

    assert with_shopify.score == without.score
    assert any(r.signal == "shopify" and r.points == 0 for r in with_shopify.reasons)
