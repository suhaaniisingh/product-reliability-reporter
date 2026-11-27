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

## 2026-11-23: Caption survey dropped; eval set drafted by case type instead

- **Supersedes:** "Survey real captions before building extraction" (same day).
- **Options:** (1) hand-collect about 30 real captions first and count what they contain; (2) build the eval set directly from the case types we already know about (URL in caption, brand only, link in bio, code only, no store, tricky).
- **Chose:** option 2 (Suhaani's call).
- **Why:** the case types are already known, and the optional `store_url` field covers the captions that don't contain a store, so the survey's answer wouldn't change what gets built. Trade-off: we don't measure how common each case is in real feeds.

## 2026-11-23: Work phase by phase, with an approval gate between phases

- **Chose:** each phase starts with a decision proposal that Suhaani approves, then gets built in small commits, then ends with a report (what was built, metrics, how to verify, known weaknesses, next phase's proposal). The next phase starts only after explicit approval. Any decision that comes up mid-phase and wasn't approved stops the work until Suhaani decides. The plan and status live in `PLAN.md`.
- **Why:** Suhaani has to be able to defend every decision, so none get made silently.

## 2026-11-23: Extraction LLM: Claude Sonnet 5.5, behind an `Extractor` interface

- **Options:** Claude Haiku 5.5 ($0.10 / $0.50 per million input/output tokens), Claude Sonnet 5.5 ($2 / $10), Claude Opus 5.5 ($4 / $20), Google Gemini (possibly a free tier), a local model via Ollama.
- **Chose:** Claude Sonnet 5.5 (`claude-sonnet-5-5`), Suhaani's choice.
  - Called through the official `anthropic` Python SDK with structured outputs (`messages.parse` + the Pydantic model).
  - Low effort, since extraction is a simple task.
  - Anthropic's server-side refusal fallback is on.
- **Why:** a mid-tier model: more capable than Haiku on the judgement-heavy cases (guessing a brand's store, tricky captions) at half Opus's price. At roughly $0.003 per caption, cost doesn't matter at this scale.
- **The interface matters:** the API depends on an `Extractor` protocol, not on the SDK. That allows swapping providers, comparing them on the eval set, and testing offline with a fake.

## 2026-11-23: Guess the store from the brand name, marked as guessed and checked

- **Options:** (1) never guess: `store_url` stays empty unless the caption contains it; (2) guess and present the guess as fact; (3) guess, mark it as guessed, and check it.
- **Chose:** option 3. Suhaani: the project has little value if it can't get from a brand name to a store.
  - The LLM proposes the brand's official domain with `store_url_source: "guessed_from_brand"`, and confidence is capped at `medium`.
  - Code checks the domain exists (DNS lookup) and drops the guess if it doesn't.
  - The eval reports guess accuracy separately.
- **Risks to watch:** the model may invent plausible domains for small brands (the DNS check catches non-existent ones, not wrong-but-real ones). A guess also points to the *official* store, while the video might promote a different seller, which the "guessed" label makes visible.

## 2026-11-23: Eval set: about 30 synthetic captions, drafted by Claude and reviewed by Suhaani

- **Options:** synthetic captions drafted by Claude and reviewed; synthetic plus a few real ones; all written by Suhaani.
- **Chose:** drafted by Claude, with the expected answers reviewed by Suhaani. About 20 rows are used for tuning the prompt and about 10 are held out for the reported number.
- **Why:** fast, and it covers every case type on purpose. Caveat recorded in `docs/EVALUATION.md`: synthetic captions may be cleaner than real ones, so accuracy may be optimistic. Tuning the prompt on the same rows that are reported would inflate the score further, hence the held-out split.

## 2026-11-23: Remove the server-side refusal fallback; use the stable API only

- **Changes:** the "Extraction LLM" entry (same day), which turned on `fallbacks="default"`.
- **Options:** keep the fallback (beta `client.beta.messages.parse` + `fallbacks`), or remove it and call the stable `client.messages.parse`.
- **Chose:** remove it (Suhaani, on Claude's recommendation).
- **Why:**
  - For Sonnet 5.5 the fallback only retries two refusal categories (cybersecurity, help building competing AI models), and product captions don't trigger either. The first 20 live calls had zero refusals.
  - Our own code already handles every refusal: it checks `stop_reason` and returns a clear 502.
  - Dropping it removes a dependency on a beta API, which can change without notice.
- **Lesson worth keeping:** LLM APIs can answer "200 OK" without a usable result (a refusal, a reply cut off at `max_tokens`, or output that doesn't fit the schema). So the extractor checks why the model stopped before trusting the content.

## 2026-11-23: Change an API and its callers together ("expand, then contract")

- **Context:** replacing `/api/check` with `/api/scan` left the web page calling the removed endpoint for five commits (`d6d008c` to `74951b0`). Tests passed throughout, but the page didn't work in those commits.
- **Options:** rewrite history to merge those commits (they aren't pushed), or leave history as is and adopt a rule.
- **Chose:** leave history, adopt the rule. When an API changes shape, either update its callers in the same commit, or first add the new endpoint alongside the old one ("expand"), move the callers over, and only then remove the old one ("contract").
- **Why:** rewriting history would lose the small step-by-step commits. Expand-then-contract is how production teams change APIs without downtime. It will matter more from Phase 4, when a released extension can't be updated at the same moment as the server.

## 2026-11-23: Pushing happens only after a phase is approved

- **Chose:** Claude handles pushing to GitHub, but only after Suhaani explicitly approves that specific phase at the end of its report. Commits stay local until then, and the next phase starts only after the push. Approving one phase never carries over to another.
- **Why:** `origin/main` only ever holds work Suhaani has reviewed and can defend, and each push marks a finished, approved phase.
- **Supersedes:** the "commit directly to `main` and push" part of the 2026-11-12 git workflow entry. Committing directly to `main` still stands.

## 2026-11-24: Trust signals: domain age, blocklist, store-page checks, Shopify detection

- **Chose (Suhaani approved):** four public signals.
  1. **Domain age** via RDAP, the structured JSON successor to WHOIS.
  2. **A blocklist check:** Google Safe Browsing; its terms are verified before building.
  3. **Store-page checks:** return policy, contact details.
  4. **Shopify-template detection.**
- **How each check runs:** each is an independent module with the same interface (value, status ok / failed / timeout, explanation). They run concurrently with their own timeouts, so one failure never breaks a scan.
- **Reviews:** researched separately (see the next entries).

## 2026-11-24: Scoring: start at 50, add or subtract points, each with a reason

- **Options:** a per-fact checklist with no overall score; hard rules or a decision tree; asking an LLM for a verdict; a learned model; additive points.
- **Chose:** additive points from a neutral 50 ("no evidence either way"). Every adjustment carries a reason string. A few combination/override rules sit on top (e.g. a blocklist hit caps the score). The page shows a plain label (low / medium / high trust) next to the number, since the number is not a probability. Confidence drops when signals fail.
- **Why:** it explains itself, needs no labelled data yet, and each rule is one testable line. It has the same shape as logistic regression (a starting value plus a weight per signal), so Phase 3 can compare hand-picked weights against weights learned from labelled stores, F1 vs F1.
- **Known weaknesses:** the weights are judgement calls until Phase 3 measures them; simple adding can miss combinations, which the override rules partly address.

## 2026-11-24: SSRF protection for fetching store pages

- **Context:** the server fetches whatever store a user pastes. A public-looking domain can point to a private or internal address (e.g. the cloud metadata service at 169.254.169.254). Rejecting IPs and `localhost` in the pasted text, which Phase 1 already does, isn't enough.
- **Chose (Suhaani approved):**
  - Resolve the domain and require every address to be public (Python `ipaddress`).
  - Connect to exactly the checked address, which defeats DNS rebinding.
  - Follow redirects manually and re-check each hop, at most 3.
  - http/https on the standard ports only; 5 s timeout; about 2 MB response cap; a few pages per store.
  - Offline tests for each attack.

## 2026-11-24: Cost protection for the public deployment, with a rate limiter written in-house

- **Chose (Suhaani approved), four layers:**
  1. A monthly spend cap in the Claude Console (Suhaani sets it).
  2. A per-IP limit on caption scans (e.g. 10/min, 50/day; looser for store-link-only scans), returning HTTP 429 with `Retry-After`.
  3. A daily global budget on caption scans across all users (e.g. 500/day ≈ $2.25), after which caption scans pause with a message.
  4. The existing caption and output size caps.
- **Rate limiter: written ourselves** rather than using `slowapi`. It's small and fully understood, which makes a good interview topic.
- **Known limits:** counts live in one server's memory. That's fine on a single free instance; several instances would need a shared store such as Redis (Phase 5). The client IP must be read the way the chosen host documents (proxy headers).

## 2026-11-24: No review source; add site popularity (Tranco top 50,000) as a fifth signal

- **Researched:**
  - **Trustpilot:** keys appear to require Trustpilot for Business (paid yearly call allowances) or a partner agreement; no free developer key could be confirmed.
  - **Reddit:** new API access needs approval, and third-party reports say new requests closed 2026-10-31. Reddit's own pages couldn't be read from this environment.
  - **ScamAdviser / APIVoid:** paid or about 20–29 free checks, and it would copy someone else's trust score into ours.
  - **Google reviews:** not researched; online stores often have no listing.
- **Chose (Suhaani):** leave reviews out (Trustpilot stays in the backlog in case a free key exists). Add **Tranco**, a research ranking of popular sites updated daily, as a fifth signal. Keep the **top 50,000** domains, downloaded once a day and looked up locally (no key, no rate limit, small enough for a free host's memory).
- **Scoring:** being on the list adds points with the rank as the reason. Not being on it scores 0, never a penalty, because most honest small shops aren't on it either.
- **Caveat:** one of Tranco's input rankings (Cloudflare Radar) is licensed CC BY-NC (non-commercial). Fine for a portfolio project; revisit if the project is ever commercial.

## 2026-11-24: Cut LLM cost: state each rule once, cache the prompt, cheap evals

- **Context:** about $1 had been spent, mostly on repeated eval runs. Measured: 97% of every request was the same system prompt and answer schema; the caption was ~60 tokens.
- **Chose (Suhaani approved options 1–4):**
  1. An eval answer cache plus a confirmation step before any paid call.
  2. Each prompt rule stated once (no schema descriptions, no docstrings leaking into the schema).
  3. Prompt caching with an explicit marker on the system prompt. Top-level automatic caching would key the cache on the varying caption.
  4. The Batch API for evals.
- **Result:** live cost per caption $0.0045 → $0.0018; an eval run ~$0.19 → ~$0.03, or $0 for unchanged rows. Accuracy kept on dev and test2 after fixing one regression (see EVALUATION.md).
- **Caveat on caching in production:** a cache write costs 1.25× and expires after 5 minutes. With sparse traffic, caching can cost slightly more than no caching. Measure with real traffic in Phase 5 before deciding whether to keep it there.
- **Implementation note:** batch mode builds its schema with the SDK's internal `to_json_output_format` helper, so it is byte-identical to `messages.parse()`. A test locks this in, in case an SDK update moves the helper.

## 2026-11-24: Stay on Claude Sonnet 5.5 for extraction

- **Options:** Sonnet 5.5, or Haiku 5.5 (measured on the same 45 rows: 93% vs 98% all-fields; 0 wrong stores for either; ~16× cheaper; slightly faster).
- **Chose:** stay on Sonnet (Suhaani).
- **Why:** more accurate on the held-out rows. At about $0.0018 per scan after the cost work, it's affordable at portfolio traffic, and the daily budget cap protects against abuse.
- **Revisit:** in Phase 5, with real traffic numbers. Switching is a one-line change behind the `Extractor` interface, and the eval can re-check it for about $0.002.

## 2026-11-24: Code rule: a hashtag matching the store's domain name is the brand

- **Context:** some brand names read like ordinary words (`#cozyknit`), so the model treats them as topic tags even when the store's domain is cozyknitco.com. Prompt changes didn't fix it (5/5 misses).
- **Chose (Suhaani approved):** a deterministic post-processing rule. If the model found no brand and a hashtag equals the store domain's name (ignoring common affixes such as co/shop/store and get/try/shop), that hashtag becomes the brand, with a note giving the reason. A short list of generic hashtags (`#skincare`, `#fyp`, `#ad`, …) never counts. The model's own brand is never overridden.
- **Why:** free (no tokens), gives the same answer every time, unit-tested, and consistent with the policy that the brand must be named in the caption (a hashtag is a mention).
- **Result:** Sonnet 45/45 on all splits, measured from cached answers at $0. The original `test` split isn't a clean measure for this rule, since its row c02 motivated it. Held-out `test2` stays 8/8.

## 2026-11-24: Project name: Social Commerce Reliability Reporter

- **Options:** "Social Commerce Trust Checker" (the working name), "Social Commerce Product Reliability Reporter", "Social Commerce Store Reliability Reporter", "Social Commerce Reliability Reporter".
- **Chose:** **Social Commerce Reliability Reporter**, short form "Reliability Reporter" (Suhaani).
- **Why:** it matches the repo name, and "Reporter" fits an output that is a report with reasons. "Product" was left out because the tool judges the *store* behind a promo, not the product's quality; that would have been misleading. Without "product" the name still fits if a later phase adds product-level checks.
- **Note:** earlier entries in this log keep the name they used at the time.

## 2026-11-24: Blocklist: Google Safe Browsing v4 Lookup API

- **Options:** Safe Browsing v4 Lookup, Safe Browsing v5 (`urls:search`, still labelled alpha), Google Web Risk (paid, for commercial use), community lists (PhishTank needs registration; URLhaus is malware-only).
- **Chose:** v4 Lookup API (Suhaani). Free; the terms allow non-commercial use only ("not for sale or revenue generating purposes"), which fits a portfolio project. Web Risk is the route if the project ever becomes commercial.
- **Key setup:** a Google Cloud project with the Safe Browsing API enabled, and an API key restricted to the Safe Browsing API only. That way a leaked key can't be used for paid Google APIs once billing is enabled for hosting. No application restriction, because Cloud Run's outbound IP isn't fixed. The key lives in `backend/.env` (git-ignored) and is sent in the `x-goog-api-key` header, never in the URL. Verified 2026-11-24 with Google's test pages (malware and phishing flagged, wikipedia.org clean).
- **Rules from the terms that shape the design:**
  - show "Advisory provided by Google" with a link next to any result, and use hedged wording ("suspected", "may")
  - never warn based on a result older than its `cacheDuration` (300 s in testing) or 30 minutes, so this signal's cache TTL in Phase 5 must be short
  - lookups send the URL to Google, which may use and share it, so the page says so in one line

## 2026-11-24: Hosting on Google Cloud

- **Options researched:** Render (free, no card, sleeps after 15 min with ~1 min wake-up), Railway (no card, but only $1/month credit), Fly.io (card needed), Google Cloud Run, the GitHub Student Pack (Heroku/Azure credits).
- **Chose:** Google Cloud (Suhaani), so hosting sits in the same project as the Safe Browsing key. Service: **Cloud Run** (scales to zero, wakes in seconds), confirmed by Suhaani 2026-11-24.
- **Billing:** Cloud Run needs a billing account (card). Its monthly free allowance is reported as 2M requests, 180,000 vCPU-seconds and 360,000 GiB-seconds per billing account (third-party sources; Google's pages couldn't be read from this environment), plus a $300 / 90-day credit for new customers. A budget alert is set before deploying.

## 2026-11-24: The remaining trust-signal and deployment details (approved together)

Suhaani approved all of these at once, before the build started.

- **The page fetcher identifies itself** as `SocialCommerceReliabilityReporter/0.1`. It's an honest bot name with no contact link, so the developer's username doesn't appear in stores' logs (the alternative with a GitHub link was declined). It never pretends to be a browser.
- **It respects `robots.txt`.** If a store disallows us, its page checks report "not checked" rather than fetching anyway.
- **Fetch limits per store:** at most 4 pages (home, return policy, contact), 5 s and 2 MB per page, at most 3 redirects, standard ports only, every hop checked for public addresses (SSRF protection).
- **Return policy and contact detection:** plain text and pattern matching in code: free, instant, deterministic. Having an LLM read policy pages stays in the backlog.
- **Popularity data:** the Tranco list is downloaded when the container is built (refreshed on each deploy, no startup delay). The top 50,000 domains are kept, and the page credits Tranco.
- **New libraries:** `tldextract` (registrable domain via the public suffix list, using its bundled snapshot so it works offline) and `beautifulsoup4` (HTML parsing).
- **Scoring weights** (starting from 50; failed checks score 0 and lower confidence; clamped to 0–100):
  - domain age: <30 d −20 · 30–180 d −10 · 6 mo–2 y 0 · 2–5 y +10 · >5 y +15
  - popularity: top 10k +15 · 10k–50k +10 · not listed 0
  - return policy: found +5, not found −10
  - contact details: found +5, none −10
  - Shopify: 0 (context only)
  - combination: <90 days old with no return policy and no contact −10
  - on Google's unsafe list: capped at 10
- **Labels:** 70–100 "Higher trust", 40–69 "Mixed signals", 0–39 "Lower trust".
- **Confidence:** high if all 5 checks ran, medium if 1 failed, low if 2+ failed or Safe Browsing failed. A store *guessed* from a brand name is still checked, but confidence is capped at medium and a note says the video may link elsewhere.
- **Rate limits per IP:**
  - caption scans: 10/min and 50/day
  - store-link scans: 30/min and 200/day
  - site-wide: 500 caption scans/day
  - Per-minute limits use a token bucket (allows short bursts, holds the average rate); daily limits are plain counters.
- **Web page:** score, label and confidence; the reasons with their points; expandable details per check; "Advisory provided by Google"; a one-line privacy note; the guessed-store warning.
- **Deployment:** a single Dockerfile (builds the page and the API) built by Cloud Build, in `us-central1`, with min 0 / max 1 instances (caps cost and keeps the in-memory rate limits correct with one counting server), 512 MB, keys in Secret Manager, public on the default `*.run.app` address, manual deploy for now. Claude may enable the needed Google Cloud APIs, create the secrets, and deploy.
- **Testing:** up to $0.50 of Claude spend; scans of a few well-known and smaller real stores plus Google's Safe Browsing test page, using only public pages and the limits above.

## 2026-11-24: Deployment details decided while deploying

- **Build permissions:** new Google Cloud projects run Cloud Build as the default compute service account without build permissions, so the first deploy failed with PERMISSION_DENIED. Following Google's documented fix, that account was granted `roles/run.builder`. **Trade-off:** the same account is the running app's identity, so the app carries those permissions too. A dedicated minimal runtime account is in the backlog.
- **Secrets:** `anthropic-api-key` and `safe-browsing-api-key` are in Secret Manager, created straight from `backend/.env` without being displayed. Read access is granted per secret to the runtime account only, and they're mounted as environment variables.
- **Upload safety:** `.gcloudignore` / `.dockerignore` exclude `.env`, caches, tests and docs. The upload list was checked before deploying.
- **Client IP on Cloud Run:** `TRUSTED_PROXY_HOPS=1` (the last `X-Forwarded-For` entry, which Cloud Run appends). Verified live: spoofed headers didn't get around the limit. Separate real visitors getting separate limits rests on community reports and is still to be confirmed from a second network.

## 2026-11-24: Cold starts: lazy SDK import, uvicorn, startup CPU boost, page-triggered warm-up

- **Problem (reported by Suhaani):** the deployed page took 20–30 s to open. Cloud Run logs showed an instance start took 26 s, about 20 s of it importing the app (mostly the Anthropic SDK), before even the static page could be served.
- **Changes (no extra cost):**
  - Import the SDK lazily, since only caption scans need it.
  - Start with `uvicorn` directly instead of the `fastapi run` CLI.
  - `--cpu-boost` (extra CPU during startup only).
  - Add a `GET /api/warmup` endpoint that the page calls when it opens.
- **Result:** start-to-ready 26 s → ~5 s; page 0.8 s; a caption scan made ~10 s after opening the page 3.0 s.
- **Lesson:** a background warm-up thread took 30 s, because with request-based billing Cloud Run gives an instance CPU only while it handles a request. So the warm-up runs *inside* a request instead.
- **Still open:** a visitor arriving after ~15 idle minutes waits ~5 s for the instance to start. Options (keep-warm ping, or `min-instances 1`) were put to Suhaani.

## 2026-11-24: Accept the ~5 s cold start for now

- **Options:** (a) accept ~5 s for the first visitor after ~15 idle minutes, at no cost; (b) a Cloud Scheduler keep-warm ping to `/api/warmup` every 10 minutes (probably ~free, one more moving part); (c) `min-instances 1` (no cold starts, but an always-on instance costs money every month).
- **Chose:** (a) (Suhaani). The app currently has one user, so the extra complexity and cost aren't justified. (b) is in the backlog for when there are real users. Keeping `min-instances 0` is a deliberate cost-versus-latency trade-off.

## 2026-11-24: Changes after Suhaani's first hands-on test

- **Popularity list: top 100,000** (was 50,000), with a new band: ranks 50,000–100,000 score **+5** (top 10k +15, 10k–50k +10, not listed 0). About 10 MB in memory. Effect: cerave.com (rank 88,330) now gets +5.
- **Safe Browsing stays one-sided:** a listing caps the score at 10, and not being listed scores 0. Almost every site, including most new scam shops, isn't listed, so a bonus for "not listed" would shift every score up without telling stores apart. Suhaani agreed.
- **Reading the brand from a video frame:** deferred to the Chrome extension (Phase 4), which can capture the visible frame when the user clicks. The platforms' public endpoints don't provide images, and downloading frames would be scraping. A manual screenshot upload was considered and not built for now; the server side (an LLM reading the image) would be shared by both.

## 2026-11-24: Check that published contact details work

- **Context:** Suhaani asked why contact details weren't checked for being real. Before, any email or phone number on the site counted.
- **Chose (Suhaani approved):** free, deterministic checks:
  - **Email:** the domain must publish mail servers (DNS MX lookup with `dnspython`). A "null MX" or a missing domain fails; a DNS timeout doesn't penalise.
  - **Email context:** the store's own domain, free webmail, or another domain. Context only, since many honest small shops use Gmail.
  - **Phone:** must be a valid number under Google's libphonenumber rules (`phonenumbers`), which also gives the country and line type. Numbers in page text must be valid to count at all, which skips order numbers and prices. Numbers without a country code are read in the store's country (from its country domain, else US).
  - **Where:** each detail records the page it was found on.
  - "Contact found" now means **working** contact; the points are unchanged (+5 / −10).
- **Rejected:** SMTP mailbox probing (unreliable, and treated as spammer behaviour), paid carrier lookups, contacting the store.
- **Limit:** a real Gmail address costs nothing, so this filters out fake-looking details but can't prove trustworthiness.

## 2026-11-26: Direction change: a backend-focused project

- **Decided by:** Suhaani.
- **Chose:** the project's depth moves to **backend engineering**: background jobs, caching and deduplication, retries and per-source limits, a Postgres data model with score history, DevOps, and measured performance. ML becomes a separate, later project.
- **Why:** the target roles are backend / SWE / cloud. A small ML component bolted onto this product would be shallow, while the product genuinely needs the backend pieces: checks are slow and depend on unreliable outside sources, popular stores get checked repeatedly, and score history needs a database.
- **Out of scope now:** training classifiers or learned scoring models, the 200–300-store labelled dataset and the F1 phase, the @handle ML matcher, multimodal extraction (screenshots, OCR, transcription), image-based dropshipping detection, and LLM extraction as the headline (it stays as a caption → store helper).
- **Still in scope:** the trust score from public signals with a reason for every point; a ~100-store validation check (a step, not a phase); the Chrome extension and the paste-link page.
- **Alternatives considered:** (a) making ML the core of this project (a scam-site detector, with the rule score as a baseline); (b) an image-based product matcher; (c) a short-video recommender as a new project. Set aside in favour of a separate ML project.

## 2026-11-26: Only build backend machinery the product needs

- **Rule:** every backend piece must serve something a user notices (speed, reliability, history) or something we must prove. Nothing is added just to show a technology.
- **Kept, with the product reason:**
  - **Background jobs + polling:** a Chrome popup is destroyed when the user clicks away, which kills a waiting request; jobs also let results appear one by one.
  - **Cache per store:** popular stores get checked repeatedly; answers become instant; fewer calls to quota- and rate-limited sources (Safe Browsing, RDAP).
  - **Deduplication:** a viral video sends many viewers to check the same store at the same moment.
  - **Postgres:** score history needs a database.
  - **Retries:** fewer false "couldn't check" results.
  - **Per-source limits:** politeness and quotas.
  - **Load test:** the proof that caching and deduplication work.
- **One datastore: Postgres** for the jobs (`SELECT … FOR UPDATE SKIP LOCKED`), the cache (latest result with an expiry), deduplication (a unique constraint) and history. **No Redis** until a measurement shows a need. *Why:* one thing to run, host for free and explain. *Alternative:* Redis with RQ/Celery/arq: faster for very high job rates, which this project won't have. In production, Postgres-backed queues are common at moderate scale (e.g. Rails' Solid Queue, Elixir's Oban).
- **Polling, not push:** `GET /api/checks/{id}`. *Alternatives:* server-sent events or WebSockets. More moving parts for a check that takes ~5–12 s.
- **Not doing:** Redis, extra services, WebSockets, multiple instances, Kubernetes. Each can be revisited if a measurement shows a need.
- **Table naming: `stores`, not "sellers".** We only ever know a store by its domain; a separate seller record would have no data behind it.
- **The LLM summary is skipped.** The reasons list already explains the score, and a summary adds cost to every check.
- **Extraction eval tooling is frozen,** not deleted. It still backs up the helper's accuracy numbers.

## 2026-11-26: New phase order

- **Order:**
  - 3: DevOps foundation (compose, CI/CD, the server);
  - 4: jobs and data model;
  - 5: reliability and score validation;
  - 6: caching, deduplication and measured performance;
  - 7: extension.
  - Phases 1–2 keep their numbers.
- **Changes from Suhaani's first draft, with reasons:**
  - **CI first.** Tests should run automatically *before* Phase 4 rewires the request flow, not after. Real teams set up CI on day one of a service.
  - **No fake skeleton.** The signals and scorer already exist, so the jobs phase runs the real checks from the start. Retries move to the reliability phase.
  - **Validate the score before caching and history.** If the ~100-store check means the weights must change, better before months of snapshots exist (snapshots also record the scorer version).
  - **Baseline load test immediately before caching**, in the same phase. With the load test last there would be no "before" number.
  - **Keep phase numbers 1–2.** Commit messages and docs refer to them; renumbering would break those references.
- **The server setup and automatic deploys moved into Phase 3** (first proposed for Phase 4) once a self-managed VM was chosen. The server is then ready before the database and the jobs need it, and Phase 4 stays focused on the jobs.

## 2026-11-26: Hosting: a self-managed always-free VM

- **Decided by:** Suhaani.
- **Options:**
  - (a) Cloud Run with "CPU always allocated" billing, a worker inside the app, and a free hosted Postgres;
  - **(b) an always-free VM running our docker-compose**;
  - (c) another free platform host.
- **Chose:** (b). The provider will be picked in Phase 3, after researching current free tiers (limits, reliability, card requirements, rules for reclaiming idle machines).
- **Why:**
  - The worker needs a process that keeps running. Cloud Run, as configured, gives CPU only during requests.
  - A VM runs the app, the worker and Postgres together, exactly as docker-compose does locally.
  - Suhaani wants hands-on DevOps.
  - No cold starts.
- **Trade-offs we take on:**
  - OS security updates, the firewall, HTTPS (a reverse proxy and a domain name), getting secrets onto the server, database backups.
  - Uptime is ours: if the machine goes down, the app goes down.
  - Cloud Run did all of this for us.
- **Transition:** the current Cloud Run deploy stays live until the VM takes over in Phase 3.

## 2026-11-26: DevOps is written by Suhaani; database tests use a real Postgres

- **DevOps:** Suhaani writes `docker-compose.yml`, the GitHub Actions workflows and the server setup. Claude explains each piece first and reviews after. *Why:* she needs to be able to defend and debug this in interviews, which only comes from writing it.
- **Database tests run against a real Postgres** (docker-compose locally, a service container in CI), not mocks. *Why:* a mock can't reproduce locking, constraints, transactions or `SKIP LOCKED`, which is exactly what the queue and deduplication rely on. *Alternative:* SQLite in tests. It behaves differently from Postgres in exactly those areas.

## 2026-11-26: Database access: SQLAlchemy 2.0 + Alembic

- **Decided by:** Suhaani.
- **Chose:**
  - **SQLAlchemy 2.0** in async mode: the ORM for ordinary reads and writes, and its SQL expression layer (Core) where we need specific SQL, e.g. the queue's `with_for_update(skip_locked=True)`.
  - **Alembic** for versioned migrations.
- **Why:** the most widely used Python database stack, and the one job posts name. Migrations make every schema change reviewable and repeatable on every machine and on the server.
- **Alternatives:**
  - raw SQL with psycopg 3 or asyncpg: full control, more hand-written code;
  - SQLModel: a thin layer on SQLAlchemy, less mature;
  - Tortoise ORM: less common.
- **Note:** plain SQL is still written widely in industry: for performance-critical queries, migrations, analytics and debugging. ORMs generate SQL, and reading it (`EXPLAIN`) is part of using one well.
- **The async driver is still open** (asyncpg or psycopg 3). It's decided at the start of Phase 4.

## 2026-11-26: API rename: `/api/scan` → `/api/checks`

- **Chose:** `POST /api/checks` creates a check and returns `202 Accepted` with its ID; `GET /api/checks/{id}` returns its status and results so far. `/api/scan` is removed once the page uses the new endpoints.
- **Why:** a check is now a resource with an ID and a lifecycle, so it has its own URL; 202 is the standard "accepted, still processing" response. The only client is our own page, so there's nothing to stay compatible with.

## 2026-11-26: Extension design: the current tab or selected text, no screenshots

- **Supersedes:** the user-driven capture sessions (planned 2026-11-24), which sent screenshots for an LLM to read. That's multimodal extraction, now out of scope.
- **Chose:** the extension checks the store page in the current tab, or text the user selects and right-clicks ("Check this store").
- **Why:**
  - Least privilege: likely just `activeTab` and `contextMenus`, confirmed in Phase 7.
  - No page reading, so no platform-terms question.
  - No per-capture LLM cost.

## 2026-11-26: Our own job queue, with the worker as a separate container

- **Decided by:** Suhaani.
- **Queue: our own, small, on Postgres `SELECT … FOR UPDATE SKIP LOCKED`**, with a lease so a crashed worker's job gets picked up again.
  - **Why:** the queue is the centre of the project's backend story. Writing it means having solved the questions interviews ask yourself: a worker crashing mid-job, two workers taking the same job, a job running twice.
  - **Honest framing for interviews:** in industry, teams almost always use an existing queue (Celery, RQ, Sidekiq, AWS SQS, or Postgres-based libraries such as procrastinate). This one is written on purpose to learn the mechanics; in production we'd pick a library.
  - **Alternative:** procrastinate or another library. Less code, but the hard parts stay hidden.
- **Worker: a separate container,** started from the same image as the API with a different command (one extra block in docker-compose).
  - **Why:** a slow or crashing check can't freeze the API, and each can be restarted on its own. It's the standard "web + worker" pattern (Celery, Sidekiq, Heroku-style apps).
  - **Alternative:** a worker inside the API process. One less container, but no isolation. The earlier lean towards it only applied to Cloud Run's request-only CPU, which no longer applies on a VM.
- **Also approved:** the server setup and automatic deploys belong to Phase 3.
