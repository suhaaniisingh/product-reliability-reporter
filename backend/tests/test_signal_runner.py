"""run_signals: concurrency, per-signal time limits, and crash isolation (all offline)."""

import time

import pytest

from app.signals.base import SignalStatus, Store
from app.signals.fake import FakeSignal
from app.signals.runner import run_signals

pytestmark = pytest.mark.anyio

STORE = Store.from_url("https://www.glowlab.co/products/serum")


async def test_ok_signal_returns_its_finding() -> None:
    [result] = await run_signals([FakeSignal(name="age", label="Domain age", value={"age_days": 21}, explanation="Registered 21 days ago.")], STORE)

    assert (result.name, result.status, result.value, result.explanation) == ("age", SignalStatus.OK, {"age_days": 21}, "Registered 21 days ago.")
    assert result.duration_ms >= 0


async def test_signals_receive_the_store_domain() -> None:
    signal = FakeSignal()

    await run_signals([signal], STORE)

    assert signal.calls == [Store(url="https://www.glowlab.co/products/serum", domain="glowlab.co")]


async def test_a_crashing_signal_fails_alone() -> None:
    results = await run_signals(
        [FakeSignal(name="a"), FakeSignal(name="b", label="Blocklist", error=RuntimeError("API down")), FakeSignal(name="c")], STORE
    )

    assert [r.status for r in results] == [SignalStatus.OK, SignalStatus.FAILED, SignalStatus.OK]
    assert results[1].value is None
    assert results[1].explanation == "Blocklist: couldn't be checked right now."
    assert "API down" not in results[1].explanation  # internal errors are logged, not shown to users


async def test_a_slow_signal_times_out_without_holding_up_the_others() -> None:
    started = time.perf_counter()

    results = await run_signals(
        [FakeSignal(name="slow", delay=5.0, timeout_seconds=0.2), FakeSignal(name="fast", delay=0.05)], STORE
    )

    assert [r.status for r in results] == [SignalStatus.TIMEOUT, SignalStatus.OK]
    assert time.perf_counter() - started < 1.0  # gave up at the 0.2 s limit, didn't wait 5 s


async def test_signals_run_concurrently() -> None:
    started = time.perf_counter()

    results = await run_signals([FakeSignal(name=f"s{i}", delay=0.3) for i in range(4)], STORE)

    assert all(r.status is SignalStatus.OK for r in results)
    assert time.perf_counter() - started < 0.8  # one after another would take 1.2 s


async def test_results_keep_the_input_order() -> None:
    results = await run_signals([FakeSignal(name="first", delay=0.2), FakeSignal(name="second", delay=0.0)], STORE)

    assert [r.name for r in results] == ["first", "second"]


async def test_no_signals_gives_no_results() -> None:
    assert await run_signals([], STORE) == []
