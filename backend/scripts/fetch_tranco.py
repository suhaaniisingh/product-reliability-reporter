"""Download the Tranco top-sites list and keep the top 100,000 domains.

    uv run python -m scripts.fetch_tranco

Run when the container is built (see Dockerfile) and once locally for
development. Writes backend/.cache/tranco_top.csv (git-ignored) plus a small
.json file recording the download date.
"""

import csv
import io
import json
import sys
import zipfile
from datetime import UTC, datetime

import httpx

from app.signals.popularity import DEFAULT_LIST

URL = "https://tranco-list.eu/top-1m.csv.zip"
KEEP = 100_000  # raised from 50,000 on 2026-11-24 (Suhaani)


def main() -> int:
    response = httpx.get(URL, timeout=60, follow_redirects=True)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        name = archive.namelist()[0]
        with archive.open(name) as raw:
            rows = []
            for rank, domain in csv.reader(io.TextIOWrapper(raw, encoding="utf-8")):
                rows.append((int(rank), domain.strip().lower()))
                if len(rows) >= KEEP:
                    break
    if len(rows) < KEEP:
        print(f"Only {len(rows)} rows downloaded; refusing to write a partial list.", file=sys.stderr)
        return 1
    DEFAULT_LIST.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_LIST.open("w", newline="") as file:
        csv.writer(file).writerows(rows)
    DEFAULT_LIST.with_suffix(".json").write_text(
        json.dumps({"source": URL, "downloaded_on": datetime.now(UTC).date().isoformat(), "rows": len(rows)})
    )
    print(f"Wrote {len(rows):,} domains to {DEFAULT_LIST} ({len(response.content) / 1e6:.1f} MB downloaded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
