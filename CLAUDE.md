# CLAUDE.md — Social Commerce Reliability Reporter

## What this project is

A tool that tells a shopper whether the store behind a TikTok/Instagram product promo looks trustworthy, and **why**.

The user gives a store link, or a video caption that mentions one (a small LLM helper pulls the store out of the caption). The backend then:

1. **Creates a check** for the store as a background job and returns its ID right away. A store checked recently is answered from the cache; simultaneous checks of the same store share one job.
2. **Collects public trust signals** in parallel (domain age, Safe Browsing, store-page checks, popularity), each with a timeout and retries. A failing source lowers confidence instead of failing the check.
3. **Scores** the store: a score, a confidence level, and a reason for every point. Every result is stored, so a store's score history can be shown.

Name: "Social Commerce Reliability Reporter" (short form: "Reliability Reporter").

## Why this project exists (read this — it shapes every decision)

This is a **portfolio project for backend / SWE / cloud internship recruiting**, built by Suhaani (2nd-year CS student). It is not a startup. Its depth is in **backend engineering**: background jobs, caching and deduplication, failure handling, a relational data model, CI/CD and measured performance. ML is a separate, later project (direction changed 2026-11-26, see `docs/DECISIONS.md`).

- **Engineering depth and measurability matter more than features.** Every phase should produce a number (p95 latency, throughput, cache hit rate, per-source failure rate, how well the score separates known scams from legit stores).
- **Only build backend machinery the product needs.** Every piece must serve something a user notices (speed, reliability, history) or something we must prove. Nothing is added just to show a technology.
- **Suhaani must understand and be able to defend every design decision in an interview.** You are a collaborator and teacher, not just a code generator. Suhaani writes the DevOps herself (docker-compose, CI/CD, the server setup); you explain first and review after.
- **Finishing matters more than scope.** A small, deployed, measured system beats a large unfinished one.

## Non-goals (do NOT build these)

- ❌ Payment layer, escrow, or protected checkout. Removed on purpose.
- ❌ Private seller data (sales history, purchase counts). We only use **public** signals.
- ❌ Scraping that violates a platform's terms of service. Use user-pasted text or user-initiated actions. If unsure whether something is allowed, stop and ask.
- ❌ B2B features, merchant dashboards, user accounts/login.
- ❌ ML training: classifiers, learned scoring models, large labelled datasets. (ML is a separate project.)
- ❌ Multimodal extraction (transcription, OCR, screenshots read by an LLM) and image-based dropshipping detection.
- ❌ LLM features as the headline. Only small helpers, such as caption → store link.
- ❌ Infrastructure without a measured need: Redis, extra services, WebSockets/push, multiple app instances, Kubernetes. Add one only when a measurement shows it's needed.
- ❌ Features from a later phase while the current phase is unfinished.

## Tech stack (confirm with Suhaani before locking anything in)

- **Backend:** Python 3.14 + FastAPI (async), managed with uv.
- **Database:** PostgreSQL. Holds stores, checks, per-signal results and score snapshots, and also serves as the job queue and the cache. Accessed through **SQLAlchemy 2.0**, with **Alembic** migrations (decided 2026-11-26).
- **Web page:** React + TypeScript + Vite + Tailwind, served by the backend.
- **Browser extension:** Chrome, Manifest V3, TypeScript (Phase 7).
- **LLM helper:** Claude Sonnet 5.5 via the `anthropic` SDK, behind the `Extractor` interface.
- **Containers:** Docker + docker-compose, the same setup locally and on the server.
- **CI/CD:** GitHub Actions.
- **Hosting:** free tiers only, with one accepted exception: a **self-managed Google Cloud e2-micro VM** (Always Free) running docker-compose, whose public IPv4 address costs about $3.65/month (decided 2026-11-26). HTTPS via Caddy on a free DuckDNS subdomain (https://reliability-reporter.duckdns.org). Cloud Run was retired on 2026-11-27.
- **Load testing:** decided in Phase 6 (k6 or Locust).

## Architecture (target, built up over the phases)

```
[Chrome extension] ─┐
                    ├─► POST /api/checks ─► fresh cached result? ── yes ─► return it
[Paste-link page] ──┘   (caption → LLM          │ no
                         helper → store)        ├─► same store already being checked? ── yes ─► return that check's ID
                                                │ no
                                                └─► insert job in Postgres ─► 202 + check ID

[Worker] claims next job ─► signal fetchers in parallel ─► scorer ─► save signal results + score snapshot
                            (timeouts, retries with backoff,
                             per-source limits)

Client ─► GET /api/checks/{id} (polling) ─► status + results so far
```

Design principles:
- Each **signal fetcher** is an independent module with the same interface. It returns a value, a status (ok / failed / timeout), and a short explanation. One failing signal must never crash a check.
- Everything that calls an outside source has a **timeout, a retry policy and a per-source limit**.
- Checks are **idempotent per store**: at most one running check per store, and results are reused until they expire.
- The **scorer** only reads signal outputs. Every point added or removed has a reason string. Score snapshots record the scorer version.
- Extraction, signals and scoring are testable offline against saved fixtures (no live API calls in unit tests). Database code is tested against a **real Postgres** (docker-compose locally, a service container in CI), not mocks.

## Phases

### Phase 1 — Caption → store extraction helper ✅ (2026-11-24)
Caption and/or store link in, structured extraction out; eval set and accuracy numbers in `docs/EVALUATION.md`.

### Phase 2 — Trust signals + rule-based score + first deploy ✅ (2026-11-25)
Five public signals run in parallel with timeouts and partial results; a scorer with a reason for every point; rate limiting; deployed on Cloud Run.

### Phase 3 — DevOps foundation: containers, CI/CD, the server
- docker-compose (app + Postgres), used both locally and on the server.
- GitHub Actions: tests and lint on every push and pull request, then an automatic deploy to the VM from `main`.
- Choose the VM provider (researched first) and set it up: firewall, HTTPS, secrets. Move the live app from Cloud Run to the VM.
- **Done when:** a push to `main` runs CI and, when green, deploys to the VM, which serves the app over HTTPS.

### Phase 4 — Checks as background jobs + data model
- Postgres schema with Alembic migrations: `stores`, `checks`, `signal_results`, `score_snapshots`.
- `POST /api/checks` → 202 + check ID; `GET /api/checks/{id}` → status + results so far (replaces `POST /api/scan`). A Postgres-backed queue and a worker run the existing signals and scorer.
- The page polls and shows each signal as it finishes.
- **Done when:** the deployed app runs checks as jobs and stores every result.

### Phase 5 — Reliability + score validation
- Retries with exponential backoff and jitter (transient errors only), per-source concurrency limits, structured JSON logs (check ID, source, duration, outcome).
- ~100 hand-labelled known-scam vs known-legit stores; a script reports how well the score separates them. A small step, not a dataset project.
- **Done when:** the per-source failure rate (before/after retries) and the separation numbers are recorded.

### Phase 6 — Caching, deduplication, measured performance
- Baseline load test first: p95 latency and throughput.
- Cache per store with an expiry; deduplicate concurrent checks of the same store; score history and "checked X ago / re-check" on the page.
- Re-run the load test; record before/after numbers and the cache hit rate in `docs/METRICS.md`.
- **Done when:** the before/after numbers are recorded.

### Phase 7 — Chrome extension
- Check the store page in the current tab, or right-click selected caption text → "Check this store". Minimal permissions, each explained to Suhaani.
- **Done when:** an unpacked extension works on real store pages and TikTok/Instagram pages.

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
| Extraction helper accuracy | 1 ✅ | `docs/EVALUATION.md` |
| Per-source failure rate, before/after retries | 5 | `docs/METRICS.md` |
| Score separation on ~100 labelled stores | 5 | `docs/EVALUATION.md` |
| p95 latency and throughput, before/after caching | 6 | `docs/METRICS.md` |
| Cache hit rate | 6 | `docs/METRICS.md` |
| Number of real users who installed the extension | 7+ | `docs/METRICS.md` |
