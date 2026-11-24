"""Deterministic checks on the LLM's answer before any client sees it.

The model is good at reading messy captions but can still return a link page, a
domain that isn't in the caption, or an invented domain. Each rule below is plain
code, so it's testable, explainable, and doesn't depend on the prompt being followed.
"""

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
        confidence=llm.confidence,
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

    return Extraction(
        product=llm.product,
        brand=llm.brand,
        store_url=draft.store_url,
        store_url_source=draft.source,
        mentions_link_in_bio=llm.mentions_link_in_bio,
        discount_code=llm.discount_code,
        confidence=draft.confidence,
        notes=" ".join(draft.notes),
    )
