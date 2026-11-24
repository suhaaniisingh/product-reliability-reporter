"""Turn signal results into an explainable trust score.

Every store starts at a neutral 50 ("no evidence either way"). Each rule adds or
subtracts points and records a reason, so the score is always the sum of the
reasons shown to the user: nothing is hidden. Weights were approved on
2026-11-24 (docs/DECISIONS.md). They're judgement calls until Phase 3 measures
them against labelled stores; this has the same shape as logistic regression (a
starting value plus a weight per signal), so a learned model can be compared
like for like.

The scorer only reads signal results. It never fetches anything itself.
"""

from app.schemas import Confidence, Reason, StoreUrlSource, TrustScore
from app.signals.base import SignalResult, SignalStatus
from app.signals.domain_age import describe_age
from app.signals.safe_browsing import THREAT_WORDS

START = 50
SAFE_BROWSING_CAP = 10
EXPECTED_SIGNALS = ("domain_age", "safe_browsing", "store_pages", "shopify", "popularity")


def _age_points(days: int) -> tuple[int, str]:
    age = describe_age(days)
    if days < 30:
        return -20, f"Domain registered only {age} ago"
    if days < 180:
        return -10, f"Domain registered recently ({age} ago)"
    if days < 730:
        return 0, f"Domain registered {age} ago"
    if days < 1825:
        return 10, f"Domain registered {age} ago"
    return 15, f"Domain registered {age} ago"


def _label(score: int) -> str:
    if score >= 70:
        return "Higher trust"
    if score >= 40:
        return "Mixed signals"
    return "Lower trust"


def score_signals(signals: list[SignalResult], store_source: StoreUrlSource) -> TrustScore:
    ok = {s.name: s.value or {} for s in signals if s.status is SignalStatus.OK}
    reasons: list[Reason] = []
    cap: int | None = None

    def add(points: int, text: str, signal: str) -> None:
        reasons.append(Reason(points=points, text=text, signal=signal))

    if "safe_browsing" in ok:
        sb = ok["safe_browsing"]
        if sb.get("flagged"):
            cap = SAFE_BROWSING_CAP
            kinds = " and ".join(THREAT_WORDS.get(t, t.lower()) for t in sb.get("threat_types", []))
            reasons.append(Reason(points=0, cap=cap, text=f"Google Safe Browsing lists this site as suspected unsafe ({kinds})", signal="safe_browsing"))
        else:
            add(0, "Not on Google Safe Browsing's list of unsafe sites", "safe_browsing")

    if "domain_age" in ok:
        add(*_age_points(ok["domain_age"]["age_days"]), "domain_age")

    if "popularity" in ok:
        rank = ok["popularity"].get("rank")
        if rank is not None and rank <= 10_000:
            add(15, f"Among the world's 10,000 most-visited sites (rank {rank:,})", "popularity")
        elif rank is not None and rank <= 50_000:
            add(10, f"Among the world's 50,000 most-visited sites (rank {rank:,})", "popularity")
        elif rank is not None:
            add(5, f"Among the world's 100,000 most-visited sites (rank {rank:,})", "popularity")
        else:
            add(0, "Not among the 100,000 most-visited sites (normal for small shops)", "popularity")

    if "store_pages" in ok:
        pages = ok["store_pages"]
        if pages.get("return_policy"):
            add(5, "Has a return or refund policy", "store_pages")
        else:
            add(-10, "No return or refund policy found", "store_pages")
        if pages.get("contact_email") or pages.get("contact_phone"):
            add(5, "Working contact email or phone number found", "store_pages")
        else:
            add(-10, "No working contact email or phone number found", "store_pages")

    if "shopify" in ok and ok["shopify"].get("shopify"):
        add(0, "Built on Shopify (context only: common for honest and quickly-made stores alike)", "shopify")

    # Combination: newness alone is only a mild warning (honest shops launch all the
    # time); new *and* impossible to contact *and* no returns is a much stronger one.
    if "domain_age" in ok and "store_pages" in ok:
        pages = ok["store_pages"]
        if (
            ok["domain_age"]["age_days"] < 90
            and not pages.get("return_policy")
            and not (pages.get("contact_email") or pages.get("contact_phone"))
        ):
            add(-10, "New store with no return policy and no way to contact it", "combination")

    for s in signals:
        if s.status is not SignalStatus.OK:
            add(0, f"{s.label} couldn't be checked", s.name)

    score = max(0, min(100, START + sum(r.points for r in reasons)))
    if cap is not None:
        score = min(score, cap)

    not_ok = {s.name for s in signals if s.status is not SignalStatus.OK}
    if len(not_ok) >= 2 or "safe_browsing" in not_ok:
        confidence = Confidence.LOW
    elif len(not_ok) == 1:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.HIGH

    notes: list[str] = []
    if store_source is StoreUrlSource.GUESSED_FROM_BRAND:
        if confidence is Confidence.HIGH:
            confidence = Confidence.MEDIUM
        notes.append("This checks the brand's official site, guessed from its name. The video may link to a different store.")

    return TrustScore(score=score, label=_label(score), confidence=confidence, reasons=reasons, notes=notes)
