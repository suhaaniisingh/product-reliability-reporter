# Backlog

Ideas and tasks for **later** phases (phase numbers follow the plan of 2026-11-26). Writing them down here keeps the current phase focused. Nothing here gets built until its phase starts (or we explicitly agree to pull it forward).

Each item: what it is, the phase it fits, and where the idea came from.

## Trust signals and scoring (any phase, when it pays off)

- **Normalize store URLs before checking.** Add `https://` when it's missing, lowercase the host, strip `www.` and tracking parameters (`utm_*`, `ref`), and compare by registrable domain. *Source: old OPEN_QUESTIONS.md.* (A basic version, adding `https://` and lowercasing the host, is built in Phase 1 for the user-supplied `store_url` field and for eval scoring. See DECISIONS 2026-11-23.)
- **Business age beyond WHOIS.** Also check the earliest Wayback Machine snapshot, so a business that is older than its current domain isn't penalized. *Source: old brief, signal 1.*
- **LLM extraction of store policy pages.** Pull structured fields from the store's own pages: shipping time, ships-from country, refund window, red-flag clauses. Could feed the "store-page checks" signal. *Source: old brief, signal 3.*
- **Resolve "link in bio".** When a caption says "link in bio", find the actual store URL. Neither TikTok nor Instagram oEmbed exposes bio links (checked 2026-11-23), so this needs a permitted source first, or the user pastes the link themselves. *Source: Phase 1 research.*
- **Impersonation check.** Does the brand's official social account link to a different domain than the one in the video? This catches the "real product, fake store" case. Needs a permitted data source. *Source: old brief, "later" list.*

- **Trustpilot as a review signal**, only if a free developer key turns out to exist (unconfirmed 2026-11-24: their docs describe keys via paid Trustpilot for Business or a partner agreement). *Source: Phase 2 review research.*

- **Pages rendered by JavaScript:** contact details (and sometimes policies) that a site loads with JavaScript aren't in the HTML our fetcher receives (e.g. Nike's help page). Options: an LLM reading the pages we do get, or a headless browser (heavier). Postal addresses aren't detected at all yet. *Source: Phase 2 live checks, 2026-11-24.*

- **Brand sites that aren't shops** (e.g. cerave.com) lose points for "no return policy / no contact" even when long-established: they send buyers to retailers, and their details are often rendered by JavaScript. Consider detecting "no checkout" sites, or weighting age + popularity differently. Decide with labelled data. *Source: live caption scan, 2026-11-24.*

## Phase 5: Score validation

- Use public scam-domain lists as one label source for the ~100-store check, recording the source for every label. *Source: CLAUDE.md.*

## Phase 7: Chrome extension

- **Terms check before reading anything from the page.** The planned design uses only the tab's URL and text the user selects (right-click), which needs no page reading. If we ever want a content script reading the DOM, check TikTok's and Instagram's terms first and ask Suhaani. *Source: Phase 1 research.*
- **TikTok embed deprecation.** TikTok's docs say "Embed Videos will be deprecated soon" and recommend the Embed Player (`tiktok.com/player/v1/{id}`) instead. If we ever show the video in our UI, use the Embed Player. *Source: Phase 1 research, docs page dated 2026-10-23.*

## Out of scope since the direction change (2026-11-26)

Kept here so the reasoning isn't lost. Not to be built in this project; some may fit the separate ML project.

- **@handle → store matching.** If the @handle feature is ever built, use the simple link-back rule (the candidate site links to the handle), not a learned matcher. *Source: discussion 2026-11-25.*
- **Add real captions to the extraction eval set.** The eval tooling is frozen; the helper's numbers stand as recorded. *Source: Phase 1 caveat.*
- **Product photo origin** (reverse image search on AliExpress/Temu) and **dropshipping/markup detection** (e.g. CLIP image embeddings). *Source: old brief, signal 5; old Phase 6.*
- **Reading the brand from a video frame or screenshots** (the extension capture sessions). Multimodal extraction is out of scope. *Source: decisions of 2026-11-24.*
- **"Claimed vs. real":** compare official product images with independent customer photos. *Source: old brief, "later" list.*
- **Marketplace presence:** "this product is also sold on Amazon, with buyer protection". *Source: old brief, "later" list.*
- **Crowdsourced purchase reports** (did it arrive, did it match the ad). Needs user accounts, which are a non-goal. *Source: old brief, "later" list.*
- **Plain-English LLM summary of the result.** Skipped: the reasons list already explains the score, and a summary adds cost to every check. *Source: 2026-11-26.*

## Engineering (any phase, when it pays off)

- **The default compute service account still has the project-wide Editor role** (Google's default). Nothing uses it now (the VM runs with no service account), so it could be removed or the account disabled. *Source: Cloud Run retirement, 2026-11-27.*
- **CI and automatic deploys:** now part of Phase 3. *Source: Phase 2 decisions.*
- **Web page tests** (Vitest + React Testing Library), once the page has logic worth testing. *Source: old OPEN_QUESTIONS.md.*
- **Investigate the Instagram Graph API "Business Discovery" endpoint** for public business/creator account data. Not verified yet: it likely needs a Meta app, an Instagram professional account, and App Review. *Source: Phase 1 research.*
