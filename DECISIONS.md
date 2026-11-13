# Decisions

One short entry per decision: what we chose, what else we considered, and why.

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

## 2026-11-12: Git workflow revised: commit directly to `main`, no PRs

- **Supersedes:** the 2026-11-11 feature branches + PRs decision.
- **Options:** keep feature branches + PRs, or commit directly to `main` and push.
- **Chose:** commit directly to `main` and push.
- **Why:** Learning the PR workflow isn't a goal for this project, and for a solo repo the extra steps add overhead without a reviewer to benefit. The cost is that `main` can briefly hold half-finished work, so we keep commits small and only commit when tests pass.
