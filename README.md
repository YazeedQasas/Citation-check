# Citation Check

Checks every **statute** and **Court of Cassation** citation in a draft judgment (Arabic, with English fragments and any digit script) against a local JSON corpus of laws and cassation principles, and reports whether each citation is real and whether the draft describes it correctly.

Everything runs locally: Gemma 4 E4B served by LM Studio, plus plain Python. No data leaves the machine.

## The four statuses

| Status | Meaning |
|---|---|
| `SUPPORTED` | The citation exists in the corpus and the draft's claim about it matches the corpus text. |
| `CONTRADICTS` | It exists and the claim is about the same subject, but says something different or opposite (different period, opposite rule, extra rule). |
| `AMBIGUOUS` | It exists but the claim is about an unrelated subject, so it cannot be confirmed. Also used when the claim check itself failed (`needs_review: true`). |
| `NOT_FOUND` | No corpus entry has this ID (fabricated, mistyped, or an incomplete citation such as "المادة 5 من قانون العمل" with no law number). A hint says why, e.g. "law 77/2011 is in the corpus but article 99 is not". |

```
Exists?  no  -> NOT_FOUND
         yes -> Correct claim?  yes -> SUPPORTED
                                no  -> Related?  yes -> CONTRADICTS
                                                 no  -> AMBIGUOUS
```
"Exists?" is a plain ID comparison (no LLM). Only citations that exist are sent to the LLM for the claim check.

## How it works

```
draft (.txt/.docx)
  -> Extraction layer:  clean text -> chunk -> Gemma extracts citations (JSON schema) -> grounding check
                        -> 'same law' resolution -> regex safety net -> extracted.json
  -> Verification layer: match IDs with corpus.json -> claim check (Gemma) -> status per citation
  -> findings.json + readable summary
```

- **IDs are built by code, never by the model.** `S:{law}/{year}:{article}` (e.g. `S:41/2008:23bis`) and `C:{appeal}/{year}` (e.g. `C:456/2015`). Any digit script, numbers in words, `مكرر`, English forms all normalise to the same ID. Both the corpus builder and the extraction layer use the same normaliser, so the two JSONs match by construction. See [docs/ids-and-schema.md](docs/ids-and-schema.md).
- **The LLM is checked by code.** Every quote must exist in the draft; numbers that contradict the quote are repaired from the quote; "القانون ذاته" is resolved in code; a regex pass adds explicit citations the model missed (marked `origin: "regex"`).
- **Articles cited together** ("المادتين (23) و(23 مكرر)") share one claim, which is judged against the articles read together.

## Setup

Requirements: Python 3.10+, LM Studio with `google/gemma-4-e4b` loaded.

```
pip install -e ".[dev]"
```

1. In LM Studio load **google/gemma-4-e4b** (context length 16000 recommended) and start the local server (Developer tab, default `http://localhost:1234`).
2. Settings are environment variables (defaults in [config.py](src/citation_check/config.py)):

| Variable | Default | Meaning |
|---|---|---|
| `LMSTUDIO_BASE_URL` | `http://localhost:1234/v1` | LM Studio server |
| `LMSTUDIO_MODEL` | `google/gemma-4-e4b` | model id |
| `LLM_CONTEXT_TOKENS` | `16000` | model context window |
| `CHUNK_MAX_CHARS` | `6000` | draft text per extraction call (longer drafts are chunked) |
| `LLM_MAX_TOKENS` / `LLM_MAX_RETRIES` | `3500` / `2` | per-call output budget / retries |
| `CORPUS_PATH`, `DRAFTS_DIR`, `LOG_DIR` | `data/corpus/corpus.json`, `data/drafts`, `logs` | paths |

Every LLM call (prompt, raw reply, tokens, timing, outcome) is appended to `logs/llm_calls.jsonl`.

## Usage

```
python -m citation_check corpus                     # build data/corpus/corpus.json from data/corpus/source/*.json
python -m citation_check check draft.docx           # full pipeline -> draft.findings.json + summary on screen
python -m citation_check check draft.txt -o out.json --extracted extracted.json
python -m citation_check extract draft.txt -o extracted.json     # extraction layer only
python -m citation_check verify extracted.json                    # verification layer only
python -m citation_check extract draft.txt --no-llm               # regex safety net only (no LM Studio)
```

Sample output (`check`):

```
Citation check: draft_03.txt
  SUPPORTED: 0   CONTRADICTS: 2   AMBIGUOUS: 0   NOT_FOUND: 2   (total 4)

NOT_FOUND (2)
  [statute] S:77/2011:99  المادة (99) من القانون ذاته
      law 77/2011 is in the corpus but article 99 is not (corpus has: 12, 15)
  [cassation] C:5555/2021  القرار رقم 5555 لسنة 2021
      no cassation decision with this number and year in the corpus
CONTRADICTS (2)
  [statute] S:77/2011:12  المادة (12) من قانون رقم (77) لسنة 2011
      النص يمنع الإثبات بالشهود إذا تجاوزت القيمة خمسة آلاف دينار.
  ...
```

Exit codes: `0` ok, `2` bad input (missing/unreadable draft or corpus), `3` finished but part of the draft could not be processed by the LLM (results may be incomplete), `4` LM Studio unreachable or model not loaded.
Supported draft formats: `.txt` (UTF-8/UTF-16/Windows-1256) and `.docx`. PDF is rejected on purpose (Arabic PDF text extraction is unreliable); convert to `.docx` first.

## Web interface (walk the pipeline)

A React + Vite interface for testing quality: paste or upload a draft (or load one of the samples), run the four stages one at a time or all at once, and look at what each stage produced.

```
python -m pip install -e ".[api]"          # once: adds FastAPI + uvicorn
python -m citation_check serve           # terminal 1: API on http://127.0.0.1:8000

cd web
npm install                              # once
npm run dev                              # terminal 2: interface on http://localhost:5173
```
Or build it once (`npm run build`) and open http://127.0.0.1:8000 directly (the API serves `web/dist`).
Or start both with one command from the project folder: `.\dev.ps1` (opens the API in a second window and runs Vite here).

**"http proxy error" / ECONNREFUSED in the Vite terminal** means the Python API is not running on port 8000: Vite only forwards `/api` requests to it. Start `python -m citation_check serve` (or `.\dev.ps1`). The interface shows a red "API not running" badge in the same situation. If `serve` itself fails, the packages are missing in that Python: `python -m pip install -e ".[api]"`.

- **Walk the pipeline**: (1) text cleaning, (2) regex safety net with no LLM, (3) extraction layer with the code safety-check notes, (4) verification. The draft on the left is highlighted: colour = status after verification, or who found it (regex / llm) before. Click a highlight or a table row to see the claim, the corpus text it was compared with, and the reason.
- **Edit and re-verify**: the verification input is an editable JSON. Change a claim or an article number, delete an entry, and re-run stage 4.
- **Gold labels**: for the sample drafts, each finding shows whether it matches the expected status, and which expected citations were never extracted.
- **Claim check**: one claim against one corpus text (or your own text). **Corpus**: browse and search it. **LLM calls**: the prompt, raw reply and timing of recent calls.

Notes: the first LLM call after LM Studio has been idle can take minutes while the model loads (one extraction call took 170 s in testing; later calls took 5 to 15 s). The API only listens on 127.0.0.1.

## JSON formats

**corpus.json / extracted.json** share one shape (JSON Schema: [citation_set.schema.json](src/citation_check/schema/citation_set.schema.json)):

```json
{
  "statute":   [ {"id": "S:41/2008:23", "law_number": "41", "year": "2008", "article": "23",
                  "law_name": "...", "clause": null, "content": "...", "citation_text": "...", "span": [99, 166], "origin": "llm", "source": "..."} ],
  "cassation": [ {"id": "C:456/2015", "appeal_number": "456", "year": "2015", "chamber": "...", "date": "...",
                  "content": "...", "citation_text": "...", "span": [525, 551], "origin": "llm", "source": "..."} ]
}
```
`content` is the authoritative text/principle in the corpus, and the claim the draft makes in `extracted.json`. `citation_text`, `span` (character offsets in the original draft) and `origin` appear only in extraction output; `source` only in the corpus. `id` is always recomputed from the number fields.

**findings.json**: `draft`, `counts` (per status), `extraction_complete`, `warnings`, and a list of `findings`, each with `kind`, `id`, `status`, `citation_text`, `claim`, `reason`, `matched_corpus_id`, `corpus_content`, `closest_corpus_id` (near miss, NOT_FOUND only), `span`, `origin`, `needs_review`. Findings are in document order.

## Using your own corpus

Put your laws and rulings in `data/corpus/source/*.json` in the same shape (raw fields are fine, any digit script; no `id` needed), delete the `seed_*.json` files, and run `python -m citation_check corpus`. The build fails with a clear message on duplicate IDs, missing numbers or empty content. The files in `data/corpus/source/` today are **synthetic seed data** (invented laws and rulings) used for development and tests.

## Tests and evaluation

```
python -m pytest                                              # 150+ tests, no LM Studio needed (LLM is faked)
python scripts/eval_pipeline.py --drafts data/eval --label heldout     # end-to-end, needs LM Studio
python scripts/eval_extraction.py --drafts data/eval                  # extraction only (LLM / regex / full)
```
Results and the change log are in [docs/evaluation-log.md](docs/evaluation-log.md) and [docs/extraction-evaluation.md](docs/extraction-evaluation.md). Latest: sample drafts 22/22, held-out set 27/27, hard stress set 17/17 statuses correct.

## Known limits (read before relying on it)

- **Evaluated on synthetic data only.** The corpus, all 19 drafts and all gold labels were written during development, by the same people who built the pipeline. A perfect score here shows the pipeline works on these shapes, not that it will on real judgments and a real corpus. Measure on real, anonymised drafts before trusting it.
- **The LLM claim check is the weakest link.** It judged every claim correctly on the test sets, but those corpus texts are one sentence long. Longer provisions, claims that mix several points, and the borderline between `AMBIGUOUS` and `CONTRADICTS` (neighbouring provisions of one law) will be harder. Treat `SUPPORTED` as "no problem found by the model", and anything `needs_review` as unchecked.
- **Extraction is not guaranteed complete.** Code safety nets catch many misses, but a citation phrased in a way neither the model nor the patterns recognise is not checked (and therefore not reported). The summary only lists what was found.
- **Citations without a law number** (e.g. "المادة 5 من قانون العمل") cannot be matched; they are reported as `NOT_FOUND` with "incomplete citation". Matching by law name is not implemented.
- **The same citation stated identically several times is reported once**, at its first position. Different claims about the same article are each checked.
- The model is not fully deterministic even at temperature 0; repeated runs can differ slightly. Speed on the development machine: roughly 10 to 15 seconds per draft page for extraction plus 1 to 3 seconds per citation for the claim check.
- Cassation IDs use number and year only; if your corpus has the same number and year in different chambers, the corpus build fails on the duplicate and the chamber must be added to the ID.
- Prompts are versioned in `src/citation_check/extraction/prompts/` and `.../verification/prompts/`. Change a prompt by creating a new version, and re-run the evaluations.

## Layout

```
web/             React + Vite interface (src/App.tsx, components/, tabs/)
src/citation_check/
  api.py         local HTTP API used by the interface (one endpoint per stage)
  extraction/    loader, text normalisation, chunking, prompt (+ prompts/), grounding, patterns (regex), same-law, pipeline, output
  verification/  matcher (Exists?), claim check (+ prompts/), status logic, findings, verify
  corpus/        corpus builder      schema/  shared models, ID normaliser, validators
  evaluation/    extraction and end-to-end evaluation     llm.py  LM Studio client     cli.py  commands
data/corpus/source/   raw corpus sources (synthetic seed)    data/drafts, data/eval, data/eval_hard   sample / held-out / stress drafts + gold.json
docs/  reports/  scripts/  tests/
```
