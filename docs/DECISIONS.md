# Decisions

One short entry per decision: the date, what we chose, why, and the alternatives we considered. Newest entries are at the bottom.

> Entries dated 2026-11-11 to 2026-11-13 were made under the original project brief (trust report with five fixed signals, payment guidance). They were copied here from the old root `DECISIONS.md`. Phase numbers in those entries refer to the old roadmap. The tooling decisions in them (FastAPI, uv, React + TypeScript, Vite proxy, `/api` prefix, committing to `main`) still stand unless a later entry supersedes them.
---

## 2026-11-11: Backend language and framework: Python + FastAPI

- **Options:** Python + FastAPI, Python + Flask, Node + Express/TypeScript.
- **Chose:** Python + FastAPI.
- **Why:** Later phases are scraping, LLM extraction, and possibly ML, and Python has the strongest ecosystem for all three. FastAPI adds type-hint-driven request validation (via Pydantic), auto-generated OpenAPI docs at `/docs`, and async support for running signal checks in parallel later (Phase 6).

## 2026-11-11: Python version and tooling: Python 3.14 + uv

- **Options:** uv, Poetry, pip + venv + requirements.txt.
- **Chose:** Python 3.14, managed with uv (`pyproject.toml` + `uv.lock`, virtualenv in `backend/.venv`).
- **Why:** uv is fast, handles the virtualenv and the lockfile in one tool, and uses the standard `pyproject.toml`. The lockfile pins exact versions so the app installs the same way on any machine or container. 3.14 is the current stable Python.

## 2026-11-11: Repo structure: one repo, one folder per component

- **Options:** a single repo with `backend/`, `web/`, `extension/` folders, or separate repos per component.
- **Chose:** a single repo (`backend/`, `web/`, later `extension/`).
- **Why:** It's a solo project and the clients are thin wrappers over one API, so keeping them together makes it easy to change the API and its callers in a single commit. Separate repos would add coordination overhead with no benefit at this size.

## 2026-11-11: Web page frontend: React + TypeScript

- **Options:** plain HTML + JS (no build step), React + TypeScript.
- **Chose:** React + TypeScript (recommended alternative was plain HTML/JS).
- **Why:** This matches how production frontends are built, and the UI will grow (signal cards, sources, summaries, later video mode). TypeScript also lets the frontend define a typed version of the report contract, which catches mismatches with the API at compile time. The cost is a build toolchain (bundler, `npm`) at the skeleton stage.

## 2026-11-11: Serving the page: FastAPI serves the frontend

- **Options:** FastAPI serves the page as static files (same origin), or a separate static server (needs CORS).
- **Chose:** FastAPI serves the page.
- **Why:** One process and one origin, so the browser's same-origin policy never gets in the way and there's no CORS configuration. (The Chrome extension's needs are a separate question for Phase 4: Manifest V3 extension pages with host permissions aren't subject to CORS, but content scripts are.)

## 2026-11-11: React dev setup: Vite + npm, with a dev proxy to FastAPI

- **Options:** (1) Vite dev proxy, (2) CORS middleware in FastAPI allowing `localhost:5173`, (3) no dev server, rebuilding and serving through FastAPI on every change.
- **Chose:** Vite (scaffolding, dev server, build) with npm, and Vite's dev proxy forwarding API requests to FastAPI on `:8000`.
- **Why:** During development the page (`:5173`) and API (`:8000`) are different origins, so the browser would block the page from reading API responses. With the proxy, the browser only ever talks to `:5173`, and Vite forwards API calls server-to-server, where the same-origin policy doesn't apply. The frontend code calls a relative path (`/check`) that works unchanged in dev and production. It mirrors production setups where a reverse proxy (nginx, a load balancer) puts frontend and API behind one domain. Option 2 would need a dev-only CORS rule plus an environment variable for the API address. Option 3 loses instant reload.

## 2026-11-11: Public repo contents: commit `CLAUDE.md`, keep personal background local

- **Options:** commit `CLAUDE.md` as-is, keep it out of git entirely, or commit it with personal background moved to a git-ignored `CLAUDE.local.md`.
- **Chose:** the last one.
- **Why:** `CLAUDE.md` is project documentation (how we work, design principles, roadmap), and it shows a deliberate process to anyone reading the repo. The "About me" section is personal context the project doesn't need. Claude Code still loads `CLAUDE.local.md` automatically, so no context is lost.

## 2026-11-11: Git workflow: feature branches + PRs, first commit on `main`

- **Options:** commit straight to `main`, one branch per phase, or one branch per feature.
- **Chose:** one branch per feature (e.g. `feature/check-endpoint`), merged into `main` via a pull request with a regular merge commit. Only the initial setup commit goes directly to `main`.
- **Why:** `main` always stays working, failed experiments can be thrown away, and each PR documents one feature (what and why), which mirrors how teams work and makes the history readable. Per-feature branches are smaller and easier to review than per-phase ones. Regular merges keep the individual small commits visible. This also sets up CI (GitHub Actions) running tests on each PR later.

## 2026-11-11: Testing approach: pytest + FastAPI TestClient

- **Options:** pytest + TestClient, manual testing only for now.
- **Chose:** pytest with FastAPI's `TestClient`.
- **Why:** `TestClient` calls the app in-process without starting a server, so tests are fast and need no setup. We start with a valid-URL test and an invalid-URL (422) test, then add tests per signal module as they're built.

## 2026-11-12: API paths live under `/api`

- **Options:** `/api/check`, bare `/check`, versioned `/api/v1/check`.
- **Chose:** `/api/check` (all API routes under `/api`).
- **Why:** FastAPI will also serve the React page at `/`, so a prefix keeps page routes and API routes from colliding, and the Vite dev proxy is a single rule ("forward `/api`"). Versioning (`/api/v1`) can be added when a breaking change actually needs it, e.g. once released extension versions depend on the current shape.

## 2026-11-12: Backend layout: small `app` package

- **Options:** a small package split by responsibility, or a single `main.py` until it hurts.
- **Chose:** `backend/app/` with `main.py` (creates the app), `schemas.py` (Pydantic request/report models), and `routes/` (one file per group of endpoints). A `signals/` package joins in Phase 2.
- **Why:** It sets the pattern each signal module will follow, and avoids a reshuffle a few weeks in. Keeping the report contract in one file (`schemas.py`) makes it the single place to look when the shape changes.

## 2026-11-12: Git workflow revised: everything on `main`, no branches, no PRs

- **Supersedes:** the 2026-11-11 feature branches + PRs decision.
- **Options:** feature branches + PRs, feature branches merged locally, or committing directly to `main`.
- **Chose:** commit directly to `main` and push. No feature branches, no pull requests.
- **Why:** Simplest workflow for a solo project, and learning the branch/PR process isn't a goal here. The tradeoff is that `main` has no buffer against half-finished work, so commits stay small and only go in once tests pass.

## 2026-11-13: Web page styling: Tailwind CSS

- **Options:** plain CSS (recommended at the time), Tailwind CSS, a component library (shadcn/ui, MUI).
- **Chose:** Tailwind CSS v4 (via its Vite plugin).
- **Why:** Utility classes are written directly in the JSX, so styling stays next to the markup it affects, and it's widely used in industry. Each class maps to a single CSS property (`px-4` = horizontal padding), so it still teaches the underlying CSS concepts, unlike a component library that hides them. Tailwind only ships the classes actually used, so the CSS stays small (~3 KB gzipped).

## 2026-11-23: Project reframed around extraction, public signals and an explainable score

- **Options:** (1) keep the original brief: a store trust report with five fixed signals, safe-payment guidance, and the video-to-seller step left for late in the roadmap; (2) the reframed brief: video caption → extract product/brand/store → public trust signals → explainable score, with a measurable result at the end of every phase.
- **Chose:** option 2. The payment layer (escrow, protected checkout, payment tips) is removed completely, and so is any use of private seller data such as sales history or purchase counts. Only public signals are used.
- **Why:** This is a portfolio project for internship recruiting, so each phase has to produce a number someone can check (extraction accuracy, F1, p95 latency, cache hit rate). Payments added legal and product scope without engineering depth that could be measured. Private seller data isn't available to us and couldn't be collected without breaking platform terms. Extraction moves to Phase 1 because it is the entry point the rest of the pipeline depends on, and it can be evaluated offline against a labelled set.
- **Consequences:** the existing `POST /api/check` fake report and its five signal names come from the old brief and will be replaced (plan agreed before any code changes). Ideas from the old brief that are still useful went into `docs/BACKLOG.md` instead of being dropped.

## 2026-11-23: Survey real captions before building extraction

- **Options:** (1) build the extraction pipeline first and collect eval captions afterwards; (2) collect about 30 real promo captions first and count what they actually contain (store URL, brand only, "link in bio", TikTok Shop, discount code only, nothing).
- **Chose:** option 2, as step 0 of Phase 1. The same captions then become the labelled eval set, so the work isn't wasted.
- **Why:** the whole pipeline assumes captions contain the store. Creators often put links in their bio because caption links usually aren't clickable, and TikTok Shop products have no store domain at all. If most captions lack a store, the design has to change, and that's cheaper to find out before writing code. It also gives a measured basis for the input design that can be explained in an interview.

## 2026-11-23: `POST /scan` accepts an optional `store_url` from the user

- **Options:** (1) caption only, always run LLM extraction; (2) add an optional `store_url` field on the same endpoint; (3) a separate endpoint for checking a store directly.
- **Chose:** option 2. At least one of `caption` or `store_url` is required. A store URL supplied by the user takes priority over an extracted one (`store_url_source: "user_provided"`). If only `store_url` is sent, no LLM call is made.
- **Why:** it covers the "link in bio" and no-URL cases: the user opens the bio link and pastes it. Scans also keep working when extraction fails (graceful degradation). Later, Phase 2 signals can be tested on known stores without depending on extraction quality. A single endpoint keeps one request/response shape for the web page and the extension. A separate endpoint (option 3) would duplicate the response contract for little benefit.
- **Consequence:** a basic store-URL normalizer moves into Phase 1, because users will paste `glowlab.co` without `https://`. Full normalization (tracking parameters, registrable domain) stays in the Phase 2 backlog item.
