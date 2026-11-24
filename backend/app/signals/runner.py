"""Runs all trust signals at the same time, each with its own time limit.

This is the only place that handles timing, timeouts and crashes, so every
signal module stays small and every result has the same shape. The runner never
raises: a broken or slow signal becomes a `failed` / `timeout` result, and the
other signals are unaffected.
"""

import asyncio
import logging
import time

from app.signals.base import Signal, SignalResult, SignalStatus, SignalUnavailable, Store

logger = logging.getLogger(__name__)


async def _run_one(signal: Signal, store: Store) -> SignalResult:
    started = time.perf_counter()

    def result(status: SignalStatus, explanation: str, value: dict | None = None, source: str | None = None) -> SignalResult:
        return SignalResult(
            name=signal.name, label=signal.label, status=status, value=value, explanation=explanation,
            source=source, duration_ms=round((time.perf_counter() - started) * 1000),
        )

    try:
        async with asyncio.timeout(signal.timeout_seconds):
            finding = await signal.check(store)
    except SignalUnavailable as reason:
        return result(SignalStatus.FAILED, f"{signal.label}: {reason}")
    except TimeoutError:
        logger.warning("signal %s timed out after %ss for %s", signal.name, signal.timeout_seconds, store.domain)
        return result(SignalStatus.TIMEOUT, f"{signal.label}: the check took too long, so it was skipped.")
    except Exception:
        # Deliberately broad: whatever goes wrong inside one signal must not break the scan.
        logger.exception("signal %s failed for %s", signal.name, store.domain)
        return result(SignalStatus.FAILED, f"{signal.label}: couldn't be checked right now.")

    return result(SignalStatus.OK, finding.explanation, value=finding.value, source=finding.source)


async def run_signals(signals: list[Signal], store: Store) -> list[SignalResult]:
    """All signals concurrently; results come back in the same order as `signals`."""
    return list(await asyncio.gather(*(_run_one(s, store) for s in signals)))
