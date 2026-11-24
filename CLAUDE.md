# CLAUDE.md — Social Commerce Trust Checker

## What this project is

A tool that tells a shopper whether the store behind a TikTok/Instagram product promo looks trustworthy, and **why**.

Given a social media video (pasted link, or the video open in the browser), the system:

1. **Extracts** what is being promoted: product, brand, and store URL, from the caption and other public metadata.
2. **Collects public trust signals** about that store (domain age, blocklists, store-page checks, etc.).
3. **Scores** the store and returns an explainable result: a score, a confidence level, and the reasons behind it.

Working name: "Social Commerce Trust Checker" (not final).

## Why this project exists (read this — it shapes every decision)

This is primarily a **portfolio project for SWE / AI-ML / cloud internship recruiting**, built by Suhaani (2nd-year CS student). It is not a startup. That means:

- **Engineering depth and measurability matter more than features.** Every phase should produce something that can be measured (accuracy, F1, latency, cache hit rate).
- **Suhaani must understand and be able to defend every design decision in an interview.** You are a collaborator and teacher, not just a code generator.
- **Finishing matters more than scope.** A small, deployed, measured system beats a large unfinished one.

## Non-goals (do NOT build these)

- ❌ Payment layer, escrow, or protected checkout. Removed on purpose.
- ❌ Private seller data (sales history, purchase counts). We only use **public** signals.
- ❌ Scraping that violates a platform's terms of service. Use official/oEmbed endpoints or user-pasted text. If unsure whether something is allowed, stop and ask.
- ❌ B2B features, merchant dashboards, user accounts/login (for the MVP).
- ❌ Features from a later phase while the current phase is unfinished.

## Proposed tech stack (confirm with Suhaani before locking anything in)

- **Backend:** Python + FastAPI
- **Web page (paste-a-link, mobile-friendly):** React + TypeScript (or a minimal page served by the backend in Phase 1)
- **Browser extension:** Chrome, Manifest V3, TypeScript (Phase 4)
- **LLM extraction:** provider TBD. Keep it behind an interface so it can be swapped and evaluated.
- **Database / cache / job queue:** decide in Phase 5 (e.g. Postgres + Redis). Don't add them before they're needed.
- **Hosting:** must be free (free tiers only).

## Architecture (target, built up over the phases)

```
[Chrome extension] ─┐
                    ├─► POST /scan ─► [Extraction] ─► [Signal fetchers (parallel)] ─► [Scorer] ─► result
[Paste-link page] ──┘                   caption→LLM      domain age, blocklists,        score +
                                        → product,       store-page checks, reviews,    confidence +
                                          brand, URL     (stretch) dropship check       reasons
```

Design principles:
- Each **signal fetcher** is an independent module with the same interface. It returns a value, a status (ok / failed / timeout), and a short explanation. One failing signal must never crash a scan.
- The **scorer** only reads signal outputs. Scoring logic must be explainable (every point added or removed has a reason string).
- **Extraction** and **scoring** must each be testable offline against saved fixtures (no live API calls in unit tests).

## Phases

### Phase 1 — Extraction pipeline (walking skeleton)
Goal: paste a video link → get structured extraction back.
- `POST /scan` takes a video URL (or raw caption text as a fallback).
- Fetch public metadata (caption, creator) using official/oEmbed endpoints. **Verify current availability and terms first** and report back.
- LLM extracts `{product, brand, store_url, confidence, notes}` as validated structured output (e.g. Pydantic).
- Handle messy cases: "link in bio", discount codes only, no store mentioned.
- Small eval set: ~30 hand-labelled captions in `data/extraction_eval.csv`, plus a script that reports extraction accuracy.
- Minimal page or CLI to try it out.
- **Done when:** end-to-end works locally, tests pass, the eval script prints an accuracy number.

### Phase 2 — Trust signals + rule-based score
- Signal fetchers: domain age (WHOIS/RDAP), Google Safe Browsing (or similar blocklist), store-page checks (return policy, contact info, Shopify-template detection), and one review/mention source if a permitted API exists.
- Rule-based scorer with reasons and a confidence level (lower confidence when signals fail).
- Deploy the backend + paste-link page on a free host.
- **Done when:** a deployed URL returns a score with reasons for a real store.

### Phase 3 — Labelled dataset + evaluation
- Label 200–300 stores as legit / sketchy in `data/stores_labelled.csv` (source of each label recorded; public scam-domain lists can help).
- Evaluation script: precision, recall, F1, confusion matrix.
- Compare the rule-based scorer with a simple learned model (e.g. logistic regression on the signals). Document the results in `docs/EVALUATION.md`.
- **Done when:** there is a reproducible F1 number for each approach.

### Phase 4 — Chrome extension
- Detect the video on the current tab, call `/scan`, show the result in a popup.
- Request only the permissions it needs. Explain each permission to Suhaani.
- **Done when:** installable unpacked extension works on real TikTok/Instagram pages.

### Phase 5 — Systems hardening
- Async job processing: a scan becomes a job; signal fetchers run in parallel.
- Timeouts and retries with backoff for outside APIs; partial results when a source is down.
- Cache results per domain with a TTL. Deduplicate concurrent scans of the same domain (idempotency).
- Rate limiting on outside API calls.
- Measure p95 latency and cache hit rate before and after; record them in `docs/METRICS.md`.

### Phase 6 — Stretch
- Dropshipping / markup detection: find the same product elsewhere at a much lower price (e.g. image embeddings like CLIP). Approach TBD; research options and discuss with Suhaani first.
- PWA share target so mobile users can share a video straight to the app.

## How to work with Suhaani

- **The product is still being defined. Ask about specs instead of guessing.** Before starting a task, list your open questions and wait for answers.
- **Explain step by step, including why.** For every meaningful decision (library, data model, API shape, architecture), explain what it is, why you chose it, what the alternatives were, and how it connects to real production systems.
- **Propose, then build.** Start each phase or larger task with a short plan; wait for approval before writing code.
- **Work in small, reviewable steps.** One focused change per commit, with clear messages.
- **Log decisions** in `docs/DECISIONS.md` (date, decision, why, alternatives considered). Suhaani will use this to prepare for interviews.
- **Write tests** for extraction, each signal fetcher, and the scorer. Use saved fixtures, not live calls.
- **Stay in the current phase.** If you notice something for a later phase, add it to `docs/BACKLOG.md` instead of building it.
- **Secrets** go in `.env` (git-ignored) with a `.env.example` committed. Never commit API keys.

## Metrics to track (these become resume bullets)

| Metric | Phase | Where recorded |
|---|---|---|
| Extraction accuracy on eval set | 1 | `docs/EVALUATION.md` |
| Precision / recall / F1 (rules vs model) | 3 | `docs/EVALUATION.md` |
| p95 scan latency (before/after Phase 5) | 5 | `docs/METRICS.md` |
| Cache hit rate | 5 | `docs/METRICS.md` |
| Number of real users who installed the extension | 4+ | `docs/METRICS.md` |
