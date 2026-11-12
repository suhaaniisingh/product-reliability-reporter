# Project Brief: Social Commerce Trust Checker (working title)

> **For the coding agent:** This is the starting context for a project that is still being defined. It describes the current thinking, not a fixed spec. Treat everything here as a starting point that can change. Your job is to help me build it step by step **and** help me shape it as we go. When something is unclear, undecided, or could reasonably go more than one way, **ask me** instead of choosing for me.

---

## 1. How we work together (read this first)

This is the most important section. The product and the technical approach are both still evolving.

- **Ask before deciding.** For any decision that shapes the product or the codebase (libraries, folder structure, data sources, scoring logic, UI, storage, deployment), give me 2–3 options with tradeoffs, recommend one, and wait for my answer. Small, obvious implementation details don't need a question.
- **Keep asking what I want.** The specs are incomplete on purpose. As we build, raise questions about what the product should do. If something in this brief seems wrong, outdated, or contradicts what we've discussed, say so.
- **Explain the why.** I'm building this to learn and to be able to explain every decision in interviews. When you write or change code, explain what it does, why this approach, and how it connects to how real production systems work. Go step by step.
- **Small steps.** Build in small, working increments. Don't build ahead of what we've agreed on. Check in at the end of each step before starting the next one.
- **Let me stay in the loop.** If I ask a follow-up about something unclear, stop and explain it properly before moving on.
- **Keep a running record.** Maintain two files in the repo:
  - `DECISIONS.md`: each decision we make, the options we considered, and why we chose what we did (one short entry per decision, dated).
  - `OPEN_QUESTIONS.md`: things that are still undecided. Add to it when questions come up, and remove items once they're resolved.
- **Be honest about limits.** If a data source is blocked, an API has restrictive terms, or an idea won't work well, tell me directly rather than working around it silently.

### Keeping this file current
- This file (CLAUDE.md) is the source of truth for the project's current state.
- At the end of each milestone, or whenever we make a decision that changes anything written here, propose an update to this file. Show me the exact changes and wait for my approval before editing it.
- Keep this file a summary of where things stand now. Detailed history and reasoning go in `DECISIONS.md`; unresolved items go in `OPEN_QUESTIONS.md`.
- If the file is getting long, suggest what to trim or move into `docs/`.
- Never change sections 1 (How we work together) or 4 (Design principles) without my explicit approval.

---

## 2. The problem

Many products are now sold through influencer videos and ads on Instagram, TikTok, etc. Buyers often get burned:

- Deliveries take weeks, or never arrive.
- The product that arrives looks cheaper than the one in the video.
- There's no easy way to tell whether the store behind the video is trustworthy. The influencer is paid to promote it, and the store's own website shows only what it wants you to see.

Existing "influencer verification" tools mostly serve **brands** (checking whether an influencer has fake followers). Very little helps the **buyer** answer: "Is the seller behind this video real, and will I actually get what I'm paying for?"

## 3. The product idea (current thinking)

A **verification layer** between social media product promotions and the seller. A user points the tool at a store or a video, and gets a **trust report**: a short list of evidence-based signals explaining how reliable the store and product look, plus safe-buying tips.

Every report should help answer two separate questions:

1. **Is the product real and good?** (reviews, does it match the ad, popularity)
2. **Is this store real, and will it deliver?** (business identity, age, policies)

The dangerous case to keep in mind: a real, popular product sold through a fake or impersonating store. Product signals look great, and the buyer still gets scammed.

---

## 4. Design principles (current thinking)

- **Evidence, not verdicts.** Report lines state facts ("Website created 3 weeks ago") rather than accusations ("This is a scam"). This is more trustworthy for users and avoids legal trouble.
- **Every signal is explainable.** Each one has a status and a plain-English explanation of what was found.
- **Show sources and ranges, never fake precision.** E.g. "2,300+ independent reviews (Trustpilot, Reddit)". Never invent numbers like an exact customer count.
- **"Not enough information" is a valid answer.** When evidence is missing, say so honestly.
- **Combinations matter more than single signals.** No single signal should trigger a "danger" result on its own. Example: a new website alone is only a mild warning, since legit small businesses (e.g. ones that sold through DMs for years) launch new websites all the time.
- **False positives matter.** Wrongly warning people away from honest businesses destroys trust in the tool.
- **Independent sources over store-controlled sources.** Reviews, sales counters, and "X people just bought this" popups on the store's own site are easy to fake and should be treated as near-worthless.
- **We never handle money.** The "safe payment" goal is achieved through guidance (e.g. "pay by credit card for chargeback protection", "this product is also on Amazon with buyer protection"), not by processing payments.

---

## 5. MVP signals (current shortlist, open to change)

| # | Signal | What it checks | Notes |
|---|---|---|---|
| 1 | **Business age** | Earliest evidence the business existed | Not just domain age (WHOIS). Also consider earliest Wayback Machine snapshot and earliest independent mention, to avoid penalizing businesses older than their website. |
| 2 | **Business transparency** | Business name, physical address, real contact email/phone, About page | Fetch store contact/About pages; an LLM can help extract details from messy page text. |
| 3 | **Shipping and refund policy** | Delivery time, ships-from location, ships to Canada, refund window, red-flag clauses | LLM extracts structured fields from policy pages. Covers delivery and region concerns. |
| 4 | **Independent customer reviews** | Reviews from sources the store doesn't control (e.g. Reddit, Trustpilot), sorted into: did it arrive, did it match the ad, region-specific experiences | Check API terms and rate limits first. "No independent reviews found" is itself useful. |
| 5 | **Product photo origin** | Reverse image search for the product photos on AliExpress/Temu etc. | Likely needs a paid or free-tier API. Check cost and feasibility before building. |

Ideas deliberately left for later (ask me before pulling any of these forward):

- Amazon/marketplace presence (and "buy it there with buyer protection" suggestions)
- Official brand account check to catch impersonator stores (e.g. official Instagram bio links to a different domain)
- "Claimed vs. real" side-by-side of official product images vs. independent customer photos
- Crowdsourced purchase reports from our own users (did it arrive, how long, did it match)
- Popularity metrics (review counts, marketplace badges, traffic estimates)

---

## 6. Clients / entry points (current thinking)

- **Backend API is the core.** All clients are thin and call the same API, so new clients are cheap to add later.
- **MVP:**
  - Simple web page with a paste box (store URL to start; video URL later). Should work on mobile browsers.
  - Chrome extension (Manifest V3, `activeTab` permission):
    - Case A: user is on a store page and clicks the extension to check it.
    - Case B: user pastes a link into the extension popup.
- **Later:**
  - Video mode: detect a TikTok/Instagram video URL, resolve which seller it promotes (caption, creator, bio links, LLM extraction), and ask the user to confirm when unsure. This is the hardest problem and comes after the rest works.
  - PWA with a share target so Android users can share a video straight to the app.
  - Possibly a native share extension or a DM bot.
- Known constraint: browser extensions don't run inside the Instagram/TikTok mobile apps or their in-app browsers.

---

## 7. Starting report contract (draft, expect it to evolve)

The API returns a report like this. Treat it as a starting shape, not a final schema.

```json
{
  "store_url": "https://example-store.com",
  "signals": {
    "business_age": { "status": "warning", "detail": "Website created 3 weeks ago" },
    "business_transparency": { "status": "warning", "detail": "No address or phone listed" },
    "shipping_policy": { "status": "warning", "detail": "Ships from overseas, 15–30 days" },
    "independent_reviews": { "status": "unknown", "detail": "No independent reviews found" },
    "photo_origin": { "status": "danger", "detail": "Photos match AliExpress listings" }
  }
}
```

Statuses so far: `good`, `warning`, `danger`, `unknown`. Things likely to be added later (ask me): sources per signal, an overall summary, payment tips, timestamps for caching.

---

## 8. Rough roadmap (tentative, order may change)

1. **Phase 0 (optional, mine):** Manually check a handful of sketchy and legit stores to see which signals actually separate them. These become the start of an evaluation dataset.
2. **Phase 1, walking skeleton:** Backend endpoint returns a hardcoded fake report; a bare paste-box page calls it and displays the result. Every layer exists and talks to the others.
3. **Phase 2, real signals one at a time,** roughly easiest first: business age, transparency, policies, reviews, photo origin. Each signal is a self-contained module.
4. **Phase 3, scoring and evaluation:** Rules-based scoring over signal combinations; an evaluation script that runs a labeled set of stores through the system and reports accuracy, false positives, etc. Possibly compare against an ML model later, once there is enough labeled data.
5. **Phase 4, Chrome extension** (store page detection plus paste box).
6. **Phase 5, video-to-seller resolution.**
7. **Phase 6, make it solid:** Parallel signal collection, caching (with different freshness per signal), deployment in a container, logging, mobile-friendly page, PWA share target.

---

## 9. Where to start: Phase 1

Goal: a working end-to-end skeleton with a fake report.

Likely pieces:

- A backend with one endpoint (e.g. `POST /check` taking a store URL) that validates input and returns the fake report from section 7.
- A minimal web page with a paste box that calls the endpoint and renders each signal with its status and detail.
- A README explaining how to run it locally.
- `DECISIONS.md` and `OPEN_QUESTIONS.md` started.

**Before writing any code, ask me about:**

- Backend language and framework. Python + FastAPI is the leading suggestion, since Python suits the later scraping, LLM, and ML work, but confirm with me.
- Python version, dependency/package manager, and virtual environment setup.
- Frontend for the paste page: plain HTML/JS vs. a framework like React + TypeScript.
- Repo structure (one repo with `backend/`, `web/`, `extension/` folders, or something else).
- Testing approach for this stage (e.g. a basic API test).

Done when: I can run the backend locally, paste a URL into the page, and see the fake report rendered, and I understand how each piece works.

---

## 10. Open questions (seed list for `OPEN_QUESTIONS.md`)

- Product name.
- Exact scoring approach: how signals combine, and what triggers each overall level.
- Which review sources are realistic given API terms and rate limits.
- Which reverse image search option to use, and its cost.
- Which LLM provider/model to use for extraction and summarization, and how to keep costs low.
- Storage: do we need a database in the MVP, and for what (cached reports, labeled stores, later user reports)?
- Deployment target (free or cheap cloud hosting) and when to deploy.
- How deep to go on the ML side (e.g. a trained classifier, image embeddings) vs. the systems side (async pipeline, caching, cloud).
- Whether to show an overall score or only individual signals.
- How to label the evaluation dataset and how big it should be.

---

## 11. Constraints and guardrails

- **Respect platform terms.** Check each data source's terms of service and rate limits before building on it. Prefer official APIs. Flag anything that would require scraping a site that prohibits it.
- **No rehosting copyrighted media.** Link to or use official embeds for brand images and videos rather than downloading and re-serving them.
- **Secrets stay out of the code.** API keys go in environment variables / a `.env` file that is git-ignored.
- **Cost-aware.** Prefer free tiers. Tell me before introducing anything that costs money.
- **Privacy.** Don't store users' personal data unless we've explicitly decided to and why.
- **No payment handling** of any kind.

---

## 12. Engineering habits I'd like (open to discussion)

- Readable code with type hints and clear names over clever code.
- Each signal as its own module with a consistent interface, so signals can be added, removed, or swapped easily.
- Basic tests for core logic as we go.
- Small commits with clear messages.
- Errors handled gracefully. A single failing data source should produce an `unknown` signal, not crash the whole report.

If any of these slow us down more than they help at a given stage, tell me and we can adjust.
