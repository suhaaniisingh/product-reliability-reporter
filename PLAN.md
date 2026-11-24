# PLAN.md: Social Commerce Trust Checker

> Approved 2026-11-23. A living document: the status table and phase sections are updated after each phase report.

## Context

The project was reframed on 2026-11-23 (see `CLAUDE.md`, `docs/DECISIONS.md`). It is now a pipeline: social video caption → extract product/brand/store → public trust signals → explainable score. Every phase ends with something measurable.

The existing repo is a walking skeleton from the old brief: `POST /api/check` returns a fake 5-signal report, and a React page displays it.

Research on 2026-11-23 showed that TikTok's and Instagram's oEmbed endpoints **no longer return captions or creators**, and Meta's terms forbid extracting them from the embed HTML. So the user pastes the caption and/or the store link. The caption survey step was considered and **dropped**: the eval set is drafted by case type instead.

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
4. **Wait.** The next phase starts only after you explicitly approve.

| Phase | Status | Key metric |
|---|---|---|
| 1. Extraction pipeline | Decisions approved 2026-11-23, ready to build | Extraction accuracy (per field, per case type) |
| 2. Trust signals + rule-based score | Not started | Deployed URL returns score + reasons |
| 3. Labelled dataset + evaluation | Not started | F1: rules vs. learned model |
| 4. Chrome extension | Not started | Works on real TikTok/Instagram pages |
| 5. Systems hardening | Not started | p95 latency, cache hit rate (before/after) |
| 6. Stretch | Not started | TBD |

---

## Phase 1: Extraction pipeline

### Approved decisions (2026-11-23)

- **LLM:** Claude Sonnet 5.5 (`claude-sonnet-5-5`, $2 / $10 per million input/output tokens), behind an `Extractor` interface so it can be swapped.
  - Uses structured outputs: `client.messages.parse()` with the Pydantic model.
  - Uses low effort, since extraction is a simple task (fewer reasoning tokens, lower cost and latency).
  - Server-side refusal fallback (`fallbacks: "default"`) is on by default, and `stop_reason` is checked.
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

## Phase 3: Labelled dataset + evaluation (outline)

- **Decisions I'll propose:** label sources for 200–300 stores (public scam-domain lists plus known-legit stores), the feature set, the train/test split or cross-validation, and the learned model (e.g. logistic regression).
- **Done when:** precision, recall, F1 and a confusion matrix are reproducible for both the rules and the model, written up in `docs/EVALUATION.md`.

## Phase 4: Chrome extension (outline)

- **Decisions I'll propose:**
  - the permissions needed, with an explanation of each
  - how the caption is obtained (a terms check on reading the page first; see BACKLOG)
  - the build tooling
  - how the popup calls the deployed API
- **Done when:** an unpacked extension works on real TikTok and Instagram pages.

## Phase 5: Systems hardening (outline)

- **First step:** measure baseline p95 latency with a load-test script before changing anything.
- **Decisions I'll propose:**
  - the job model (async jobs, parallel fetchers)
  - timeout and retry policy
  - the cache store and TTLs
  - deduplication of concurrent scans of the same domain
  - rate limiting
  - whether Postgres/Redis are needed and their free hosting
- **Done when:** before/after p95 latency and cache hit rate are recorded in `docs/METRICS.md`.

## Phase 6: Stretch (outline)

- Research options for dropshipping/markup detection (e.g. CLIP image embeddings) and a PWA share target, then discuss before building anything.

---

## Verification (Phase 1)

- `cd backend && uv run pytest -v`, all passing, with no `ANTHROPIC_API_KEY` set. This proves the tests make no live calls.
- `cd backend && uv run python scripts/eval_extraction.py` prints the metrics table (live calls, costs about $0.10).
- Manual check: `uv run fastapi dev app/main.py` + `npm run dev`, then try one caption of each case type plus a store-link-only scan, and check the result and the "guessed" badge.
- `cd web && npm run lint && npm run build`.
