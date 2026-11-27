"""Measure extraction quality on data/extraction_eval.csv.

    uv run python -m scripts.eval_extraction --dry-run --split all   # check the CSV and scoring, no API calls
    uv run python -m scripts.eval_extraction                         # dev split (for tuning the prompt)
    uv run python -m scripts.eval_extraction --split test2           # held-out split: the number we report
    uv run python -m scripts.eval_extraction --model claude-haiku-5-5
    uv run python -m scripts.eval_extraction --live --runs 3         # real-time calls (measures latency), repeated

Runs the same pipeline as the API (Claude extractor, then the deterministic rules
with real DNS checks), so the score covers both. Live calls need ANTHROPIC_API_KEY
in backend/.env.

Keeping eval costs down (2026-11-24):
- Answers are cached in backend/.cache/eval_responses.json, keyed by the exact
  request (model, prompt, schema, effort, caption). Re-running unchanged rows is
  free; any prompt change automatically misses the cache. --no-cache forces calls.
- By default new calls go through the Message Batches API at half price (results
  usually arrive within minutes). --live calls in real time instead, which is
  needed to measure latency.
- Before any paid call, the script prints how many calls it will make and the
  estimated cost, and asks for confirmation (--yes skips the question).

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
import hashlib
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from pydantic import ValidationError

from app.extraction.base import ExtractionError, ExtractorNotConfigured, LLMExtraction
from app.extraction.claude import MODEL, ClaudeExtractor, build_batch_params
from app.extraction.domain_check import DnsResolver
from app.extraction.postprocess import apply_rules
from app.extraction.store_url import store_domain
from app.schemas import Extraction

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = REPO_ROOT / "data" / "extraction_eval.csv"
CACHE_FILE = REPO_ROOT / "backend" / ".cache" / "eval_responses.json"

# USD per million tokens (Anthropic price list, 2026-11). Output includes thinking tokens.
PRICES = {
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, "cache_read": 0.10},
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50, "cache_read": 0.01},
}
CACHE_WRITE_MULTIPLIER = 1.25  # 5-minute cache writes cost 1.25x the input price
BATCH_DISCOUNT = 0.5
# Rough per-call size for the up-front estimate (measured 2026-11-24 with the trimmed prompt).
EST_INPUT_TOKENS, EST_OUTPUT_TOKENS = 1300, 150

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
    seconds: float | None = None  # only measured for --live calls
    cost: float = 0.0  # what this answer cost when it was made
    from_cache: bool = False  # True = reused from the eval cache, nothing spent this run
    usage: dict = field(default_factory=dict)


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


def call_cost(model: str, usage: dict, batch: bool) -> float:
    p = PRICES[model]
    dollars = (
        usage.get("input", 0) * p["in"]
        + usage.get("cache_write", 0) * p["in"] * CACHE_WRITE_MULTIPLIER
        + usage.get("cache_read", 0) * p["cache_read"]
        + usage.get("output", 0) * p["out"]
    ) / 1e6
    return dollars * (BATCH_DISCOUNT if batch else 1.0)


def _usage_dict(usage: object) -> dict:
    return {
        "input": getattr(usage, "input_tokens", 0) or 0,
        "cache_write": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "output": getattr(usage, "output_tokens", 0) or 0,
    }


def request_key(caption: str, model: str) -> str:
    """Identifies the exact request: any change to the prompt, schema, effort,
    model or caption gives a new key, so stale answers are never reused."""
    body = json.dumps(build_batch_params(caption, model), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


def load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text())
    except FileNotFoundError:
        return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))


def confirm_spend(n_calls: int, model: str, batch: bool, assume_yes: bool) -> bool:
    estimate = n_calls * call_cost(model, {"input": EST_INPUT_TOKENS, "output": EST_OUTPUT_TOKENS}, batch)
    mode = "batch (half price)" if batch else "live"
    print(f"About to make {n_calls} {mode} call(s) to {model}; estimated cost up to ${estimate:.3f}.", file=sys.stderr)
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("Not confirmed (no terminal). Re-run with --yes to proceed.", file=sys.stderr)
        return False
    return input("Proceed? [y/N] ").strip().lower() in {"y", "yes"}


async def call_live(rows: list[EvalRow], model: str) -> dict[str, dict]:
    """One real-time call per row (sequential, so latency is measured cleanly)."""
    out: dict[str, dict] = {}
    seen: dict = {}

    def record(message, seconds: float) -> None:  # called by ClaudeExtractor after each reply
        seen.update(usage=_usage_dict(message.usage), seconds=seconds)

    extractor = ClaudeExtractor(model=model, on_response=record)
    for i, row in enumerate(rows, 1):
        print(f"  [{i}/{len(rows)}] {row.id}", file=sys.stderr)
        seen.clear()
        try:
            llm = await extractor.extract(row.caption)
            out[row.id] = {"llm": llm.model_dump(), "usage": seen["usage"], "seconds": seen["seconds"], "batch": False}
        except ExtractionError as error:
            out[row.id] = {"error": str(error), "usage": seen.get("usage", {}), "batch": False}
    return out


def call_batch(rows: list[EvalRow], model: str) -> dict[str, dict]:
    """All rows in one Message Batches request: half price, answers in minutes."""
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(
        requests=[{"custom_id": row.id, "params": build_batch_params(row.caption, model)} for row in rows]
    )
    print(f"  batch {batch.id} submitted ({len(rows)} requests)", file=sys.stderr)
    started = time.monotonic()
    while batch.processing_status != "ended":
        time.sleep(5)
        batch = client.messages.batches.retrieve(batch.id)
        counts = batch.request_counts
        print(f"  {time.monotonic() - started:4.0f}s: {counts.succeeded} done, {counts.processing} processing", file=sys.stderr)

    out: dict[str, dict] = {}
    for item in client.messages.batches.results(batch.id):
        result = item.result
        if result.type != "succeeded":
            out[item.custom_id] = {"error": f"batch request {result.type}", "usage": {}, "batch": True}
            continue
        message = result.message
        usage = _usage_dict(message.usage)
        # Same checks as ClaudeExtractor: why did the model stop, and does the answer fit the schema?
        if message.stop_reason in {"refusal", "max_tokens"}:
            out[item.custom_id] = {"error": f"stop_reason={message.stop_reason}", "usage": usage, "batch": True}
            continue
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            llm = LLMExtraction.model_validate_json(text)
        except ValidationError:
            out[item.custom_id] = {"error": "output didn't fit the schema", "usage": usage, "batch": True}
            continue
        out[item.custom_id] = {"llm": llm.model_dump(), "usage": usage, "seconds": None, "batch": True}
    return out


async def run(
    rows: list[EvalRow], *, model: str, dry_run: bool, use_cache: bool, batch: bool, assume_yes: bool
) -> list[RowResult] | None:
    """Returns None if the user declined the spend."""
    resolver = _AlwaysExists() if dry_run else DnsResolver()
    answers: dict[str, dict] = {}
    from_cache: set[str] = set()

    if dry_run:
        answers = {r.id: {"llm": _expected_as_llm(r).model_dump(), "usage": {}} for r in rows}
    else:
        cache = load_cache()
        keys = {r.id: request_key(r.caption, model) for r in rows}
        if use_cache:
            for r in rows:
                if keys[r.id] in cache:
                    answers[r.id] = cache[keys[r.id]]
                    from_cache.add(r.id)
        todo = [r for r in rows if r.id not in answers]
        if todo:
            if not confirm_spend(len(todo), model, batch, assume_yes):
                return None
            new = call_batch(todo, model) if batch else await call_live(todo, model)
            answers.update(new)
            for r in todo:
                if "llm" in new[r.id]:  # never cache failures
                    cache[keys[r.id]] = new[r.id]
            save_cache(cache)
        print(f"  {len(from_cache)} answer(s) reused from the eval cache, {len(todo)} new call(s)", file=sys.stderr)

    results = []
    for row in rows:
        answer = answers[row.id]
        if "llm" in answer:
            llm = LLMExtraction.model_validate(answer["llm"])
            extraction, error = await apply_rules(llm, row.caption, resolver), None
        else:
            extraction, error = None, answer["error"]
        usage = answer.get("usage", {})
        result = RowResult(
            row, extraction, error,
            seconds=answer.get("seconds"),
            cost=0.0 if dry_run else call_cost(model, usage, answer.get("batch", False)),
            from_cache=row.id in from_cache,
            usage=usage,
        )
        result.correct = score(row, extraction)
        results.append(result)
    return results


def _pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / len(values):.0f}% ({sum(values)}/{len(values)})" if values else "n/a"


def report(results: list[RowResult], split: str, dry_run: bool, model: str) -> str:
    """Markdown tables, ready to paste into docs/EVALUATION.md."""
    scored = lambda f, rs: [r.correct[f] for r in rs if r.correct[f] is not None]  # noqa: E731
    lines = [f"### Extraction eval: split={split}, rows={len(results)}, model={'(dry run)' if dry_run else model}", ""]

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
        total = sum(r.cost for r in results)
        spent = sum(r.cost for r in results if not r.from_cache)
        tokens = {k: sum(r.usage.get(k, 0) for r in results) for k in ("input", "cache_write", "cache_read", "output")}
        lines += [
            "| Cost and latency | Value |", "|---|---|",
            f"| Cost per caption (as measured when each answer was made) | ${total / len(results):.5f} |",
            f"| Spent in this run (answers reused from the eval cache cost nothing) | ${spent:.4f} |",
            f"| Tokens: full-price in / cache write / cache read / out | {tokens['input']:,} / {tokens['cache_write']:,} / {tokens['cache_read']:,} / {tokens['output']:,} |",
            f"| Mean / max latency per caption | {statistics.mean(times):.2f}s / {max(times):.2f}s |" if times
            else "| Latency | not measured (batch or cached answers; use --live --no-cache) |",
            "",
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
    for row_results in zip(*runs, strict=True):
        marks = ["✓" if _all_ok(r) else "✗" for r in row_results]
        if "✗" in marks:
            unstable += "✓" in marks
            r = row_results[0]
            brands = sorted({str(x.extraction.brand) if x.extraction else "error" for x in row_results})
            stores = sorted({str(x.extraction.store_url) if x.extraction else "error" for x in row_results})
            lines.append(f"- `{r.row.id}` ({r.row.case_type}) {' '.join(marks)}  brand={brands} store={stores}")
    lines += ["", f"Rows that flipped between right and wrong: {unstable}"]
    spent = sum(r.cost for rs in runs for r in rs if not r.from_cache)
    lines.append(f"Spent across these runs: ${spent:.4f}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=[*sorted(SPLITS), "all"], default="dev")
    parser.add_argument("--model", choices=sorted(PRICES), default=MODEL)
    parser.add_argument("--runs", type=int, default=1, help="repeat N times and report the spread (implies --no-cache)")
    parser.add_argument("--live", action="store_true", help="real-time calls (measures latency) instead of the half-price batch API")
    parser.add_argument("--no-cache", action="store_true", help="don't reuse earlier answers from the eval cache")
    parser.add_argument("--yes", action="store_true", help="don't ask before spending")
    parser.add_argument("--dry-run", action="store_true", help="score the expected answers against themselves (no API calls)")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / "backend" / ".env", override=False)
    rows = [r for r in load_rows(args.csv) if args.split == "all" or r.split == args.split]
    runs: list[list[RowResult]] = []
    try:
        for _ in range(max(1, args.runs)):
            results = asyncio.run(run(
                rows, model=args.model, dry_run=args.dry_run,
                use_cache=not (args.no_cache or args.runs > 1), batch=not args.live, assume_yes=args.yes,
            ))
            if results is None:
                return 1
            runs.append(results)
    except ExtractorNotConfigured as error:
        print(f"{error} (or use --dry-run)", file=sys.stderr)
        return 1
    except anthropic.AuthenticationError:
        print("ANTHROPIC_API_KEY is missing or invalid (or use --dry-run)", file=sys.stderr)
        return 1
    print(report(runs[-1], args.split, args.dry_run, args.model))
    if len(runs) > 1:
        print("\n" + consistency_report(runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
