"""The eval script's matching rules, and a check that the eval CSV stays valid."""

import pytest

from scripts.eval_extraction import DEFAULT_CSV, load_rows, match_store, match_text


def test_eval_csv_is_valid() -> None:
    rows = load_rows(DEFAULT_CSV)

    assert len(rows) >= 30
    assert {r.split for r in rows} == {"dev", "test", "test2"}


@pytest.mark.parametrize(
    ("expected", "predicted", "contains", "result"),
    [
        ("CeraVe", "cerave", False, True),  # case-insensitive
        ("Bloom & Root", "Bloom and Root", False, False),  # "&" vs "and" is a real difference
        ("GlowLab Skin|GlowLab", "glowlab", False, True),  # any alternative
        ("", None, False, True),  # blank = must be null
        ("", "Nike", False, False),
        ("*", "anything", False, None),  # not scored
        ("Kyoto Leaf|*", None, False, None),  # "*" among alternatives also means not scored
        ("Nike", None, False, False),
        ("matcha whisk set", "Matcha whisk set (bamboo)", True, True),  # product: containment allowed
        ("matcha whisk set", "Matcha whisk set (bamboo)", False, False),
    ],
)
def test_match_text(expected: str, predicted: str | None, contains: bool, result: bool | None) -> None:
    assert match_text(expected, predicted, contains=contains) is result


@pytest.mark.parametrize(
    ("expected", "predicted", "result"),
    [
        ("glowlab.co", "https://www.GlowLab.co/products/x", True),
        ("dyson.com|dyson.ca", "https://dyson.ca", True),
        ("glowlab.co", "https://glowlab.com", False),
        ("", None, True),
        ("", "https://glowlab.co", False),
        ("glowlab.co", None, False),
    ],
)
def test_match_store(expected: str, predicted: str | None, result: bool) -> None:
    assert match_store(expected, predicted) is result


def test_call_cost_uses_cache_and_batch_pricing() -> None:
    from scripts.eval_extraction import call_cost

    usage = {"input": 1_000_000, "cache_write": 0, "cache_read": 0, "output": 0}
    assert call_cost("claude-sonnet-5-5", usage, batch=False) == pytest.approx(2.00)
    assert call_cost("claude-sonnet-5-5", usage, batch=True) == pytest.approx(1.00)  # batch = half price
    cached = {"input": 0, "cache_write": 0, "cache_read": 1_000_000, "output": 0}
    assert call_cost("claude-sonnet-5-5", cached, batch=False) == pytest.approx(0.10)  # cache reads: 5%
    written = {"input": 0, "cache_write": 1_000_000, "cache_read": 0, "output": 0}
    assert call_cost("claude-sonnet-5-5", written, batch=False) == pytest.approx(2.50)  # cache writes: 1.25x


def test_request_key_changes_with_prompt_model_or_caption(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.extraction.claude as claude
    from scripts.eval_extraction import request_key

    key = request_key("caption", "claude-sonnet-5-5")
    assert request_key("caption", "claude-sonnet-5-5") == key  # stable
    assert request_key("other caption", "claude-sonnet-5-5") != key
    assert request_key("caption", "claude-haiku-5-5") != key
    monkeypatch.setattr(claude, "SYSTEM_PROMPT", "a different prompt")
    assert request_key("caption", "claude-sonnet-5-5") != key  # a prompt change invalidates cached answers
