"""DnsResolver: its three answers, with the system DNS call faked (no network)."""

import asyncio
import socket

import pytest

from app.extraction.domain_check import DnsResolver

pytestmark = pytest.mark.anyio


def fake_getaddrinfo(error: Exception | None):
    async def getaddrinfo(*args: object, **kwargs: object) -> list:
        if error is not None:
            raise error
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443))]

    return getaddrinfo


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (None, True),
        (socket.gaierror(socket.EAI_NONAME, "nodename nor servname provided"), False),  # doesn't exist
        (socket.gaierror(socket.EAI_AGAIN, "temporary failure"), None),  # DNS trouble: can't tell
        (OSError("network unreachable"), None),
        (TimeoutError(), None),
    ],
)
async def test_dns_resolver(monkeypatch: pytest.MonkeyPatch, error: Exception | None, expected: bool | None) -> None:
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo(error))

    assert await DnsResolver().exists("glowlab.co") is expected
