"""Does a domain exist? Used to catch invented domains when the LLM guesses a store.

Behind a small interface so tests use a fake and never touch the network.
"""

import asyncio
import socket
from typing import Protocol

DNS_TIMEOUT_SECONDS = 3.0


class DomainResolver(Protocol):
    async def exists(self, domain: str) -> bool | None:
        """True = resolves, False = definitely doesn't exist, None = couldn't tell."""
        ...


class DnsResolver:
    """Asks the system's DNS resolver for the domain's address.

    A domain that doesn't resolve can't be a working store, so it's a cheap way to
    catch most made-up guesses. It can't catch a guess that is real but wrong.
    """

    async def exists(self, domain: str) -> bool | None:
        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(loop.getaddrinfo(domain, 443, type=socket.SOCK_STREAM), DNS_TIMEOUT_SECONDS)
        except socket.gaierror as error:
            # EAI_NONAME = the name doesn't exist. Anything else (no network, server failure) = unknown.
            return False if error.errno == socket.EAI_NONAME else None
        except (TimeoutError, OSError):
            return None
        return True
