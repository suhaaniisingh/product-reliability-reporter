# Social Commerce Reliability Reporter

Tells a shopper whether the store behind a TikTok/Instagram product promo looks trustworthy, and **why**. Paste the video's caption (or the store link). The system works out the product, brand and store, then (from Phase 2) collects public trust signals about that store and returns an explainable score.

> **Status: Phase 3 (DevOps foundation): live at https://reliability-reporter.duckdns.org**, deployed automatically from `main` by CI/CD. Caption or store link → store → five public trust checks → a score out of 100 with the reasons behind every point. See [`PLAN.md`](PLAN.md) for the plan and status.

## How it fits together

```
Browser ──▶ web page (React + TS) ──POST /api/scan──▶ FastAPI
                                                        │
                    video link ──▶ parse_video_url()    │  (no network: platform, video ID, handle)
                    caption    ──▶ ClaudeExtractor      │  (Claude Sonnet 5.5, structured output)
                               ──▶ apply_rules()        │  (code checks on the model's answer, DNS check for guesses)
                    store link ──▶ normalize_store_url()│  (the user's link always wins)
                                                        ▼
                    store ─────▶ run_signals()          │  (5 checks at once, each with a time limit)
                                   domain age (RDAP) · Google Safe Browsing · store pages
                                   (SSRF-safe fetcher, robots.txt) · Shopify · popularity (Tranco)
                               ──▶ score_signals()        │  (start at 50, points with reasons, cap, confidence)
                                                        ▼
                                  { video, extraction, trust } JSON
```

Every scan first passes a rate limiter (per-visitor token bucket, daily caps, a site-wide daily budget for caption scans).

Why the caption has to be pasted: TikTok's and Instagram's official oEmbed endpoints no longer return captions or creators, and Meta's terms forbid extracting them from the embed HTML (checked 2026-11-23; see `docs/DECISIONS.md`).

| Path | What's there |
|---|---|
| `backend/app/routes/scan.py` | `POST /api/scan` and its error mapping (422 / 502 / 503) |
| `backend/app/scan.py` | Orchestration: which steps run for which input |
| `backend/app/extraction/` | `base.py` (Extractor interface), `claude.py` + `prompt.py` (the LLM call), `postprocess.py` (rules), `video_url.py`, `store_url.py`, `domain_check.py`, `fake.py` (test doubles) |
| `backend/app/signals/` | The trust checks: `base.py` (interface), `runner.py` (concurrency, timeouts), `fetcher.py` (SSRF-safe page fetching), `domain_age.py`, `safe_browsing.py`, `store_pages.py`, `popularity.py` |
| `backend/app/scoring.py` | Turns check results into a score with reasons |
| `backend/app/ratelimit.py` | In-house rate limiter (token bucket + daily caps) |
| `backend/scripts/eval_extraction.py` | Extraction accuracy on `data/extraction_eval.csv` |
| `backend/scripts/fetch_tranco.py` | Downloads the popularity list (run at build time) |
| `Dockerfile` | One image: builds the page, serves page + API |
| `compose.yaml`, `compose.prod.yaml` | The app + Postgres together (local), plus Caddy/HTTPS and the CI-built image (server) |
| `.github/workflows/ci.yml` | CI/CD: lint, tests, web build; on `main`, build the image and deploy |
| `deploy/` | Server setup script and Caddy config |
| `docs/DEPLOY.md` | How the server is set up, deployed to, and rolled back |
| `web/` | React + TypeScript page (Vite, Tailwind CSS) |
| `PLAN.md` | Phase-by-phase plan and status |
| `docs/DECISIONS.md` | Every design decision, the options considered, and why |
| `docs/BACKLOG.md` | Ideas parked for later phases |
| `docs/EVALUATION.md` | Measured results |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager). It installs Python 3.14 automatically if needed.
- [Node.js](https://nodejs.org/) 20+ with npm.
- An Anthropic API key, only for scans that include a caption and for the eval script.

## Setup (once)

```bash
cd backend && uv sync      # creates backend/.venv and installs Python dependencies
cp .env.example .env       # then put your API keys in backend/.env (git-ignored)
uv run python -m scripts.fetch_tranco   # download the popularity list (once)
cd ../web && npm install   # installs web dependencies into web/node_modules
```

Without keys, everything still runs: caption scans return a clear 503 message, and the Safe Browsing check reports "not configured".

## Run in development (two terminals)

```bash
# Terminal 1: API on http://localhost:8000 (auto-reloads on save)
cd backend
uv run fastapi dev app/main.py

# Terminal 2: web page on http://localhost:5173 (instant reload on save)
cd web
npm run dev
```

Open **http://localhost:5173**. The Vite dev server forwards every `/api/...` request to the API on port 8000 (configured in `web/vite.config.ts`), so the browser sees a single origin and no CORS setup is needed.

Interactive API docs: **http://localhost:8000/docs**

## Run like production (one process)

```bash
cd web && npm run build                       # compiles the page into web/dist/
cd ../backend && uv run fastapi run app/main.py
```

Open **http://localhost:8000**. FastAPI serves both the API (`/api/...`) and the compiled page (`/`).

## Run with Docker (the app + Postgres, as on the server)

```bash
docker compose up --build    # then open http://localhost:8000; Ctrl+C to stop
```

Needs Docker Desktop, `backend/.env` (API keys) and a root `.env` with `POSTGRES_PASSWORD=...` (both git-ignored).

## Deploy

Automatic: every push to `main` that passes CI is built into an image, published to GitHub Container Registry, and deployed to the Google Cloud e2-micro server over SSH, then smoke-tested over HTTPS. Server setup, secrets and rollback are in [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Tests, checks and eval

```bash
cd backend && uv run pytest -v   # all offline: fake extractor, fake DNS, fake websites, recorded API responses
cd web && npm run lint           # lint the web code
cd web && npm run build          # also type-checks all TypeScript

cd backend
uv run python -m scripts.eval_extraction --dry-run --split all   # check the eval CSV, no API calls
uv run python -m scripts.eval_extraction --split test            # live: the reported accuracy (needs the key)
```

## Example request

```bash
curl -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d '{"caption": "Obsessed w this serum 😍 code GLOW20 at glowlabskin.co",
       "video_url": "https://www.tiktok.com/@anna/video/7301234567890123456"}'
```

Example response (illustrative; the model's exact wording varies):

```json
{
  "video": { "platform": "tiktok", "video_id": "7301234567890123456", "creator_handle": "anna" },
  "extraction": {
    "product": "serum",
    "brand": null,
    "store_url": "https://glowlabskin.co",
    "store_url_source": "in_caption",
    "mentions_link_in_bio": false,
    "discount_code": "GLOW20",
    "confidence": "high",
    "notes": ""
  }
}
```

- **Request:** at least one of `caption` or `store_url` is required; `video_url` is optional.
- **`store_url_source`:** `in_caption`, `user_provided`, `guessed_from_brand` (a guess from the brand name, checked to exist in DNS, never above `medium` confidence), or `none`.
- **`confidence`:** how sure we are that `store_url` is the store actually being promoted.
- **Errors:** 422 invalid input · 502 the LLM provider failed or returned something unusable · 503 no API key configured.
