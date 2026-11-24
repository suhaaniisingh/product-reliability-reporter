# Social Commerce Trust Checker (working title)

Tells a shopper whether the store behind a TikTok/Instagram product promo looks trustworthy, and **why**. Paste the video's caption (or the store link), and the system extracts the product, brand and store, collects public trust signals about the store, and returns an explainable score.

> **Status: Phase 1 (extraction pipeline) in progress.** See [`PLAN.md`](PLAN.md) for the phase plan and status. The code below is still the earlier walking skeleton: `POST /api/check` returns the same placeholder report for every URL, and it is being replaced by `POST /api/scan`. This README is rewritten at the end of Phase 1.

## How it fits together

```
 Browser ──▶ web page (React + TypeScript) ──POST /api/check──▶ API (Python + FastAPI) ──▶ report JSON
```

- **`backend/`**: FastAPI app. `POST /api/check` takes `{"url": "..."}`, validates it, and returns a report.
- **`web/`**: React + TypeScript page (Vite, Tailwind CSS) with a paste box that calls the API and renders each signal.
- **`PLAN.md`**: the phase-by-phase plan and current status.
- **`docs/DECISIONS.md`**: every design decision, the options considered, and why.
- **`docs/BACKLOG.md`**: ideas parked for later phases.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager). It installs Python 3.14 automatically if needed.
- [Node.js](https://nodejs.org/) 20+ with npm.

## Setup (once)

```bash
cd backend && uv sync      # creates backend/.venv and installs Python dependencies
cd ../web && npm install   # installs web dependencies into web/node_modules
```

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

## Tests and checks

```bash
cd backend && uv run pytest -v   # API tests (validation, report shape, page serving)
cd web && npm run lint           # lint the web code
cd web && npm run build          # also type-checks all TypeScript
```

## Example request

```bash
curl -X POST http://localhost:8000/api/check \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example-store.com"}'
```

```json
{
  "store_url": "https://example-store.com/",
  "signals": {
    "business_age": { "status": "warning", "detail": "Website created 3 weeks ago" },
    "business_transparency": { "status": "warning", "detail": "No address or phone listed" },
    "shipping_policy": { "status": "warning", "detail": "Ships from overseas, 15–30 days" },
    "independent_reviews": { "status": "unknown", "detail": "No independent reviews found" },
    "photo_origin": { "status": "danger", "detail": "Photos match AliExpress listings" }
  }
}
```

Statuses: `good`, `warning`, `danger`, `unknown` ("not enough information" is a valid answer).

## Roadmap

See [`PLAN.md`](PLAN.md).
