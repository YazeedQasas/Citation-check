# IDs and shared schema

## Canonical IDs (decided)

| Kind | Shape | Examples |
|---|---|---|
| Statute | `S:{law_number}/{year}:{article}` | `S:12/2010:23`, `S:12/2010:23bis`, `S:12/2010:23bis-a` |
| Cassation | `C:{appeal_number}/{year}` | `C:456/2015` |

Rules (implemented in `src/citation_check/schema/ids.py`, tested in `tests/test_ids.py`):

- Any digit script (Western, Arabic-Indic, Persian, fullwidth) -> ASCII, leading zeros dropped. Mixed scripts inside one number are fine.
- `مكرر` -> `bis`; a following Arabic letter -> Latin (`(أ)` -> `-a`). `المادة` / `مادة` prefixes and brackets are ignored.
- Numbers in words are accepted for 1..99 (`الثالثة والعشرون` -> 23, `الخامسة عشرة` -> 15); English forms too (`Article 23 bis`, `Law No. 12 of 2010`). The corpus is Arabic only; drafts may contain English fragments, so the extraction output must still be in the shared (Arabic-corpus) structure.
- **Not in the ID:** clause (فقرة), chamber, decision date. Drafts often omit them, so requiring them would create false NOT_FOUND results. They are stored as metadata.
- A citation missing a required part gets `id = null` (e.g. "article 5 of the law" with no law number).
- IDs are always computed from the fields, never trusted from input (LLM or corpus).

Known limit: cassation numbering may restart per chamber/court in some systems. If the real corpus has two rulings with the same number and year, `Corpus` validation fails loudly on the duplicate; at that point add `chamber` to the cassation ID.

## Shared JSON shape

`extracted.json` and `corpus.json` both look like:

```json
{
  "statute":   [ {"id": "S:41/2008:23", "law_number": "41", "year": "2008", "article": "23",
                  "law_name": "...", "clause": null, "content": "...", "citation_text": "...", "source": "..."} ],
  "cassation": [ {"id": "C:456/2015", "appeal_number": "456", "year": "2015",
                  "chamber": "...", "date": "...", "content": "...", "citation_text": "...", "source": "..."} ]
}
```

`content` = what the law / principle says (corpus) or what the draft claims it says (extraction). `citation_text` is the exact wording in the draft and is extraction-only; `source` is corpus-only.

## Seed data

`data/corpus/source/seed_*.json` and `data/drafts/draft_*.txt` are **synthetic** (invented laws and rulings) so the pipeline can be built and tested before real material is available. `data/drafts/gold.json` holds the expected result for every citation in the six drafts (22 citations: 12 SUPPORTED, 4 CONTRADICTS, 2 AMBIGUOUS, 4 NOT_FOUND). `draft_06.txt` mixes in English citations and an article number written in words. Real sources go in `data/corpus/source/` in the same format; `python -m citation_check.corpus.build` regenerates `data/corpus/corpus.json`.
