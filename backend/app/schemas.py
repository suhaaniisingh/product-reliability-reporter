"""The API's data contract: the shapes of requests and reports.

Pydantic models do two jobs at once: they validate incoming JSON (rejecting bad
input with a 422 before our code runs) and they describe outgoing JSON (which
also appears in the auto-generated docs at /docs).
"""

from enum import StrEnum

from pydantic import BaseModel, HttpUrl


class Status(StrEnum):
    """How a single signal looks. Kept deliberately small (see CLAUDE.md, report contract)."""

    GOOD = "good"
    WARNING = "warning"
    DANGER = "danger"
    UNKNOWN = "unknown"  # "Not enough information" is a valid answer.


class Signal(BaseModel):
    """One piece of evidence: a status plus a plain-English, fact-based explanation."""

    status: Status
    detail: str


class CheckRequest(BaseModel):
    """What the client sends: the URL to check.

    HttpUrl only accepts http/https URLs with a host, so input like
    "hello" or "ftp://x.com" is rejected before reaching our code.
    """

    url: HttpUrl


class Report(BaseModel):
    """The trust report returned to every client (web page, extension, ...).

    `signals` is keyed by signal name (e.g. "business_age") so signal modules
    can be added or removed without changing this model.
    """

    store_url: str
    signals: dict[str, Signal]
