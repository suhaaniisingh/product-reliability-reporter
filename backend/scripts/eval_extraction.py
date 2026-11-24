"""Measure extraction quality on data/extraction_eval.csv.

    uv run python -m scripts.eval_extraction                 # dev split (for tuning the prompt)
    uv run python -m scripts.eval_extraction --split test2   # held-out split: the number we report
    uv run python -m scripts.eval_extraction --runs 3        # repeat to see run-to-run variation
    uv run python -m scripts.eval_extraction --dry-run       # check the CSV and scoring, no API calls

Runs the same pipeline as the API (Claude extractor, then the deterministic rules
with real DNS checks), so the score covers both. Live runs need ANTHROPIC_API_KEY
in backend/.env and cost roughly $0.003 per row.

Matching rules for the expected_* columns:
- blank = the field must be null / none
- "a|b" = any listed alternative is accepted
- "*"   = anything is accepted (the field isn't scored for this row)
- product: case- and punctuation-insensitive, and either side may contain the other
- brand, discount code: case- and punctuation-insensitive exact match
- store URL: compared by domain (https://www.GlowLab.co/x == glowlab.co)
"""

import argparse
import asyncio
import csv
import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from app.extraction.base import ExtractionError, ExtractorNotConfigured, LLMExtraction
from app.extraction.claude import MODEL, ClaudeExtractor
from app.extraction.domain_check import DnsResolver
from app.extraction.postprocess import apply_rules
from app.extraction.store_url import store_domain
from app.schemas import Extraction

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = REPO_ROOT / "data" / "extraction_eval.csv"

# USD per million tokens for claude-sonnet-5-5 (Anthropic price list, 2026-11).
# Output tokens include the model's thinking tokens.
PRICE_IN_PER_MTOK = 2.00
PRICE_OUT_PER_MTOK = 10.00

CASE_TYPES = {"explicit_url", "brand_only", "link_in_bio", "code_only", "no_store", "tricky"}
SOURCES = {"in_caption", "guessed_from_brand", "none"}
# test = first held-out split (used 2026-11-23, then seen while fixing hashtag brands);
# test2 = fresh held-out rows for reporting after that fix.
SPLITS = {"dev", "test", "test2"}
FIELDS = ("store", "source", "product", "brand", "discount_code", "link_in_bio")


@dataclass
class EvalRow:
    id: str
    split: str
    case_type: str
    platform: str
    caption: str
    product: str
    brand: str
    store_url: str
    source: str
    link_in_bio: bool
    discount_code: str
    notes: str


@dataclass
class RowResult:
    row: EvalRow
    extraction: Extraction | None
    error: str | None
    correct: dict[str, bool | None] = field(default_factory=dict)  # None = not scored
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


def load_rows(path: Path) -> list[EvalRow]:
    """Read and validate the CSV. Raises ValueError naming the first bad row."""
    rows = []
    with path.open(newline="", encoding="utf-8") as file:
        for record in csv.DictReader(file):
            row = EvalRow(
                id=record["id"], split=record["split"], case_type=record["case_type"], platform=record["platform"],
                caption=record["caption"], product=record["expected_product"], brand=record["expected_brand"],
                store_url=record["expected_store_url"], source=record["expected_store_url_source"],
                link_in_bio=record["expected_link_in_bio"].strip().lower() == "true",
                discount_code=record["expected_discount_code"], notes=record["notes"],
            )
            problems = [
                row.split not in SPLITS and f"split must be one of {sorted(SPLITS)}",
                row.case_type not in CASE_TYPES and f"unknown case_type {row.case_type!r}",
                row.source not in SOURCES and f"unknown expected_store_url_source {row.source!r}",
                record["expected_link_in_bio"].strip().lower() not in {"true", "false"} and "expected_link_in_bio must be true/false",
                not row.caption.strip() and "empty caption",
                bool(row.store_url) != (row.source != "none") and "expected_store_url and its source disagree",
            ]
            if bad := [p for p in problems if p]:
                raise ValueError(f"{path.name} row {row.id}: {'; '.join(bad)}")
            rows.append(row)
    if len({r.id for r in rows}) != len(rows):
        raise ValueError(f"{path.name}: duplicate ids")
    return rows


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _alternatives(expected: str) -> list[str]:
    return [a.strip() for a in expected.split("|") if a.strip()]


def match_text(expected: str, predicted: str | None, *, contains: bool = False) -> bool | None:
    if "*" in _alternatives(expected):  # "*" or "Kyoto Leaf|*": anything goes, not scored
        return None
    if not expected.strip():
        return predicted is None or not predicted.strip()
    if predicted is None or not _norm(predicted):
        return False
    got = _norm(predicted)
    for alt in map(_norm, _alternatives(expected)):
        if got == alt or (contains and (alt in got or got in alt)):
            return True
    return False


def match_store(expected: str, predicted: str | None) -> bool:
    if not expected.strip():
        return predicted is None
    if predicted is None:
        return False
    return store_domain(predicted) in {store_domain(a) for a in _alternatives(expected)}


def score(row: EvalRow, extraction: Extraction | None) -> dict[str, bool | None]:
    if extraction is None:  # the extraction failed: every scored field is wrong
        return {f: False for f in FIELDS}
    return {
        "store": match_store(row.store_url, extraction.store_url),
        "source": extraction.store_url_source.value == row.source,
        "product": match_text(row.product, extraction.product, contains=True),
        "brand": match_text(row.brand, extraction.brand),
        "discount_code": match_text(row.discount_code, extraction.discount_code),
        "link_in_bio": extraction.mentions_link_in_bio == row.link_in_bio,
    }


def _expected_as_llm(row: EvalRow) -> LLMExtraction:
    """For --dry-run: pretend the model returned exactly the expected answer."""
    first = lambda s: None if s.strip() in {"", "*"} else _alternatives(s)[0]  # noqa: E731
    return LLMExtraction(
        product=first(row.product), brand=first(row.brand), store_url=first(row.store_url),
        store_url_source=row.source, mentions_link_in_bio=row.link_in_bio,  # type: ignore[arg-type]
        discount_code=first(row.discount_code), confidence="high" if row.store_url else "low", notes="",
    )


class _AlwaysExists:
    async def exists(self, domain: str) -> bool:
        return True


async def run(rows: list[EvalRow], dry_run: bool) -> list[RowResult]:
    results: list[RowResult] = []
    usage: dict = {}

    def record(message, seconds: float) -> None:  # called by ClaudeExtractor after each reply
        usage.update(seconds=seconds, input=message.usage.input_tokens, output=message.usage.output_tokens)

    extractor = ClaudeExtractor(on_response=record)
    resolver = _AlwaysExists() if dry_run else DnsResolver()
    for i, row in enumerate(rows, 1):
        usage.clear()
        print(f"  [{i}/{len(rows)}] {row.id} {row.case_type}", file=sys.stderr)
        try:
            llm = _expected_as_llm(row) if dry_run else await extractor.extract(row.caption)
            extraction, error = await apply_rules(llm, row.caption, resolver), None
        except ExtractionError as exc:
            extraction, error = None, str(exc)
        result = RowResult(row, extraction, error, seconds=usage.get("seconds", 0.0),
                           input_tokens=usage.get("input", 0), output_tokens=usage.get("output", 0))
        result.correct = score(row, extraction)
        results.append(result)
    return results


def _pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / len(values):.0f}% ({sum(values)}/{len(values)})" if values else "n/a"


def report(results: list[RowResult], split: str, dry_run: bool) -> str:
    """Markdown tables, ready to paste into docs/EVALUATION.md."""
    scored = lambda f, rs: [r.correct[f] for r in rs if r.correct[f] is not None]  # noqa: E731
    lines = [f"### Extraction eval: split={split}, rows={len(results)}, model={'(dry run)' if dry_run else MODEL}", ""]

    lines += ["| Field | Accuracy |", "|---|---|"]
    lines += [f"| {f} | {_pct(scored(f, results))} |" for f in FIELDS]
    all_ok = [all(v is not False for v in r.correct.values()) for r in results]
    lines += [f"| **all fields correct** | {_pct(all_ok)} |", ""]

    by_case: dict[str, list[RowResult]] = defaultdict(list)
    for r in results:
        by_case[r.row.case_type].append(r)
    lines += ["| Case type | Store correct | All fields correct |", "|---|---|---|"]
    for case in sorted(by_case):
        rs = by_case[case]
        lines.append(f"| {case} | {_pct(scored('store', rs))} | {_pct([all(v is not False for v in r.correct.values()) for r in rs])} |")
    lines.append("")

    guesses = [r for r in results if r.row.source == "guessed_from_brand"]
    no_store = [r for r in results if not r.row.store_url and r.extraction is not None]
    lines += [
        "| Store-specific metric | Value |", "|---|---|",
        f"| Guess accuracy (rows where the right answer is a guessed domain) | {_pct(scored('store', guesses))} |",
        f"| False-store rate (a store returned when the right answer is none) | {_pct([r.extraction.store_url is not None for r in no_store])} |",  # type: ignore[union-attr]
        f"| Extraction errors | {sum(r.error is not None for r in results)} |", "",
    ]

    by_conf: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        if r.extraction is not None:
            by_conf[r.extraction.confidence.value].append(bool(r.correct["store"]))
    lines += ["| Reported confidence | Store correct |", "|---|---|"]
    lines += [f"| {c} | {_pct(by_conf[c])} |" for c in ("high", "medium", "low")]
    lines.append("")

    if not dry_run:
        times = [r.seconds for r in results if r.seconds]
        cost = sum(r.input_tokens * PRICE_IN_PER_MTOK + r.output_tokens * PRICE_OUT_PER_MTOK for r in results) / 1e6
        lines += [
            "| Cost and latency | Value |", "|---|---|",
            f"| Mean / max latency per caption | {statistics.mean(times):.2f}s / {max(times):.2f}s |" if times else "| Latency | n/a |",
            f"| Tokens in / out (total) | {sum(r.input_tokens for r in results):,} / {sum(r.output_tokens for r in results):,} |",
            f"| Estimated cost | ${cost:.4f} total, ${cost / len(results):.4f} per caption |", "",
        ]

    misses = [r for r in results if any(v is False for v in r.correct.values())]
    if misses:
        lines += ["Misses:", ""]
        for r in misses:
            wrong = ", ".join(f for f, v in r.correct.items() if v is False)
            got = r.error or (f"store={r.extraction.store_url} source={r.extraction.store_url_source.value} "  # type: ignore[union-attr]
                              f"brand={r.extraction.brand} product={r.extraction.product}")  # type: ignore[union-attr]
            lines.append(f"- `{r.row.id}` ({r.row.case_type}) wrong: {wrong}. Got: {got}")
    return "\n".join(lines)


def _all_ok(r: RowResult) -> bool:
    return all(v is not False for v in r.correct.values())


def consistency_report(runs: list[list[RowResult]]) -> str:
    """For --runs N: the spread of the headline numbers, and which rows changed."""
    n = len(runs)
    header = "| Metric | " + " | ".join(f"Run {i + 1}" for i in range(n)) + " | Mean |"
    lines = [f"### Consistency over {n} runs ({len(runs[0])} rows each)", "", header, "|---" * (n + 2) + "|"]
    for name, check in [
        ("store", lambda r: r.correct["store"]),
        ("brand", lambda r: r.correct["brand"]),
        ("all fields correct", _all_ok),
    ]:
        rates = []
        for results in runs:
            values = [check(r) for r in results if check(r) is not None]
            rates.append(100 * sum(values) / len(values) if values else 0.0)
        lines.append(f"| {name} | " + " | ".join(f"{x:.0f}%" for x in rates) + f" | {statistics.mean(rates):.0f}% |")

    lines += ["", "Rows that were wrong in at least one run (✓ = all fields right in that run):", ""]
    unstable = 0
    for i, row_results in enumerate(zip(*runs)):
        marks = ["✓" if _all_ok(r) else "✗" for r in row_results]
        if "✗" in marks:
            unstable += "✓" in marks
            r = row_results[0]
            brands = sorted({str(x.extraction.brand) if x.extraction else "error" for x in row_results})
            stores = sorted({str(x.extraction.store_url) if x.extraction else "error" for x in row_results})
            lines.append(f"- `{r.row.id}` ({r.row.case_type}) {' '.join(marks)}  brand={brands} store={stores}")
    lines += ["", f"Rows that flipped between right and wrong: {unstable}"]
    cost = sum(r.input_tokens * PRICE_IN_PER_MTOK + r.output_tokens * PRICE_OUT_PER_MTOK for rs in runs for r in rs) / 1e6
    lines.append(f"Total estimated cost: ${cost:.4f}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=[*sorted(SPLITS), "all"], default="dev")
    parser.add_argument("--runs", type=int, default=1, help="repeat the eval N times and report the spread")
    parser.add_argument("--dry-run", action="store_true", help="score the expected answers against themselves (no API calls)")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / "backend" / ".env", override=False)
    rows = [r for r in load_rows(args.csv) if args.split == "all" or r.split == args.split]
    try:
        runs = [asyncio.run(run(rows, args.dry_run)) for _ in range(max(1, args.runs))]
    except ExtractorNotConfigured as error:
        print(f"{error} (or use --dry-run)", file=sys.stderr)
        return 1
    print(report(runs[-1], args.split, args.dry_run))
    if len(runs) > 1:
        print("\n" + consistency_report(runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
