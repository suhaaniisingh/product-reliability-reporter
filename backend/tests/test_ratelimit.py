"""The in-house rate limiter, driven by a fake clock (no real waiting)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.ratelimit import Limits, RateLimiter, client_ip


class FakeTime:
    def __init__(self) -> None:
        self.monotonic = 1000.0
        self.utc = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)

    def advance(self, seconds: float) -> None:
        self.monotonic += seconds
        self.utc += timedelta(seconds=seconds)


@pytest.fixture
def t() -> FakeTime:
    return FakeTime()


def limiter(t: FakeTime, **kwargs) -> RateLimiter:
    return RateLimiter(clock=lambda: t.monotonic, now_utc=lambda: t.utc, **kwargs)


def test_a_burst_up_to_the_minute_limit_is_allowed_then_refused(t: FakeTime) -> None:
    rl = limiter(t)

    assert all(rl.check("1.2.3.4", "caption").allowed for _ in range(10))
    refused = rl.check("1.2.3.4", "caption")

    assert (refused.allowed, refused.status) == (False, 429)
    assert refused.retry_after == 6  # 10 tokens per 60 s: one token every 6 s


def test_tokens_refill_steadily(t: FakeTime) -> None:
    rl = limiter(t)
    for _ in range(10):
        rl.check("1.2.3.4", "caption")

    t.advance(6)
    assert rl.check("1.2.3.4", "caption").allowed  # one token back after 6 s
    assert not rl.check("1.2.3.4", "caption").allowed


def test_the_daily_limit_holds_even_when_spread_out(t: FakeTime) -> None:
    rl = limiter(t)
    for _ in range(50):
        assert rl.check("1.2.3.4", "caption").allowed
        t.advance(10)  # slow enough to never hit the per-minute limit

    refused = rl.check("1.2.3.4", "caption")
    assert (refused.status, refused.message) == (429, "You've reached today's scan limit. Please try again tomorrow.")


def test_a_new_day_resets_the_daily_limit(t: FakeTime) -> None:
    rl = limiter(t, limits={"caption": Limits(per_minute=100, per_day=2), "store": Limits(100, 2)})
    rl.check("1.2.3.4", "caption")
    rl.check("1.2.3.4", "caption")
    assert not rl.check("1.2.3.4", "caption").allowed

    t.advance(12 * 3600)  # past midnight UTC

    assert rl.check("1.2.3.4", "caption").allowed


def test_visitors_and_scan_kinds_have_separate_limits(t: FakeTime) -> None:
    rl = limiter(t)
    for _ in range(10):
        rl.check("1.2.3.4", "caption")

    assert not rl.check("1.2.3.4", "caption").allowed
    assert rl.check("5.6.7.8", "caption").allowed  # another visitor
    assert rl.check("1.2.3.4", "store").allowed  # store-link scans have their own, looser limits


def test_store_link_scans_allow_30_per_minute(t: FakeTime) -> None:
    rl = limiter(t)

    assert all(rl.check("1.2.3.4", "store").allowed for _ in range(30))
    assert not rl.check("1.2.3.4", "store").allowed


def test_the_site_wide_caption_budget_applies_across_visitors(t: FakeTime) -> None:
    rl = limiter(t, global_caption_per_day=3)
    for ip in ["1.1.1.1", "2.2.2.2", "3.3.3.3"]:
        assert rl.check(ip, "caption").allowed

    refused = rl.check("4.4.4.4", "caption")  # a fresh visitor, but the site budget is used up

    assert (refused.allowed, refused.status) == (False, 503)
    assert "pasting its link" in refused.message  # store-link scans are still possible...
    assert rl.check("4.4.4.4", "store").allowed  # ...and work
    assert refused.retry_after == 12 * 3600  # until midnight UTC


def test_a_refused_scan_uses_up_nothing(t: FakeTime) -> None:
    rl = limiter(t, limits={"caption": Limits(per_minute=1, per_day=5), "store": Limits(1, 5)})
    rl.check("1.2.3.4", "caption")
    for _ in range(20):
        assert not rl.check("1.2.3.4", "caption").allowed  # refused attempts...

    t.advance(60)
    assert rl.check("1.2.3.4", "caption").allowed  # ...didn't eat into the daily 5


@pytest.mark.parametrize(
    ("header", "peer", "hops", "expected"),
    [
        (None, "10.0.0.1", 0, "10.0.0.1"),  # local development: no proxy
        ("6.6.6.6", "10.0.0.1", 0, "10.0.0.1"),  # untrusted header is ignored
        ("203.0.113.7", "169.254.1.1", 1, "203.0.113.7"),  # behind one proxy: it set the real IP
        ("6.6.6.6, 203.0.113.7", "169.254.1.1", 1, "203.0.113.7"),  # a spoofed entry in front is ignored
        ("", "169.254.1.1", 1, "169.254.1.1"),
    ],
)
def test_client_ip(header: str | None, peer: str, hops: int, expected: str) -> None:
    assert client_ip(header, peer, hops) == expected


def test_the_api_returns_429_with_retry_after(client: TestClient) -> None:
    for _ in range(30):
        assert client.post("/api/scan", json={"store_url": "glowlab.co"}).status_code == 200

    response = client.post("/api/scan", json={"store_url": "glowlab.co"})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "2"  # 30 tokens per 60 s: one every 2 s
    assert "Too many scans" in response.json()["detail"]


def test_spoofing_x_forwarded_for_doesnt_bypass_the_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    for i in range(30):
        client.post("/api/scan", json={"store_url": "glowlab.co"}, headers={"X-Forwarded-For": f"9.9.9.{i}, 203.0.113.7"})

    response = client.post("/api/scan", json={"store_url": "glowlab.co"}, headers={"X-Forwarded-For": "9.9.9.99, 203.0.113.7"})

    assert response.status_code == 429  # still one visitor: 203.0.113.7
