"""Basic store-URL clean-up: what people paste is rarely a perfect URL.

Phase 1 only needs the basics (add https://, lowercase the host, check it looks
like a public domain). Stripping tracking parameters and comparing by registrable
domain are in docs/BACKLOG.md for Phase 2.

This module must not import app.schemas (schemas uses it for validation).
"""

import re
from urllib.parse import urlsplit

# Labels of letters/digits/hyphens separated by dots, ending in a real-looking TLD.
# This rejects "localhost", bare words and IP addresses, which are never stores.
_DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$")


def normalize_store_url(raw: str) -> str:
    """Return a cleaned URL like "https://glowlab.co/products/serum", or raise ValueError."""
    text = raw.strip()
    if "://" not in text:
        text = "https://" + text

    parts = urlsplit(text)
    if parts.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only http and https links are supported.")
    if parts.username or parts.password:
        raise ValueError("Links with a username or password aren't supported.")

    host = (parts.hostname or "").rstrip(".")
    try:
        host = host.encode("idna").decode("ascii")  # bücher.de -> xn--bcher-kva.de
    except UnicodeError as error:
        raise ValueError("That doesn't look like a website address.") from error
    if not _DOMAIN.match(host):
        raise ValueError("That doesn't look like a website address.")

    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme.lower()}://{host}{parts.path}{query}"  # fragment (#...) dropped


def store_domain(url: str) -> str:
    """The domain to compare stores by: "https://www.GlowLab.co/x" -> "glowlab.co"."""
    host = urlsplit(normalize_store_url(url)).hostname or ""
    return host.removeprefix("www.")
