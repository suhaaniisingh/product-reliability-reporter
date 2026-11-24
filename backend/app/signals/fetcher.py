"""Fetch public store pages safely (SSRF protection), politely and within limits.

The server fetches whatever store a user pastes, so a hostile user could try to
make it read private addresses: the cloud metadata service (169.254.169.254),
localhost, or the hosting provider's internal network. Rejecting IPs in the
pasted text isn't enough, because any public-looking domain can *point to* a
private address. So every request here:

1. resolves the host and requires **every** address to be public;
2. connects to exactly the address it checked (the URL uses the IP, while the
   Host header and TLS name stay the real domain, so HTTPS certificates are
   still verified against it). This defeats DNS rebinding, where a name answers
   "public" when checked and "private" a moment later when connected;
3. follows redirects itself (at most 3), re-checking each hop;
4. allows only http/https on the standard ports, 5 s and 2 MB per page;
5. identifies itself honestly and respects robots.txt.

See docs/DECISIONS.md (2026-11-24, SSRF protection; fetcher details).
"""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "SocialCommerceReliabilityReporter/0.1"
ROBOTS_AGENT = "SocialCommerceReliabilityReporter"
MAX_BYTES = 2_000_000
PAGE_TIMEOUT_SECONDS = 5.0
MAX_REDIRECTS = 3
_TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")


class FetchBlocked(Exception):
    """The request was refused on purpose (unsafe address, bad URL, too many redirects).
    The message is safe to show to users."""


class FetchFailed(Exception):
    """The site couldn't be reached or answered with an error."""


@dataclass(frozen=True)
class FetchedPage:
    url: str  # final URL after redirects
    status: int
    content_type: str
    text: str  # empty for non-text responses
    truncated: bool  # True if the body was cut at MAX_BYTES


class HostResolver(Protocol):
    async def resolve(self, host: str) -> list[str]: ...


class SystemResolver:
    async def resolve(self, host: str) -> list[str]:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
        return sorted({info[4][0] for info in infos})


def is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped  # ::ffff:10.0.0.1 is really 10.0.0.1
    # is_global is False for private, loopback, link-local (incl. 169.254.169.254),
    # carrier-grade NAT (100.64/10), reserved and unspecified addresses.
    return ip.is_global and not ip.is_multicast


def _check_url(url: str) -> tuple[str, str, str]:
    """Returns (scheme, host, path_and_query) or raises FetchBlocked."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise FetchBlocked("Only http and https links can be checked.")
    if parts.username or parts.password:
        raise FetchBlocked("Links with a username or password can't be checked.")
    try:
        port = parts.port
    except ValueError as error:
        raise FetchBlocked("That link has an invalid port.") from error
    if port not in (None, 80 if scheme == "http" else 443):
        raise FetchBlocked("Only standard web ports can be checked.")
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise FetchBlocked("That link has no website address.")
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return scheme, host, path


class SafeFetcher:
    def __init__(
        self,
        resolver: HostResolver | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        page_timeout: float = PAGE_TIMEOUT_SECONDS,
    ) -> None:
        """`resolver` and `transport` are injectable so tests run offline."""
        self._resolver = resolver or SystemResolver()
        self._page_timeout = page_timeout
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(page_timeout),
            follow_redirects=False,  # we follow redirects ourselves, re-checking each hop
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"},
        )
        self._robots: dict[str, RobotFileParser | bool] = {}  # per host: parser, or True/False = allow/deny all

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _public_address(self, host: str) -> str:
        try:
            addresses = await self._resolver.resolve(host)
        except OSError as error:
            raise FetchFailed(f"{host} couldn't be found.") from error
        if not addresses:
            raise FetchFailed(f"{host} couldn't be found.")
        if not all(is_public_ip(a) for a in addresses):
            raise FetchBlocked(f"{host} points to a private or internal address, so it wasn't visited.")
        return addresses[0]

    async def _get_once(self, url: str) -> tuple[httpx.Response, bytes, bool]:
        scheme, host, path = _check_url(url)
        address = await self._public_address(host)
        ip_host = f"[{address}]" if ":" in address else address
        extensions = {"sni_hostname": host} if scheme == "https" else {}
        request = self._client.build_request(
            "GET", f"{scheme}://{ip_host}{path}", headers={"Host": host}, extensions=extensions
        )
        response = await self._client.send(request, stream=True)
        try:
            body, truncated = b"", False
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if not response.is_redirect and content_type in _TEXT_TYPES:
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        body, truncated = body[:MAX_BYTES], True
                        break
        finally:
            await response.aclose()
        return response, body, truncated

    async def fetch(self, url: str) -> FetchedPage:
        """GET a public page, following up to MAX_REDIRECTS safe redirects."""
        try:
            async with asyncio.timeout(self._page_timeout):
                current = url
                for _ in range(MAX_REDIRECTS + 1):
                    response, body, truncated = await self._get_once(current)
                    if response.is_redirect and "location" in response.headers:
                        current = urljoin(current, response.headers["location"])
                        continue
                    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    return FetchedPage(
                        url=current,
                        status=response.status_code,
                        content_type=content_type,
                        text=body.decode(response.encoding or "utf-8", errors="replace"),
                        truncated=truncated,
                    )
                raise FetchBlocked("The page redirected too many times.")
        except TimeoutError as error:
            raise FetchFailed("The page took too long to load.") from error
        except httpx.HTTPError as error:
            raise FetchFailed("The site couldn't be reached.") from error

    async def allowed_by_robots(self, url: str) -> bool:
        """Does the site's robots.txt allow us to fetch this URL? Cached per host.

        Like major crawlers: a missing robots.txt (4xx) allows everything; a server
        error or unreachable robots.txt disallows everything, to be safe."""
        scheme, host, _ = _check_url(url)
        if host not in self._robots:
            try:
                page = await self.fetch(f"{scheme}://{host}/robots.txt")
                if page.status == 200:
                    parser = RobotFileParser()
                    parser.parse(page.text.splitlines())
                    self._robots[host] = parser
                else:
                    self._robots[host] = page.status < 500
            except (FetchBlocked, FetchFailed):
                self._robots[host] = False
        rules = self._robots[host]
        return rules if isinstance(rules, bool) else rules.can_fetch(ROBOTS_AGENT, url)
