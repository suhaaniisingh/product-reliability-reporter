"""SafeFetcher: SSRF protection, redirects, limits and robots.txt, all offline.

A fake resolver decides what each hostname "resolves" to, and httpx's
MockTransport plays the websites, so no test touches the network.
"""

import asyncio
import inspect

import httpx
import pytest

from app.signals.fetcher import USER_AGENT, FetchBlocked, FetchFailed, SafeFetcher, is_public_ip

pytestmark = pytest.mark.anyio

PUBLIC = "93.184.215.14"


class FakeResolver:
    def __init__(self, table: dict[str, list[str]]) -> None:
        self.table = table

    async def resolve(self, host: str) -> list[str]:
        if host not in self.table:
            raise OSError("not found")
        return self.table[host]


def make_fetcher(sites: dict, dns: dict[str, list[str]] | None = None, **kwargs) -> tuple[SafeFetcher, list[httpx.Request]]:
    """`sites` maps (host, path) to an httpx.Response or a callable returning one."""
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        site = sites.get((request.headers["host"], request.url.raw_path.decode()))
        if site is None:
            return httpx.Response(404, text="not found", headers={"content-type": "text/plain"})
        return await site(request) if inspect.iscoroutinefunction(site) else site

    dns = dns if dns is not None else {host: [PUBLIC] for host, _ in sites}
    return SafeFetcher(resolver=FakeResolver(dns), transport=httpx.MockTransport(handler), **kwargs), seen


def html(body: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8"})


def redirect(location: str) -> httpx.Response:
    return httpx.Response(301, headers={"location": location})


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("93.184.215.14", True),
        ("2606:4700::6810:84e5", True),
        ("10.0.0.1", False),
        ("192.168.1.1", False),
        ("127.0.0.1", False),
        ("169.254.169.254", False),  # cloud metadata service
        ("100.64.0.1", False),  # carrier-grade NAT
        ("0.0.0.0", False),
        ("::1", False),
        ("fd00::1", False),
        ("::ffff:10.0.0.1", False),  # IPv4-mapped private address
        ("224.0.0.1", False),  # multicast
    ],
)
def test_is_public_ip(address: str, public: bool) -> None:
    assert is_public_ip(address) is public


async def test_fetches_a_public_page_by_pinned_ip_with_the_real_host_name() -> None:
    fetcher, seen = make_fetcher({("glowlab.co", "/"): html("<h1>Glow</h1>")})

    page = await fetcher.fetch("https://glowlab.co/")

    assert (page.status, page.text, page.url) == (200, "<h1>Glow</h1>", "https://glowlab.co/")
    request = seen[0]
    assert request.url.host == PUBLIC  # connected to the address we checked
    assert request.headers["host"] == "glowlab.co"  # ...while asking for the real site
    assert request.extensions["sni_hostname"] == "glowlab.co"  # TLS certificate checked against the real name
    assert request.headers["user-agent"] == USER_AGENT


@pytest.mark.parametrize("private", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1"])
async def test_a_domain_pointing_to_a_private_address_is_never_visited(private: str) -> None:
    fetcher, seen = make_fetcher({("evil-shop.com", "/"): html("secret")}, dns={"evil-shop.com": [private]})

    with pytest.raises(FetchBlocked, match="private or internal"):
        await fetcher.fetch("https://evil-shop.com/")
    assert seen == []


async def test_one_private_address_among_public_ones_is_enough_to_block() -> None:
    fetcher, seen = make_fetcher({("mixed.com", "/"): html("x")}, dns={"mixed.com": [PUBLIC, "10.0.0.5"]})

    with pytest.raises(FetchBlocked):
        await fetcher.fetch("https://mixed.com/")
    assert seen == []


async def test_a_redirect_to_a_private_address_is_blocked() -> None:
    fetcher, seen = make_fetcher(
        {("glowlab.co", "/"): redirect("http://metadata.internal/computeMetadata/v1/")},
        dns={"glowlab.co": [PUBLIC], "metadata.internal": ["169.254.169.254"]},
    )

    with pytest.raises(FetchBlocked):
        await fetcher.fetch("https://glowlab.co/")
    assert len(seen) == 1  # the first hop only; the metadata address was never contacted


async def test_relative_redirects_are_followed() -> None:
    fetcher, _ = make_fetcher({("glowlab.co", "/"): redirect("/home"), ("glowlab.co", "/home"): html("home")})

    page = await fetcher.fetch("https://glowlab.co/")

    assert (page.text, page.url) == ("home", "https://glowlab.co/home")


async def test_too_many_redirects_are_refused() -> None:
    fetcher, seen = make_fetcher({("loop.com", f"/{i}"): redirect(f"/{i + 1}") for i in range(10)})

    with pytest.raises(FetchBlocked, match="redirected too many times"):
        await fetcher.fetch("https://loop.com/0")
    assert len(seen) == 4  # the first request + 3 redirects


@pytest.mark.parametrize(
    "url",
    ["ftp://glowlab.co/", "https://user:pw@glowlab.co/", "https://glowlab.co:8443/", "http://glowlab.co:22/", "https:///nohost"],
)
async def test_bad_urls_are_refused(url: str) -> None:
    fetcher, seen = make_fetcher({("glowlab.co", "/"): html("x")})

    with pytest.raises(FetchBlocked):
        await fetcher.fetch(url)
    assert seen == []


async def test_large_pages_are_cut_at_the_size_limit() -> None:
    fetcher, _ = make_fetcher({("big.com", "/"): html("a" * 3_000_000)})

    page = await fetcher.fetch("https://big.com/")

    assert page.truncated and len(page.text) == 2_000_000


async def test_non_text_responses_are_not_read() -> None:
    image = httpx.Response(200, content=b"\x89PNG...", headers={"content-type": "image/png"})
    fetcher, _ = make_fetcher({("glowlab.co", "/logo.png"): image})

    page = await fetcher.fetch("https://glowlab.co/logo.png")

    assert (page.status, page.text) == (200, "")


async def test_slow_pages_time_out() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return html("late")

    fetcher, _ = make_fetcher({("slow.com", "/"): slow}, page_timeout=0.2)

    with pytest.raises(FetchFailed, match="too long"):
        await fetcher.fetch("https://slow.com/")


async def test_unknown_hosts_fail_cleanly() -> None:
    fetcher, _ = make_fetcher({}, dns={})

    with pytest.raises(FetchFailed, match="couldn't be found"):
        await fetcher.fetch("https://no-such-store.com/")


ROBOTS = "User-agent: *\nDisallow: /checkout\n\nUser-agent: SocialCommerceReliabilityReporter\nDisallow: /private\n"


async def test_robots_rules_are_respected() -> None:
    fetcher, _ = make_fetcher({("glowlab.co", "/robots.txt"): httpx.Response(200, text=ROBOTS, headers={"content-type": "text/plain"})})

    assert await fetcher.allowed_by_robots("https://glowlab.co/policies/refund-policy")
    assert not await fetcher.allowed_by_robots("https://glowlab.co/private/page")


async def test_a_site_that_blocks_all_bots_is_not_visited() -> None:
    blocked = httpx.Response(200, text="User-agent: *\nDisallow: /\n", headers={"content-type": "text/plain"})
    fetcher, _ = make_fetcher({("closed.com", "/robots.txt"): blocked})

    assert not await fetcher.allowed_by_robots("https://closed.com/")


async def test_missing_robots_txt_allows_everything_and_server_errors_allow_nothing() -> None:
    fetcher, _ = make_fetcher(
        {("open.com", "/"): html("x"), ("down.com", "/robots.txt"): httpx.Response(503, text="down", headers={"content-type": "text/plain"})}
    )

    assert await fetcher.allowed_by_robots("https://open.com/")  # robots.txt is a 404
    assert not await fetcher.allowed_by_robots("https://down.com/")


async def test_robots_txt_is_fetched_once_per_host() -> None:
    fetcher, seen = make_fetcher({("glowlab.co", "/robots.txt"): httpx.Response(200, text=ROBOTS, headers={"content-type": "text/plain"})})

    for path in ["/", "/a", "/b"]:
        await fetcher.allowed_by_robots(f"https://glowlab.co{path}")

    assert len(seen) == 1
