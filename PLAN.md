# PLAN.md: Social Commerce Reliability Reporter

> Approved 2026-11-23. A living document: the status table and phase sections are updated after each phase report.

## Context

The project was reframed on 2026-11-23 (see `CLAUDE.md`, `docs/DECISIONS.md`). It is now a pipeline: social video caption → extract product/brand/store → public trust signals → explainable score. Every phase ends with something measurable.

The existing repo is a walking skeleton from the old brief: `POST /api/check` returns a fake 5-signal report, and a React page displays it.

Research on 2026-11-23 showed that TikTok's and Instagram's oEmbed endpoints **no longer return captions or creators**, and Meta's terms forbid extracting them from the embed HTML. So the user pastes the caption and/or the store link. The caption survey step was considered and **dropped**: the eval set is drafted by case type instead.

**Direction change (2026-11-26).** The project is now **backend-focused**; ML is a separate, later project. Out: training models, the large labelled dataset and the F1 phase, multimodal extraction (screenshots, OCR, transcription), dropshipping detection, and LLM extraction as the headline (it stays as a helper). In: background jobs, caching and deduplication, retries and per-source limits, a Postgres data model with score history, DevOps that Suhaani sets up herself, measured performance, a ~100-store validation check, and the extension. Phases 1–2 keep their numbers; the new phases continue from 3. See `CLAUDE.md` and `docs/DECISIONS.md` (2026-11-26).

## How each phase runs (the approval loop)

1. **Propose.** At the start of a phase, I post that phase's decisions: options, my recommendation, and why. Nothing is built until you approve. Approved decisions are logged in `docs/DECISIONS.md`.
2. **Build.** Small commits directly on `main`, with tests passing at every commit. If a decision comes up mid-phase that wasn't approved, I **stop and ask** instead of choosing.
3. **Report.** When the phase is done, I report:
   - what was built (commit list)
   - the phase's metrics
   - how you can run and verify it yourself
   - anything deferred to `docs/BACKLOG.md`
   - known weaknesses
   - the decision proposal for the next phase
4. **Ask, then push.** At the end of the report, I ask whether everything in the phase is okay. Only after you explicitly approve **that specific phase** do I push its commits to GitHub (`origin/main`) and start the next phase. Approval of one phase never carries over to another, and nothing is pushed without it.

| Phase | Status | Key metric |
|---|---|---|
| 1. Caption → store extraction helper | **Approved and pushed 2026-11-24** | Held-out: store 100% on both splits; all fields 90% (test) → 100% (test2, after hashtag fix) |
| 2. Trust signals + rule-based score + first deploy | **Approved and pushed 2026-11-25** (on Cloud Run until 2026-11-27) | Deployed URL returns score + reasons |
| 3. DevOps foundation: containers, CI/CD, the server | **Approved and pushed 2026-11-27** (live at https://reliability-reporter.duckdns.org) | Push → green CI → automatic deploy to the VM over HTTPS |
| 4. Checks as background jobs + data model | Not started | Every check runs as a job and is stored |
| 5. Reliability + score validation | Not started | Per-source failure rate before/after retries; score separation on ~100 stores |
| 6. Caching, deduplication, measured performance | Not started | p95 latency, throughput, cache hit rate (before/after) |
| 7. Chrome extension | Not started | Works on real store and TikTok/Instagram pages |

---

## Phase 1: Extraction pipeline

### Approved decisions (2026-11-23)

- **LLM:** Claude Sonnet 5.5 (`claude-sonnet-5-5`, $2 / $10 per million input/output tokens), behind an `Extractor` interface so it can be swapped.
  - Uses structured outputs: `client.messages.parse()` with the Pydantic model.
  - Uses low effort, since extraction is a simple task (fewer reasoning tokens, lower cost and latency).
  - ~~Server-side refusal fallback~~ removed 2026-11-23 (see DECISIONS): stable API only; `stop_reason` is checked on every reply.
  - API key goes in `.env`, with `.env.example` committed.
- **Input:** `POST /api/scan` takes `{caption?, video_url?, store_url?}`. At least one of `caption` / `store_url` is required. A store link from the user overrides the extracted one. `video_url` is parsed locally (platform, video ID, TikTok handle) with no network call.
- **Brand → store guessing: yes, marked as guessed.**
  - When the caption names a brand but no URL, the LLM proposes the brand's official domain, with `store_url_source: "guessed_from_brand"` and confidence at most `medium`.
  - Code then checks the guessed domain actually exists (DNS lookup). If it doesn't, the guess is dropped and a note is added.
  - The eval reports guess accuracy separately from in-caption accuracy.
- **Never trust the LLM:** an `in_caption` URL must actually appear in the caption, or it is dropped.
- **Eval set:** I draft about 30 English captions across the case types and you review the expected answers. About 20 are used for tuning the prompt and about 10 are held out for the reported number. `EVALUATION.md` notes the caveat that synthetic captions may be easier than real ones.
- **Cleanup:**
  - retire the root `DECISIONS.md` and `OPEN_QUESTIONS.md`
  - log that the survey was dropped
  - rewrite `data/README.md` without the survey step
  - rewrite `README.md`
  - update `CLAUDE.md`'s Phase 1 bullet (wording shown in the report)

### What you need to provide

- **An Anthropic API key, by step 6** (steps 1–5 use recorded responses and need no key).
  - Create it in the Claude Console with a small prepaid credit (about $5 is plenty; API billing is separate from a Claude.ai subscription), and set a spend limit.
  - Put it in `backend/.env` as `ANTHROPIC_API_KEY=...` yourself. Never paste it in chat or commit it.
  - When step 5 is done, I'll pause and ask you to confirm the key is in place before any live call.

### Extraction output schema

```python
class Extraction(BaseModel):
    product: str | None
    brand: str | None
    store_url: str | None
    store_url_source: Literal["in_caption", "user_provided", "guessed_from_brand", "none"]
    mentions_link_in_bio: bool
    discount_code: str | None
    confidence: Literal["high", "medium", "low"]
    notes: str
```

Response: `{ "video": {platform, video_id, creator_handle} | null, "extraction": Extraction }`. Errors: 422 for invalid input, 502 when the LLM provider fails.

### Case types in the eval set (`data/extraction_eval.csv`, `case_type` column)

| Case type | What the caption looks like |
|---|---|
| `explicit_url` | The store domain is in the caption |
| `brand_only` | A brand is named; the expected answer is the official domain (tests guessing) |
| `link_in_bio` | Points to the bio, with or without a brand |
| `code_only` | A discount code only |
| `no_store` | No store mentioned |
| `tricky` | Linktree / link-aggregator URLs, an unrelated URL (charity, music), several products, a misspelled brand |

The cases where the user supplies their own store link don't involve the LLM, so they're covered by API tests, not the eval.

### Build steps (one commit each)

1. **Cleanup** (as approved above) + commit `CLAUDE.md`, `docs/`, `PLAN.md`.
2. **`/api/scan` skeleton:**
   - new request/response models in `backend/app/schemas.py`
   - route in `backend/app/routes/scan.py`, replacing `routes/check.py` and `tests/test_check.py`
   - a `FakeExtractor` injected via `Depends`
   - `create_app()` in `backend/app/main.py` is kept; only the router changes
3. **`backend/app/extraction/video_url.py`** (`parse_video_url`) and a basic `normalize_store_url`, with parametrized tests.
4. **`Extractor` protocol + Claude implementation** (`extraction/extractor.py`, `prompt.py`).
   - Add the `anthropic` dependency through uv.
   - Before writing the code, read the Python SDK docs in the claude-api skill for the exact `messages.parse` / fallback usage.
   - Tests use recorded responses in `backend/tests/fixtures/` (valid, malformed, refusal, timeout). No live calls.
5. **Post-processing** (`extraction/postprocess.py`): the in-caption guard, the DNS check for guessed domains (behind a small interface so tests use a fake resolver), merging with the user's link, and the confidence cap. Tests for each rule.
6. **Eval set + eval script:**
   - I draft `data/extraction_eval.csv` and you review it.
   - `backend/scripts/eval_extraction.py` prints: per-field accuracy, accuracy per case type, guess accuracy, the false-URL rate, accuracy per confidence bucket, average latency and cost.
   - Results are written to `docs/EVALUATION.md`.
7. **Web page:** `web/src/App.tsx`, `api.ts`, `types.ts` get a caption box, a store-link box and an optional video link, and show the extraction (with a "guessed" badge for guessed domains).
8. **`README.md` rewrite.**

### Done when

- the scan works end to end locally (page → API → Claude → page)
- `uv run pytest` passes with no network access
- the eval script prints accuracy on the held-out set

---

## Phase 2: Trust signals + rule-based score (outline; decisions proposed at phase start)

- **Decisions I'll propose:**
  - the signal fetcher interface (value, status ok/failed/timeout, explanation)
  - the HTTP client
  - the domain age source (RDAP)
  - the blocklist (Google Safe Browsing vs. alternatives, terms checked)
  - which store-page checks to run (return policy, contact info, Shopify template) and how to fetch pages politely
  - a review source, only if a permitted API exists
  - scoring rules and confidence
  - the free host (researched then)
- **Done when:** a deployed URL returns a score with reasons for a real store.

## Phase 3: DevOps foundation: containers, CI/CD, the server

Suhaani writes the DevOps files and sets up the server; Claude explains each piece first and reviews after.

- **Decided (2026-11-26, see DECISIONS):**
  - **The server:** a Google Cloud e2-micro VM (~$3.65/month for its IPv4 address), Ubuntu 24.04 LTS.
  - **Securing it:** SSH keys only, no root login, automatic security updates, a cloud firewall allowing only 22/80/443, and Postgres never exposed.
  - **Setting it up:** by hand first, recorded in `docs/DEPLOY.md`, then a bootstrap script.
  - **HTTPS:** Caddy, on a DuckDNS subdomain.
  - **Shipping code:** CI builds the image, pushes it to GHCR tagged with the commit ID, then deploys over SSH. Rollback = the previous tag.
  - **Secrets:** a `.env` file on the VM, placed by hand; CI holds only the deploy key and the registry token.
  - **CI:** ruff, pytest with a Postgres service container, web lint + build, then a deploy job on `main` only.
- **Build order:**
  1. docker-compose locally (`api` + `postgres`, memory limits, health checks)
  2. the CI workflow
  3. setting up the server by hand + the runbook
  4. Caddy + DuckDNS
  5. the deploy job
  6. retire Cloud Run (service, images, the extra role)
- **Done when:** a push to `main` runs CI and, when green, deploys to the VM, which serves the app over HTTPS. Cloud Run is retired.

## Phase 4: Checks as background jobs + data model (outline)

- **Already decided (2026-11-26):** Postgres for jobs, cache and history (no Redis); our own small queue; the worker as a separate container from the same image; polling (no push); SQLAlchemy 2.0 + Alembic; `/api/scan` → `/api/checks`; a `stores` table (not "sellers"); database tests against a real Postgres.
- **Decisions I'll propose:**
  - the schema: tables, keys, indexes, what each row means
  - the queue's details: we write our own on `SKIP LOCKED` (decided 2026-11-26); leases for jobs whose worker crashed, retries, what happens when a job runs twice
  - the async database driver
  - the API shape: statuses, partial results, errors
  - how the page polls (interval, when to stop)
- **Done when:** the deployed app runs checks as jobs and stores every result.

## Phase 5: Reliability + score validation (outline)

- **Decisions I'll propose:**
  - which errors are retried (transient only), how many times, and the backoff with jitter
  - per-source concurrency limits
  - the structured log format and what gets logged
  - more blocklists, if their terms allow (URLhaus, PhishTank, OpenPhish researched first)
  - where the ~100 known-scam and known-legit stores come from, and how to handle scam sites that have already gone offline
- **Done when:** the per-source failure rate (before/after retries) and the score-separation numbers are recorded.

## Phase 6: Caching, deduplication, measured performance (outline)

- **First step:** a baseline load test before changing anything.
- **Decisions I'll propose:**
  - the load-test tool (k6 or Locust) and the traffic mix
  - cache expiry per signal (Safe Browsing minutes to hours; domain age days)
  - how deduplication works when two checks of one store arrive together
  - how the page shows score history and "checked X ago / re-check"
- **Done when:** before/after p95 latency, throughput and cache hit rate are in `docs/METRICS.md`.

## Phase 7: Chrome extension (outline)

- **Design (2026-11-26):** check the store page in the current tab, or right-click selected caption text → "Check this store". This replaces the screenshot capture sessions (multimodal extraction is out of scope).
- **Decisions I'll propose:**
  - permissions (expected: `activeTab` and `contextMenus`), with an explanation of each
  - the build tooling
  - how the popup calls the API and keeps the check ID when the popup closes
- **Done when:** an unpacked extension works on real store pages and TikTok/Instagram pages.

---

## Verification (Phase 1)

- `cd backend && uv run pytest -v`, all passing, with no `ANTHROPIC_API_KEY` set. This proves the tests make no live calls.
- `cd backend && uv run python scripts/eval_extraction.py` prints the metrics table (live calls, costs about $0.10).
- Manual check: `uv run fastapi dev app/main.py` + `npm run dev`, then try one caption of each case type plus a store-link-only scan, and check the result and the "guessed" badge.
- `cd web && npm run lint && npm run build`.
