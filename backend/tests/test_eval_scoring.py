"""The eval script's matching rules, and a check that the eval CSV stays valid."""

import pytest

from scripts.eval_extraction import DEFAULT_CSV, load_rows, match_store, match_text


def test_eval_csv_is_valid() -> None:
    rows = load_rows(DEFAULT_CSV)

    assert len(rows) >= 30
    assert {r.split for r in rows} == {"dev", "test"}


@pytest.mark.parametrize(
    ("expected", "predicted", "contains", "result"),
    [
        ("CeraVe", "cerave", False, True),  # case-insensitive
        ("Bloom & Root", "Bloom and Root", False, False),  # "&" vs "and" is a real difference
        ("GlowLab Skin|GlowLab", "glowlab", False, True),  # any alternative
        ("", None, False, True),  # blank = must be null
        ("", "Nike", False, False),
        ("*", "anything", False, None),  # not scored
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
