"""Dev check of the claim-comparison prompt: gold claim text vs corpus text for every citation that exists.

Expected: SUPPORTED -> matches; CONTRADICTS -> related but not matching; AMBIGUOUS -> neither.
(The gold 'claim' strings are short English summaries, so this also tests cross-language comparison.
The realistic end-to-end evaluation uses the claims extracted from the drafts.)
"""
import time

from citation_check import config
from citation_check.evaluation.extraction import load_gold
from citation_check.llm import LMStudioClient
from citation_check.schema.validate import load_citation_file
from citation_check.verification import claim
from citation_check.verification.matcher import CorpusIndex

EXPECT = {"SUPPORTED": (True, True), "CONTRADICTS": (False, True), "AMBIGUOUS": (False, False)}
corpus = CorpusIndex(load_citation_file(config.CORPUS_PATH, kind="corpus"))
ok = total = 0
with LMStudioClient() as client:
    for name, items in load_gold().items():
        for it in items:
            if it["expected_status"] == "NOT_FOUND":
                continue
            entry = (corpus.statute if it["kind"] == "statute" else corpus.cassation)[it["id"]]
            t0 = time.time()
            j = claim.judge_claim(client, it["kind"], it["id"], entry.content, it["claim"])
            got = (j.matches_claim, j.related)
            good = got == EXPECT[it["expected_status"]]
            ok += good
            total += 1
            print(f"{'OK ' if good else 'BAD'} {name} {it['id']:18s} want {it['expected_status']:11s} got match={j.matches_claim!s:5} related={j.related!s:5} "
                  f"({time.time() - t0:.0f}s) {j.reason}")
print(f"\n{ok}/{total} as expected")
