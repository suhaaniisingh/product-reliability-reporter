# Backlog

Ideas and tasks for **later** phases. Writing them down here keeps the current phase focused. Nothing here gets built until its phase starts (or we explicitly agree to pull it forward).

Each item: what it is, the phase it fits, and where the idea came from.

## Phase 2: Trust signals + rule-based score

- **Normalize store URLs before checking.** Add `https://` when it's missing, lowercase the host, strip `www.` and tracking parameters (`utm_*`, `ref`), and compare by registrable domain. *Source: old OPEN_QUESTIONS.md.* (A basic version, adding `https://` and lowercasing the host, is built in Phase 1 for the user-supplied `store_url` field and for eval scoring. See DECISIONS 2026-11-23.)
- **Business age beyond WHOIS.** Also check the earliest Wayback Machine snapshot, so a business that is older than its current domain isn't penalized. *Source: old brief, signal 1.*
- **LLM extraction of store policy pages.** Pull structured fields from the store's own pages: shipping time, ships-from country, refund window, red-flag clauses. Could feed the "store-page checks" signal. *Source: old brief, signal 3.*
- **Resolve "link in bio".** When a caption says "link in bio", find the actual store URL. Neither TikTok nor Instagram oEmbed exposes bio links (checked 2026-11-23), so this needs a permitted source first, or the user pastes the link themselves. *Source: Phase 1 research.*
- **Impersonation check.** Does the brand's official social account link to a different domain than the one in the video? This catches the "real product, fake store" case. Needs a permitted data source. *Source: old brief, "later" list.*

- **Trustpilot as a review signal**, only if a free developer key turns out to exist (unconfirmed 2026-11-24: their docs describe keys via paid Trustpilot for Business or a partner agreement). *Source: Phase 2 review research.*

- **Pages rendered by JavaScript:** contact details (and sometimes policies) that a site loads with JavaScript aren't in the HTML our fetcher receives (e.g. Nike's help page). Options: an LLM reading the pages we do get, or a headless browser (heavier). Postal addresses aren't detected at all yet. *Source: Phase 2 live checks, 2026-11-24.*

- **Brand sites that aren't shops** (e.g. cerave.com) lose points for "no return policy / no contact" even when long-established: they send buyers to retailers, and their details are often rendered by JavaScript. Consider detecting "no checkout" sites, or weighting age + popularity differently. Decide with labelled data. *Source: live caption scan, 2026-11-24.*

## Phase 3: Labelled dataset + evaluation

- **Add real captions to the eval set**, to check how optimistic the synthetic numbers are. *Source: Phase 1 caveat.*

- Use public scam-domain lists as one label source, recording the source for every label. *Source: CLAUDE.md.*

## Phase 4: Chrome extension

- **Terms check before reading captions from the page.** The extension would read the caption from the page the user is already viewing (a content script reading the DOM, started by the user). Check TikTok's and Instagram's terms on this before building it, and ask Suhaani. *Source: Phase 1 research.*
- **TikTok embed deprecation.** TikTok's docs say "Embed Videos will be deprecated soon" and recommend the Embed Player (`tiktok.com/player/v1/{id}`) instead. If we ever show the video in our UI, use the Embed Player. *Source: Phase 1 research, docs page dated 2026-10-23.*

## Phase 6 / stretch

- **Product photo origin:** reverse image search for the product photos on AliExpress/Temu. Overlaps with the dropshipping/markup detection already planned for Phase 6. *Source: old brief, signal 5.*
- **Marketplace presence:** "this product is also sold on Amazon, with buyer protection". *Source: old brief, "later" list.*
- **"Claimed vs. real":** compare official product images with independent customer photos. *Source: old brief, "later" list.*
- **Crowdsourced purchase reports** (did it arrive, did it match the ad). This probably needs user accounts, which are a non-goal for the MVP, so it's parked. *Source: old brief, "later" list.*

## Engineering (any phase, when it pays off)

- **A dedicated Cloud Run runtime service account** with only secret-read access. The default compute account currently also holds the Cloud Run Builder role (needed for source deploys), so the running app has more permissions than it needs. *Source: Phase 2 deploy.*
- **Keep the instance warm** once there are real users: a Cloud Scheduler job calling `/api/warmup` every ~10 minutes removes the ~5 s cold start (confirm Scheduler's free allowance first); `min-instances 1` if a guarantee is worth paying for. *Source: decision of 2026-11-24.*
- **Automatic deploys** (GitHub Actions or a Cloud Build trigger on push to `main`) once the manual deploy feels stable. *Source: Phase 2 decisions.*

- **CI:** a GitHub Actions workflow that runs `pytest` and the web build on every push to `main`.
- **Web page tests** (Vitest + React Testing Library), once the page has logic worth testing. *Source: old OPEN_QUESTIONS.md.*
- **Investigate the Instagram Graph API "Business Discovery" endpoint** for public business/creator account data. Not verified yet: it likely needs a Meta app, an Instagram professional account, and App Review. *Source: Phase 1 research.*
