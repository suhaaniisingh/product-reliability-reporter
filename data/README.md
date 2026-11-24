# Data

## `extraction_eval.csv`: Phase 1 extraction eval set

About 30 synthetic captions written to cover every case type, with the answer extraction *should* give for each. They were drafted by Claude, to be reviewed by Suhaani (see `docs/DECISIONS.md`, 2026-11-23). The eval script scores the extractor against these rows.

**Caveat:** synthetic captions may be cleaner than real ones, so the accuracy measured here may be optimistic.

### Columns

| Column | Meaning |
|---|---|
| `id` | `c01`, `c02`, … |
| `split` | `dev` (used while tuning the prompt) or `test` (held out; the reported number) |
| `case_type` | See below |
| `platform` | `tiktok` or `instagram` (written in that platform's style) |
| `caption` | Caption text (quoted, see "CSV tips") |
| `expected_product` | Product name. Use `\|` for acceptable alternatives (`vitamin C serum\|glow serum`). Blank if none. |
| `expected_brand` | Brand, or blank |
| `expected_store_url` | The store domain extraction should return. For `brand_only` rows, this is the brand's real official domain. Blank if no store should be returned. |
| `expected_store_url_source` | `in_caption`, `guessed_from_brand`, or `none` (`user_provided` never appears here, because those scans don't use the LLM) |
| `expected_link_in_bio` | `true` / `false` |
| `expected_discount_code` | The code, or blank |
| `notes` | Why this row is interesting |

In the `expected_*` text columns: blank means the field must be null, `a|b` accepts any listed alternative, and `*` means "anything is fine, don't score this field for this row". The exact matching rules are at the top of `backend/scripts/eval_extraction.py`.

### Case types

| `case_type` | What the caption looks like |
|---|---|
| `explicit_url` | The store domain is in the caption (`glowlab.co` counts even without `https://`) |
| `brand_only` | A brand is named, with no URL; the expected answer is the official domain (tests guessing) |
| `link_in_bio` | Points to the bio ("link in bio", "LIB"), with or without a brand |
| `code_only` | A discount code, with no brand or URL |
| `no_store` | No store mentioned |
| `tricky` | Linktree/link-aggregator URLs, an unrelated URL (charity, music), several products, a misspelled brand |

### Running the eval

```bash
cd backend
uv run python -m scripts.eval_extraction --dry-run --split all   # check the CSV, no API calls
uv run python -m scripts.eval_extraction                         # dev split, live (needs ANTHROPIC_API_KEY)
uv run python -m scripts.eval_extraction --split test            # held-out split: the reported number
```

### CSV tips

Captions contain commas, quotes and line breaks. Wrap each caption in double quotes and write any `"` inside it as `""`. Editing in a spreadsheet and exporting as CSV takes care of this.
