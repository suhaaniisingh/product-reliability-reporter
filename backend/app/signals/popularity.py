"""Site popularity: is the store among the world's 100,000 most-visited sites?

Uses the Tranco list (tranco-list.eu), a research ranking that combines several
traffic sources and is hardened against manipulation. scripts/fetch_tranco.py
downloads it when the container is built; here it's loaded once into memory
(100,000 domains, about 10 MB in memory).

Being on the list is real evidence of an established site, so it adds points.
Not being on it means nothing (most honest small shops aren't), so it never
counts against a store.
"""

import csv
import json
import os
from functools import lru_cache
from pathlib import Path

from app.signals.base import Finding, SignalUnavailable, Store
from app.signals.domains import registrable_domain

DEFAULT_LIST = Path(__file__).resolve().parents[2] / ".cache" / "tranco_top.csv"
ATTRIBUTION = "Popularity data: Tranco list (https://tranco-list.eu)"


class TrancoList:
    def __init__(self, ranks: dict[str, int], downloaded_on: str | None = None) -> None:
        self.ranks = ranks
        self.downloaded_on = downloaded_on

    @classmethod
    def load(cls, path: Path) -> "TrancoList":
        with path.open(newline="") as file:
            ranks = {domain: int(rank) for rank, domain in csv.reader(file)}
        meta = path.with_suffix(".json")
        downloaded_on = json.loads(meta.read_text()).get("downloaded_on") if meta.exists() else None
        return cls(ranks, downloaded_on)

    def rank(self, domain: str) -> int | None:
        return self.ranks.get(domain)


@lru_cache(maxsize=1)
def default_tranco() -> TrancoList | None:
    """The list from disk, loaded once per process; None if it hasn't been downloaded."""
    path = Path(os.environ.get("TRANCO_LIST_PATH", DEFAULT_LIST))
    return TrancoList.load(path) if path.exists() else None


class PopularitySignal:
    name = "popularity"
    label = "Site popularity"
    timeout_seconds = 1.0

    def __init__(self, tranco: TrancoList | None) -> None:
        self._tranco = tranco

    async def check(self, store: Store) -> Finding:
        if self._tranco is None:
            raise SignalUnavailable("the popularity list isn't available on this server.")
        domain = registrable_domain(store.domain)
        rank = self._tranco.rank(domain)
        size = len(self._tranco.ranks)
        if rank is not None:
            explanation = f"{domain} is among the world's most-visited sites (rank {rank:,} of the top {size:,})."
        else:
            explanation = (
                f"{domain} isn't among the {size:,} most-visited sites. That's normal for small shops, "
                "so it doesn't count against the store."
            )
        return Finding(value={"rank": rank, "list_size": size, "domain": domain}, explanation=explanation, source=ATTRIBUTION)
