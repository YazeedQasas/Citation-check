import json

import httpx
import pytest

from citation_check import config
from citation_check.llm import LMStudioClient
from citation_check.schema import CassationCitation, CitationSet, StatuteCitation
from citation_check.schema.validate import load_citation_file
from citation_check.verification import Status, decide_status, render_summary, verify, write_findings_json

CORPUS = load_citation_file(config.CORPUS_PATH, kind="corpus")


# ------------------------------------------------------------------ the flow chart, branch by branch
@pytest.mark.parametrize("exists,matches,related,expected", [
    (False, None, None, Status.NOT_FOUND),
    (False, True, True, Status.NOT_FOUND),        # existence wins; the claim is irrelevant
    (True, True, True, Status.SUPPORTED),
    (True, True, False, Status.SUPPORTED),
    (True, False, True, Status.CONTRADICTS),
    (True, False, False, Status.AMBIGUOUS),
])
def test_decide_status_all_branches(exists, matches, related, expected):
    assert decide_status(exists, matches, related) is expected


def test_decide_status_requires_judgement_when_citation_exists():
    with pytest.raises(ValueError):
        decide_status(True)
    with pytest.raises(ValueError):
        decide_status(True, False)


# ------------------------------------------------------------------ verify() with a fake LLM
def fake_llm(tmp_path, judge):
    """judge(user_text) -> (matches, related) ; records every call."""
    calls = []

    def handler(req):
        user = json.loads(req.content)["messages"][-1]["content"]
        calls.append(user)
        if judge == "DOWN":
            return httpx.Response(400, text="boom")
        m, r = judge(user)
        out = {"reason": "سبب", "matches_claim": m, "related": r}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(out, ensure_ascii=False)},
                                                       "finish_reason": "stop"}]})

    c = LMStudioClient("http://x/v1", "m", log_path=tmp_path / "l.jsonl", transport=httpx.MockTransport(handler),
                       max_retries=0, backoff_s=0)
    c.calls_seen = calls
    return c


def S(n, y, a, content="ادعاء", span=None):
    return StatuteCitation(law_number=n, year=y, article=a, content=content, span=span, citation_text=f"م{a}")


def C(n, y, content="ادعاء", span=None):
    return CassationCitation(appeal_number=n, year=y, content=content, span=span, citation_text=f"ق{n}")


def test_four_statuses_and_llm_only_called_for_existing_ids(tmp_path):
    ex = CitationSet(
        statute=[S("41", "2008", "23", "ثلاثون", [10, 20]),            # exists, judged match -> SUPPORTED
                 S("77", "2011", "99", "x", [30, 40]),                 # not in corpus -> NOT_FOUND (no LLM)
                 S("77", "2011", "12", "y", [50, 60])],                # exists, judged contradicts
        cassation=[C("2210", "2019", "unrelated", [70, 80]),           # exists, judged unrelated -> AMBIGUOUS
                   C("5555", "2021", "fake", [90, 99])],               # NOT_FOUND (no LLM)
    )

    def judge(user):
        if "ثلاثون" in user:
            return True, True
        if "unrelated" in user:
            return False, False
        return False, True

    llm = fake_llm(tmp_path, judge)
    rep = verify(ex, CORPUS, llm, draft_name="d.txt")
    st = {f.id: f.status for f in rep.findings}
    assert st == {"S:41/2008:23": Status.SUPPORTED, "S:77/2011:99": Status.NOT_FOUND, "S:77/2011:12": Status.CONTRADICTS,
                  "C:2210/2019": Status.AMBIGUOUS, "C:5555/2021": Status.NOT_FOUND}
    assert len(llm.calls_seen) == 3                       # only the three that exist
    assert rep.counts == {"SUPPORTED": 1, "CONTRADICTS": 1, "AMBIGUOUS": 1, "NOT_FOUND": 2}
    assert [f.id for f in rep.findings] == ["S:41/2008:23", "S:77/2011:99", "S:77/2011:12", "C:2210/2019", "C:5555/2021"]  # document order
    nf = next(f for f in rep.findings if f.id == "S:77/2011:99")
    assert nf.closest_corpus_id and "article 99 is not" in nf.reason and nf.matched_corpus_id is None
    ok = rep.findings[0]
    assert ok.matched_corpus_id == "S:41/2008:23" and "ثلاثون" in ok.corpus_content and ok.span == [10, 20] and ok.kind == "statute"


def test_articles_cited_together_share_the_claim(tmp_path):
    # 'للمادتين (23) و(23 مكرر)': one quote, one claim that only matches 23 bis
    claim_text = "يوقف ميعاد الطعن بالوفاة"
    ex = CitationSet(statute=[S("41", "2008", "23", claim_text, [10, 40]), S("41", "2008", "23bis", claim_text, [10, 40]),
                              S("41", "2008", "77", claim_text, [10, 40])])
    # matches only article 23 bis on its own; the combined ('cited together') check does NOT match, so the
    # fallback applies (and article 77, which is not in the corpus, is never judged)
    llm = fake_llm(tmp_path, lambda user: ("23 of law" not in user and "(cited together)" not in user, True))
    rep = verify(ex, CORPUS, llm)
    st = {f.id: f for f in rep.findings}
    assert st["S:41/2008:23bis"].status is Status.SUPPORTED
    assert st["S:41/2008:23"].status is Status.SUPPORTED and "cited together with S:41/2008:23bis" in st["S:41/2008:23"].reason
    assert st["S:41/2008:77"].status is Status.NOT_FOUND                         # not rescued by the group


def test_claim_covering_both_articles_is_judged_on_the_articles_read_together(tmp_path):
    # the claim mixes article 23 (30 days) and 23 bis (suspension): neither article alone matches it
    claim_text = "ثلاثون يوماً ويوقف الميعاد بالوفاة"
    ex = CitationSet(statute=[S("41", "2008", "23", claim_text, [5, 50]), S("41", "2008", "23bis", claim_text, [5, 50])])
    llm = fake_llm(tmp_path, lambda user: ("[S:41/2008:23]" in user and "[S:41/2008:23bis]" in user, True))
    rep = verify(ex, CORPUS, llm)
    assert [f.status for f in rep.findings] == [Status.SUPPORTED, Status.SUPPORTED]
    assert all("read together" in f.reason for f in rep.findings)
    assert len(llm.calls_seen) == 3          # 2 individual + 1 combined


def test_group_is_found_even_if_spans_differ_by_a_character(tmp_path):
    # regression (hard set H04): the LLM's quote and the regex net's quote of the same sentence differed by 1 char
    claim_text = "ثلاثون يوماً ويوقف الميعاد بالوفاة"
    ex = CitationSet(statute=[S("41", "2008", "23", claim_text, [99, 166]), S("41", "2008", "23bis", claim_text, [99, 167])])
    llm = fake_llm(tmp_path, lambda user: ("[S:41/2008:23]" in user and "[S:41/2008:23bis]" in user, True))
    rep = verify(ex, CORPUS, llm)
    assert [f.status for f in rep.findings] == [Status.SUPPORTED, Status.SUPPORTED]


def test_combined_check_not_run_when_all_members_already_supported(tmp_path):
    ex = CitationSet(statute=[S("41", "2008", "23", "x", [5, 50]), S("41", "2008", "23bis", "x", [5, 50])])
    llm = fake_llm(tmp_path, lambda u: (True, True))
    verify(ex, CORPUS, llm)
    assert len(llm.calls_seen) == 2


def test_cited_together_with_no_matching_article_keeps_individual_statuses(tmp_path):
    ex = CitationSet(statute=[S("41", "2008", "23", "ادعاء خاطئ", [1, 9]), S("41", "2008", "23bis", "ادعاء خاطئ", [1, 9])])
    rep = verify(ex, CORPUS, fake_llm(tmp_path, lambda u: (False, True)))
    assert [f.status for f in rep.findings] == [Status.CONTRADICTS, Status.CONTRADICTS]


def test_same_span_cassations_and_separate_spans_are_not_grouped(tmp_path):
    ex = CitationSet(statute=[S("41", "2008", "23", "x", [1, 9]), S("41", "2008", "23bis", "x", [50, 60])])
    rep = verify(ex, CORPUS, fake_llm(tmp_path, lambda u: ("23 of law" not in u, True)))
    assert {f.id: f.status for f in rep.findings} == {"S:41/2008:23": Status.CONTRADICTS, "S:41/2008:23bis": Status.SUPPORTED}


def test_user_message_contains_corpus_text_and_claim(tmp_path):
    llm = fake_llm(tmp_path, lambda u: (True, True))
    verify(CitationSet(statute=[S("41", "2008", "23", "ادعاء الحكم")]), CORPUS, llm)
    msg = llm.calls_seen[0]
    assert "ميعاد الطعن بالاستئناف ثلاثون يوماً" in msg and "ادعاء الحكم" in msg and "article 23 of law 41/2008" in msg


def test_llm_failure_gives_ambiguous_needs_review_not_a_guess(tmp_path):
    rep = verify(CitationSet(statute=[S("41", "2008", "23")]), CORPUS, fake_llm(tmp_path, "DOWN"))
    f = rep.findings[0]
    assert f.status is Status.AMBIGUOUS and f.needs_review and "claim check failed" in f.reason
    rep = verify(CitationSet(statute=[S("41", "2008", "23")]), CORPUS, None)       # no client at all
    assert rep.findings[0].needs_review


def test_blank_claim_cannot_be_judged(tmp_path):
    llm = fake_llm(tmp_path, lambda u: (True, True))
    rep = verify(CitationSet(statute=[S("41", "2008", "23", content="  ")]), CORPUS, llm)
    assert rep.findings[0].status is Status.AMBIGUOUS and rep.findings[0].needs_review and llm.calls_seen == []


def test_incomplete_citation_is_not_found_with_explanation(tmp_path):
    ex = CitationSet(statute=[StatuteCitation(article="5", content="x", citation_text="المادة 5 من قانون العمل")])
    rep = verify(ex, CORPUS, fake_llm(tmp_path, lambda u: (True, True)))
    f = rep.findings[0]
    assert f.status is Status.NOT_FOUND and f.id is None and "incomplete citation" in f.reason


def test_identical_claims_are_judged_once(tmp_path):
    llm = fake_llm(tmp_path, lambda u: (True, True))
    ex = CitationSet(statute=[S("41", "2008", "23", "نفس الادعاء", [1, 5]), S("41", "2008", "23", "نفس الادعاء", [100, 105])])
    rep = verify(ex, CORPUS, llm)
    assert len(rep.findings) == 2 and len(llm.calls_seen) == 1


def test_extraction_incomplete_flag_and_warnings_are_carried(tmp_path):
    rep = verify(CitationSet(), CORPUS, None, extraction_complete=False, extraction_warnings=["w1"])
    assert not rep.extraction_complete and rep.warnings == ["w1"] and rep.counts["SUPPORTED"] == 0
    assert "could not be processed" in render_summary(rep)


def test_summary_and_json_output(tmp_path):
    ex = CitationSet(statute=[S("77", "2011", "99", "x", [30, 40])], cassation=[C("456", "2015", "y", [5, 9])])
    rep = verify(ex, CORPUS, fake_llm(tmp_path, lambda u: (False, True)), draft_name="draft.txt")
    text = render_summary(rep)
    assert "NOT_FOUND: 1" in text and "CONTRADICTS: 1" in text and "S:77/2011:99" in text
    assert text.index("NOT_FOUND (1)") < text.index("CONTRADICTS (1)")        # most worrying first
    out = write_findings_json(rep, tmp_path / "o" / "findings.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["counts"]["NOT_FOUND"] == 1 and data["findings"][0]["status"] in {"CONTRADICTS", "NOT_FOUND"}
    assert {"kind", "status", "span"} <= set(data["findings"][0])
