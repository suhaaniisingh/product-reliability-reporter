"""Deterministic checks on the LLM's answer before any client sees it.

The model is good at reading messy captions but can still return a link page, a
domain that isn't in the caption, or an invented domain. Each rule below is plain
code, so it's testable, explainable, and doesn't depend on the prompt being followed.
"""

import re
from dataclasses import dataclass, field

from app.extraction.base import LLMExtraction
from app.extraction.domain_check import DomainResolver
from app.extraction.store_url import normalize_store_url, store_domain
from app.schemas import Confidence, Extraction, StoreUrlSource

# Link-in-bio pages and social/media sites: never the store itself.
NOT_A_STORE_DOMAINS = {
    "linktr.ee", "beacons.ai", "stan.store", "linkin.bio", "lnk.bio", "bio.link", "campsite.bio",
    "solo.to", "tap.bio", "snipfeed.co", "komi.io", "msha.ke", "hoo.be",
    "tiktok.com", "instagram.com", "facebook.com", "youtube.com", "youtu.be", "x.com", "twitter.com",
    "pinterest.com", "snapchat.com", "threads.net", "spotify.com", "open.spotify.com", "music.apple.com",
}


@dataclass
class _Draft:
    """Mutable working copy of the result while rules run."""

    llm: LLMExtraction
    store_url: str | None
    source: StoreUrlSource
    confidence: Confidence
    notes: list[str] = field(default_factory=list)

    def drop_store(self, reason: str) -> None:
        self.store_url, self.source, self.confidence = None, StoreUrlSource.NONE, Confidence.LOW
        self.notes.append(reason)


def _is_not_a_store(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in NOT_A_STORE_DOMAINS)


# Words stores add around their name in a domain: cozyknitco.com, sunveilshop.com, getglow.com.
_DOMAIN_SUFFIXES = ("official", "online", "store", "shop", "brand", "hq", "co", "us")
_DOMAIN_PREFIXES = ("shop", "get", "try", "buy", "the")
# Topic hashtags that must never become a brand, even if a domain happens to match.
_GENERIC_HASHTAGS = {
    "ad", "sponsored", "gifted", "fyp", "foryou", "foryoupage", "viral", "trending", "sale", "shop", "shopping",
    "skincare", "makeup", "beauty", "fashion", "ootd", "style", "home", "fitness", "tiktokmademebuyit",
}


def _domain_names(domain: str) -> set[str]:
    """Names a store's domain could be "about": cozyknitco.com -> {cozyknitco, cozyknit}."""
    names = set()
    for label in domain.split(".")[:-1]:  # every label except the TLD
        names.add(label)
        for suffix in _DOMAIN_SUFFIXES:
            if label.endswith(suffix) and len(label) > len(suffix) + 2:
                names.add(label.removesuffix(suffix))
        for prefix in _DOMAIN_PREFIXES:
            if label.startswith(prefix) and len(label) > len(prefix) + 2:
                names.add(label.removeprefix(prefix))
    return {n.replace("-", "") for n in names}


def brand_from_hashtag(caption: str, store_url: str) -> str | None:
    """A hashtag that matches the store's domain name is the brand: #cozyknit + cozyknitco.com.

    Deterministic backstop for brand names that also read like ordinary words
    ("cozy knit"), which the model tends to treat as topic tags.
    """
    names = _domain_names(store_domain(store_url))
    for tag in re.findall(r"#(\w+)", caption):
        if len(tag) >= 3 and tag.lower() not in _GENERIC_HASHTAGS and tag.lower() in names:
            return tag
    return None


def _appears_in(domain: str, caption: str) -> bool:
    text = caption.lower()
    try:
        unicode_domain = domain.encode("ascii").decode("idna")  # xn--bcher-kva.de -> bücher.de
    except UnicodeError:
        unicode_domain = domain
    return domain in text or unicode_domain in text


async def apply_rules(
    llm: LLMExtraction,
    caption: str,
    resolver: DomainResolver,
    user_store_url: str | None = None,
) -> Extraction:
    draft = _Draft(
        llm=llm,
        store_url=None,
        source=StoreUrlSource(llm.store_url_source),
        confidence=Confidence(llm.confidence),
        notes=[llm.notes] if llm.notes else [],
    )

    # 1. A store_url must be a real-looking web address.
    if llm.store_url is not None:
        try:
            draft.store_url = normalize_store_url(llm.store_url)
        except ValueError:
            draft.drop_store(f'"{llm.store_url}" isn\'t a valid web address, so it was ignored.')
    if draft.store_url is None and draft.source is not StoreUrlSource.NONE:
        draft.drop_store("No usable store link was found.")

    if draft.store_url is not None:
        domain = store_domain(draft.store_url)

        # 2. Link pages and social sites aren't stores, whatever the model said.
        if _is_not_a_store(domain):
            draft.drop_store(f"{domain} is a link page or social site, not a store. Open it to find the actual store.")

        # 3. "In the caption" must be literally true.
        elif draft.source is StoreUrlSource.IN_CAPTION and not _appears_in(domain, caption):
            draft.drop_store("A store link was suggested that isn't in the caption, so it was discarded.")

        # 4. A guessed domain must at least exist, and is never more than medium confidence.
        elif draft.source is StoreUrlSource.GUESSED_FROM_BRAND:
            exists = await resolver.exists(domain)
            if exists is False:
                draft.drop_store(f"The guessed store {domain} doesn't exist, so it was discarded.")
            else:
                if draft.confidence is Confidence.HIGH:
                    draft.confidence = Confidence.MEDIUM
                draft.notes.append(
                    f"{domain} is a guess based on the brand name, not a link from the video."
                    + (" Its existence couldn't be verified." if exists is None else "")
                )

    # 5. No store means low confidence, whatever the model reported.
    if draft.store_url is None:
        draft.source, draft.confidence = StoreUrlSource.NONE, Confidence.LOW

    # 6. The user's own link wins. Flag it if the caption points somewhere else.
    if user_store_url is not None:
        if draft.store_url is not None and store_domain(draft.store_url) != store_domain(user_store_url):
            draft.notes.append(
                f"The caption points to {store_domain(draft.store_url)}, but you provided "
                f"{store_domain(user_store_url)}. Checking the one you provided."
            )
        draft.store_url, draft.source, draft.confidence = user_store_url, StoreUrlSource.USER_PROVIDED, Confidence.HIGH

    # 7. A hashtag matching the store's domain name is the brand, if the model found none.
    brand = llm.brand
    if brand is None and draft.store_url is not None:
        brand = brand_from_hashtag(caption, draft.store_url)
        if brand is not None:
            draft.notes.append(f"Brand taken from #{brand}, which matches the store's web address.")

    return Extraction(
        product=llm.product,
        brand=brand,
        store_url=draft.store_url,
        store_url_source=draft.source,
        mentions_link_in_bio=llm.mentions_link_in_bio,
        discount_code=llm.discount_code,
        confidence=draft.confidence,
        notes=" ".join(draft.notes),
    )
