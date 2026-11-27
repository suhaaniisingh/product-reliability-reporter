"""The shape every trust signal shares.

Each signal is an independent module with the same small interface: given the
store, look one thing up and return a Finding (a value plus a plain-English
explanation). Signals never deal with timeouts, crashes or timing themselves;
the runner (runner.py) does that in one place, so one failing signal can never
break a scan and every signal reports its outcome the same way.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel

from app.extraction.store_url import store_domain


@dataclass(frozen=True)
class Store:
    """What every signal receives: the store's URL and the domain to look up."""

    url: str
    domain: str

    @classmethod
    def from_url(cls, url: str) -> Store:
        return cls(url=url, domain=store_domain(url))


@dataclass(frozen=True)
class Finding:
    """What a signal returns when its check worked.

    `value` holds the raw facts the scorer reads (e.g. {"age_days": 21}); each
    signal documents its own keys. `explanation` is shown to users, so it states
    facts ("Domain registered 21 days ago"), never accusations.
    """

    value: dict[str, Any]
    explanation: str
    source: str | None = None  # e.g. "Advisory provided by Google" where terms require attribution


class SignalUnavailable(Exception):
    """Raised by a signal when its check can't be done, with a reason that's safe to
    show users (e.g. "No public registration data for .xyz domains."). Unlike an
    unexpected crash, the message is displayed as-is."""


class SignalStatus(StrEnum):
    OK = "ok"  # the check ran and produced a finding
    FAILED = "failed"  # the check crashed or its data source returned an error
    TIMEOUT = "timeout"  # the check took longer than its time limit


class SignalResult(BaseModel):
    """One signal's outcome, as returned by the API and read by the scorer."""

    name: str  # stable key, e.g. "domain_age"
    label: str  # human-readable, e.g. "Domain age"
    status: SignalStatus
    value: dict[str, Any] | None  # None unless status is ok
    explanation: str
    source: str | None
    duration_ms: int


class Signal(Protocol):
    name: str
    label: str
    timeout_seconds: float

    async def check(self, store: Store) -> Finding: ...
