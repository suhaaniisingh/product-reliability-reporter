"""Rate limiting, written in-house (docs/DECISIONS.md, 2026-11-24).

Why: the deployed site is public, every caption scan costs real money (Claude),
and every scan makes our server visit other websites. Limits per visitor (IP):

- per minute: a **token bucket**. Each visitor has a bucket of N tokens; a scan
  takes one; tokens refill steadily (N per minute). That allows a short burst
  (N quick scans) while holding the long-run average at N/minute. A fixed
  "N per calendar minute" counter would allow 2N in a few seconds around the
  minute boundary.
- per day: a plain counter that resets at midnight UTC.
- site-wide: a daily budget of caption scans across everyone, so many visitors
  (or a botnet) each staying under their own limit still can't run up the bill.

State lives in this process's memory. That's correct here because Cloud Run is
configured with at most one instance; several instances would need a shared
store such as Redis (Phase 5).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

ScanKind = Literal["caption", "store"]


@dataclass(frozen=True)
class Limits:
    per_minute: int
    per_day: int


DEFAULT_LIMITS: dict[str, Limits] = {
    "caption": Limits(per_minute=10, per_day=50),  # these call Claude
    "store": Limits(per_minute=30, per_day=200),  # these only visit websites
}
DEFAULT_GLOBAL_CAPTION_PER_DAY = 500  # about $0.90/day at ~$0.0018 per caption scan


@dataclass
class Decision:
    allowed: bool
    status: int = 200  # 429 = this visitor is over a limit; 503 = the site-wide budget is used up
    message: str = ""
    retry_after: int = 0  # seconds


class TokenBucket:
    def __init__(self, capacity: int, per_seconds: float, now: float) -> None:
        self.capacity = capacity
        self.rate = capacity / per_seconds  # tokens added per second
        self.tokens = float(capacity)
        self.updated = now

    def _refill(self, now: float) -> None:
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now

    def seconds_until_token(self, now: float) -> float:
        self._refill(now)
        return 0.0 if self.tokens >= 1 else (1 - self.tokens) / self.rate

    def take(self, now: float) -> None:
        self._refill(now)
        self.tokens -= 1


class RateLimiter:
    def __init__(
        self,
        limits: dict[str, Limits] | None = None,
        global_caption_per_day: int = DEFAULT_GLOBAL_CAPTION_PER_DAY,
        clock: Callable[[], float] = time.monotonic,
        now_utc: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """`clock` and `now_utc` are injectable so tests control time."""
        self.limits = limits or DEFAULT_LIMITS
        self.global_caption_per_day = global_caption_per_day
        self._clock, self._now_utc = clock, now_utc
        self._buckets: dict[tuple[str, str], TokenBucket] = {}
        self._daily: dict[tuple[str, str], int] = {}
        self._global_caption = 0
        self._day: date | None = None

    def _seconds_to_midnight(self) -> int:
        now = self._now_utc()
        midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), UTC)
        return max(1, int((midnight - now).total_seconds()))

    def _roll_day(self) -> None:
        today = self._now_utc().date()
        if today != self._day:  # new day: daily counters start again, idle buckets are dropped
            self._day, self._daily, self._global_caption = today, {}, 0
            now = self._clock()
            self._buckets = {k: b for k, b in self._buckets.items() if now - b.updated < 3600}

    def check(self, client: str, kind: ScanKind) -> Decision:
        """Decide, and only if allowed, record the scan. Checks everything first and
        then commits, so a refused scan never uses up any limit."""
        self._roll_day()
        limits, now, key = self.limits[kind], self._clock(), (client, kind)

        if kind == "caption" and self._global_caption >= self.global_caption_per_day:
            return Decision(
                False, 503,
                "Caption scans are paused for today because the site's daily limit was reached. "
                "You can still check a store by pasting its link.",
                self._seconds_to_midnight(),
            )
        if self._daily.get(key, 0) >= limits.per_day:
            return Decision(False, 429, "You've reached today's scan limit. Please try again tomorrow.", self._seconds_to_midnight())
        bucket = self._buckets.get(key) or TokenBucket(limits.per_minute, 60.0, now)
        wait = bucket.seconds_until_token(now)
        if wait > 0:
            self._buckets[key] = bucket
            seconds = max(1, round(wait))
            return Decision(False, 429, f"Too many scans in a short time. Please wait {seconds} seconds.", seconds)

        bucket.take(now)
        self._buckets[key] = bucket
        self._daily[key] = self._daily.get(key, 0) + 1
        if kind == "caption":
            self._global_caption += 1
        return Decision(True)


def client_ip(forwarded_for: str | None, peer: str | None, trusted_proxy_hops: int) -> str:
    """Which IP to rate-limit.

    Behind a proxy (Cloud Run's front end), the TCP peer is the proxy, and the
    visitor's IP is in X-Forwarded-For. A visitor can put anything they like at the
    *start* of that header, so we count from the *end*: each trusted proxy appends
    exactly one entry. With 0 trusted hops (local development) the header is
    ignored entirely, because nobody is vouching for it.
    """
    if trusted_proxy_hops > 0 and forwarded_for:
        entries = [e.strip() for e in forwarded_for.split(",") if e.strip()]
        if len(entries) >= trusted_proxy_hops:
            return entries[-trusted_proxy_hops]
    return peer or "unknown"
