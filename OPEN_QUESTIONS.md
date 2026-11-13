# Open Questions

Things still undecided. Items are removed once resolved (and the decision recorded in `DECISIONS.md`).

## Product

- **URL input leniency:** the API currently rejects `example-store.com` (no `https://`). Should the API or the page add `https://` automatically, and should we strip tracking parameters (e.g. `?utm_source=tiktok`) before checking?
- Product name.
- Whether to show an overall score or only individual signals.
- Exact scoring approach: how signals combine, and what triggers each overall level.

## Data sources and cost

- Which review sources are realistic given API terms and rate limits.
- Which reverse image search option to use, and its cost.
- Which LLM provider/model to use for extraction and summarization, and how to keep costs low.

## Infrastructure

- Storage: do we need a database in the MVP, and for what (cached reports, labeled stores, later user reports)?
- Deployment target (free or cheap cloud hosting) and when to deploy.

## Depth and evaluation

- How deep to go on the ML side (e.g. a trained classifier, image embeddings) vs. the systems side (async pipeline, caching, cloud).
- How to label the evaluation dataset and how big it should be.
