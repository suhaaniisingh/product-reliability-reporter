"""normalize_store_url / store_domain: cleaning up what people paste."""

import pytest

from app.extraction.store_url import normalize_store_url, store_domain


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("glowlab.co", "https://glowlab.co"),
        ("  GlowLab.CO  ", "https://glowlab.co"),
        ("https://www.glowlab.co/products/serum?variant=2#reviews", "https://www.glowlab.co/products/serum?variant=2"),
        ("http://glowlab.co", "http://glowlab.co"),
        ("shop.glowlab.co.uk/", "https://shop.glowlab.co.uk/"),
        ("bücher.de", "https://xn--bcher-kva.de"),
    ],
)
def test_normalize_store_url(raw: str, expected: str) -> None:
    assert normalize_store_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["glowlab", "localhost:8000", "192.168.0.1", "ftp://glowlab.co", "https://user:pw@glowlab.co", "not a url", "glow lab.co", "-glowlab.co"],
)
def test_normalize_store_url_rejects(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_store_url(raw)


@pytest.mark.parametrize(
    ("url", "domain"),
    [("https://www.GlowLab.co/x?y=1", "glowlab.co"), ("glowlab.co", "glowlab.co"), ("shop.glowlab.co", "shop.glowlab.co")],
)
def test_store_domain(url: str, domain: str) -> None:
    assert store_domain(url) == domain
