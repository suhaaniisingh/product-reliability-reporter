# Evaluation

Measured results, one section per metric. Each entry records the date, the model and the exact command, so it can be reproduced.

## Phase 1: Extraction accuracy

**Setup.**
- **Data:** `data/extraction_eval.csv`, 30 synthetic captions across six case types (explicit URL, brand only, link in bio, code only, no store, tricky). 20 are `dev` rows used while tuning the prompt; 10 are held-out `test` rows, which give the reported number.
- **Pipeline:** the same one the API runs: Claude Sonnet 5.5 extraction, then the deterministic rules in `backend/app/extraction/postprocess.py`, with real DNS checks for guessed domains.
- **Matching rules:** at the top of `backend/scripts/eval_extraction.py`.

**Caveats.**
- The captions are synthetic, so they may be cleaner than real ones, and accuracy may be optimistic.
- 10 held-out rows is a small sample: one row is 10 percentage points.
- `brand_only` expected domains reflect the brands' official sites as of 2026-11.

**Results: 2026-11-23, `claude-sonnet-5-5`, effort low, prompt at commit `326d67d`.**

Held-out test split (10 rows), run once after all tuning was finished:

| Metric | Result |
|---|---|
| **Store correct** (the field Phase 2 depends on) | **100% (10/10)** |
| Store source correct (in caption / guessed / none) | 100% (10/10) |
| Guess accuracy (brand → official domain) | 100% (2/2) |
| False-store rate (a store returned when the answer is none) | 0% (0/5) |
| Product / discount code / link-in-bio | 100% / 100% / 100% |
| Brand | 88% (7/8) |
| **All fields correct** | **90% (9/10)** |
| Latency per caption | 1.76 s mean, 2.25 s max |
| Cost | $0.0045 per caption (about 1,700 input + 115 output tokens) |

```bash
cd backend && uv run python -m scripts.eval_extraction --split test
```

**Dev split during tuning (20 rows).** Store correct was 20/20 on every run:

| Run | Change | All fields correct | Misses |
|---|---|---|---|
| 1 | baseline prompt (eval scoring bug for `x\|*` labels fixed afterwards) | 17/20 | c03 brand, c06 brand (scoring bug), c16 "LIB" not recognised |
| 2 | list "LIB" and other bio phrasings in the prompt; c03 relabelled | 19/20 | c03 brand read from the domain |
| 3 | "brand only when the caption names it" | 19/20 | c04 brand given only as a hashtag was skipped |

**What the misses show.**
- **Hashtag brands that match the store's domain** (`#cozyknit` with cozyknitco.com, `#summitgear` with summitgear.ca) were skipped every time: the "don't take the brand from a web address" rule overrode the hashtag. Brands that appear *only* as a hashtag were fine. Fixed below.
- **Correction (2026-11-23):** an earlier version of this section said dev c03 changed answer because of model randomness. That was wrong. The prompt changed between those two runs (the LIB line was added), and that change moved c03. Repeated runs with an unchanged prompt show no randomness on these rows (below).
- **Store extraction held up on the hard cases:** link aggregators, a charity URL, a "Dior dupe" comparison, a prompt-injection caption naming a scam domain, and TikTok Shop.

### Fix: hashtag brands (2026-11-23)

New rows: 5 in dev (including negative cases where generic hashtags like `#skincare` and `#fyp` must not become brands) and 8 in a fresh held-out split, `test2`. The original `test` split can't measure this fix, because its miss (c02) was seen while designing it.

Dev, 25 rows, each run 3 times (`--split dev --runs 3`):

| Prompt | Store | Brand | All fields | Rows changing between runs |
|---|---|---|---|---|
| Before (commit `326d67d`) | 100% ×3 | 96% ×3 | 96% ×3 | 0 of 25 |
| After: brand hashtags count even when they match the domain; generic and comparison hashtags don't | 100% ×3 | 100% ×3 | 100% ×3 | 0 of 25 |

Run-to-run variation: 0 rows out of 25 changed across 3 identical runs, for both prompts (150 calls). It exists in principle but was too small to see here.

Held-out `test2`: pending Suhaani's review of the 8 new rows.

**Not measured yet:**
- real (non-synthetic) captions
- how often a guessed domain is real but wrong (the eval only has well-known brands for guesses)
