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
- **Brands that appear only as a hashtag** (`#cozyknit`, `#summitgear`) are skipped since the "brand only when named" rule was added (test c02, dev c04). This is a systematic weakness, not noise; the next prompt change should target it, measured on dev only.
- **The same caption can give different answers on different runs** (dev c03: no brand on run 1, "Lumora Design" on run 2, with the same rules). Sonnet 5.5 doesn't accept sampling settings like `temperature`, so single-run numbers carry noise. On 10 rows, one row is 10 points.
- **Store extraction held up on the hard cases:** link aggregators, a charity URL, a "Dior dupe" comparison, a prompt-injection caption naming a scam domain, and TikTok Shop.

**Not measured yet:**
- run-to-run variance (repeat runs, report mean ± spread)
- real (non-synthetic) captions
- how often a guessed domain is real but wrong (the eval only has well-known brands for guesses)
