# Evaluation log

Commands: `python scripts/eval_pipeline.py --drafts <dir> --label <name> --out reports/pipeline_eval_<name>.json` (end-to-end: final status vs gold) and `python scripts/eval_extraction.py --drafts <dir>` (extraction only). Needs LM Studio with `google/gemma-4-e4b`.
Result files are in `reports/`. Gold statuses are relative to the **synthetic seed corpus** in `data/corpus/`.

| Set | Folder | Size | What it is |
|---|---|---|---|
| sample | `data/drafts/` | 6 drafts, 22 citations | The first drafts. The extraction patterns were tuned on these, so this is the least independent set. |
| held-out | `data/eval/` | 8 drafts, 27 citations | Planted errors (12 SUPPORTED, 6 CONTRADICTS, 4 AMBIGUOUS, 5 NOT_FOUND), English citations, distractors (appeal-court decision, contract article, case number), different phrasings. Built by `scripts/build_eval_set.py`. |
| hard | `data/eval_hard/` | 5 drafts, 17 citations | Subtle one-detail contradictions, heavy paraphrase, near-miss IDs, line breaks inside a citation, diacritics, plural articles with a combined claim. Built by `scripts/build_eval_hard.py`. |

## Runs

| Run | sample (22) | held-out (27) | hard (17) | Notes |
|---|---|---|---|---|
| v1 (first end-to-end) | 22/22 | 27/27 | **14/17** | hard set exposed 3 errors, all in draft H04 |
| v2 (after fixes below) | 22/22 | 27/27 | **17/17** | no regressions |

Extraction alone (held-out): full pipeline P 1.000 / R 1.000; LLM only R 0.926 (misses `S:77/2011:12`, `S:15/2015:9`); regex only R 0.852. Each half misses different citations, which is why both are kept.

## Failures found on the hard set, grouped by cause, and what fixed them

| # | Cause | Symptom | Fix | Effect |
|---|---|---|---|---|
| 1 | **Article normaliser was not idempotent** (ID normalisation bug) | `23bis-a` became `23` whenever an entry was rebuilt (grounding repair, same-law resolution) or `extracted.json` was read back; the citation "المادة (٢٣ مكرر (أ))" was reported as article 23 instead of NOT_FOUND | Accept the canonical `-a` suffix when parsing; strip nested/stray brackets (`ids.py`); regression test `test_normalisation_is_idempotent` | fixes the MISSED `S:41/2008:23bis-a` |
| 2 | **Plural articles with a combined claim** (claim judgement) | "المادتين (٢٣) و(٢٣ مكرر) ... يمتد الميعاد ثلاثين يوماً ويوقف إذا توفي ..." describes both articles; judged against each article alone, both looked contradicted | Judge the claim against the articles read together; if it matches all existing members are SUPPORTED (`verify.py`) | fixes 2 wrong CONTRADICTS |
| 3 | **Quote spans differing by one character** (grouping) | the LLM's quote and the regex net's quote of the same sentence differed by a trailing space, so the group in #2 was not recognised | Group findings by overlapping spans; regex quotes no longer include trailing whitespace | needed for #2 to fire |

No prompt change was needed: all three causes were in code, not in the LLM's judgement.

### Found while covering edge cases (`tests/test_edge_cases.py`)

| # | Cause | Symptom | Fix |
|---|---|---|---|
| 4 | **Duplicate merging compared whole sentences** (extraction merge) | Three different claims about the same article, in sentences sharing the citation wording, were merged into one, so a wrong claim repeated later in a draft could be hidden behind a correct one | Compare only the claim part (citation wording removed) before merging (`pipeline._same_claim`) |
| 5 | **Regex needed cassation context before the number** | "وفي القرار رقم (2210) لسنة 2019 قررت محكمة النقض…" was not found by the regex net; in a long multi-chunk draft the LLM also missed it (17/18 IDs) | Accept cassation context right after the number, only when the phrase starts with a decision keyword (القرار / الطعن / Decision …), so "الدعوى برقم (445)" stays excluded |
| 6 | **No early check that LM Studio is up** | With LM Studio down, every call failed separately | `LMStudioClient.ping()` runs first; CLI exits with code 4 and a clear message (start the server, load the model). Bad input (missing draft/corpus) is still reported first, exit code 2. Client no longer sleeps after its final failed attempt |

After #4-#6 all three sets were re-run: sample 22/22, held-out 27/27, hard 17/17.

Multi-chunk check (real model): all 8 held-out drafts joined (4,719 characters) and forced into 3 chunks of at most 2,200 characters, 17 of 18 distinct IDs found before fix #5, no invented citations, no incomplete chunks.

## Not fixed / known limits

- The LLM claim check was 100% on these sets, but the sets are small and written by the same person who built the pipeline. Real judgments will have longer sentences, claims that mix several points, and corpus texts that are longer than our one-sentence seeds.
- The boundary between AMBIGUOUS (unrelated claim) and CONTRADICTS (related but different) is fuzzy for provisions of the same law on neighbouring topics. The 4 AMBIGUOUS cases in the held-out set use clearly unrelated subjects; a borderline case (e.g. overtime pay claimed under the notice-period article) was left out of the gold because the "right" answer is arguable.
- Model output is not perfectly deterministic at temperature 0; results can differ slightly between runs.
