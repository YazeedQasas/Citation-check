# Extraction evaluation

Run: `python scripts/eval_extraction.py` (needs LM Studio with `google/gemma-4-e4b`; `--no-llm-runs` for regex only).
Raw results: `reports/extraction_eval.json`. Gold labels: `data/drafts/gold.json` (22 citations, 6 Arabic drafts, 3 citations in English phrasing).
A citation is found when its canonical ID matches a gold ID of the same kind in the same draft; entries without an ID count as false positives.

## Proceed thresholds (decided)

| Metric | Threshold | Why |
|---|---|---|
| Recall on IDs (overall, and for each kind) | >= 0.90 | A missed citation is never checked, so it silently passes. |
| Precision | >= 0.95 | A false citation produces a false NOT_FOUND against the judge's draft. |

## Results (prompt `extraction_v2`, 2026-11-11)

| Configuration | Precision | Recall | TP / FP / FN | Time |
|---|---|---|---|---|
| **full** (LLM + grounding + same-law + regex net) | 1.000 | 1.000 | 22 / 0 / 0 | 55 s for 6 drafts |
| llm_only (no regex net) | 1.000 | 0.909 | 20 / 0 / 2 | 56 s |
| regex_only (no LLM) | 1.000 | 1.000 | 22 / 0 / 0 | < 1 s |

LLM-only misses: `S:8/2013:77` ("المادة (۷۷) من القانون ذاته" after a cassation citation) and `S:8/2013:31bis` (English citation inside an Arabic sentence). Both are covered by the code-side steps (same-law resolution / regex net), which is why they exist.

By language (full): Arabic 1.000 / 1.000, English 1.000 / 1.000. LLM-only English recall: 0.667.

## Read this before trusting the numbers

- **The gold set is small (22) and written by the same person who tuned the regex net.** The drafts use fairly standard phrasing. A perfect score here shows the pipeline works on these shapes, not that it generalises. Real judgments will contain phrasings nobody anticipated.
- **The regex net alone matching the LLM is partly a sign of that.** On messier real text the LLM should carry more of the load and the regex less.
- The few-shot examples were deliberately made from invented citations that appear in neither the corpus nor the gold set, so the LLM score is not inflated by leakage.
- The model is not fully deterministic even at temperature 0: repeat runs sometimes differ (one run produced a garbled year, which the grounding step repairs).

## Next measurements (Phase 5)

Re-run this evaluation on the held-out planted-error drafts (new documents, different phrasings) and, ideally, on a few real anonymised judgments. If recall drops below 0.90 there, iterate on the prompt/regex or try a larger model before relying on extraction.
