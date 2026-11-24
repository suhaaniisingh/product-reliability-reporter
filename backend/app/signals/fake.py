"""A stand-in signal for tests: no network, configurable result, delay or crash."""

import asyncio

from app.signals.base import Finding, Store


class FakeSignal:
    def __init__(
        self,
        name: str = "fake",
        label: str = "Fake check",
        value: dict | None = None,
        explanation: str = "Fake finding.",
        delay: float = 0.0,
        error: Exception | None = None,
        timeout_seconds: float = 1.0,
    ) -> None:
        self.name, self.label, self.timeout_seconds = name, label, timeout_seconds
        self.value = value if value is not None else {"ok": True}
        self.explanation, self.delay, self.error = explanation, delay, error
        self.calls: list[Store] = []

    async def check(self, store: Store) -> Finding:
        self.calls.append(store)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return Finding(value=self.value, explanation=self.explanation)
