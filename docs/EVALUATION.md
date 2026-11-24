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

**Results.** Pending the first live run (needs `ANTHROPIC_API_KEY`):

```bash
cd backend && uv run python -m scripts.eval_extraction --split test
```
