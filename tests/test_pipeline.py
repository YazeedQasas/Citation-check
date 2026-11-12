"""Pipeline tests with a fake LLM (deterministic, no LM Studio needed)."""
import json

import httpx

from citation_check.extraction.chunking import halve, split_chunks
from citation_check.extraction.grounding import FoldedText, locate_quote
from citation_check.extraction.loader import from_text
from citation_check.extraction.pipeline import extract_citations
from citation_check.llm import LMStudioClient
from citation_check.schema import CitationSet

ENTRY = {"law_number": None, "year": None, "article": None, "law_name": None, "clause": None,
         "content": "", "citation_text": None}
CENTRY = {"appeal_number": None, "year": None, "chamber": None, "date": None, "content": "", "citation_text": None}


def S(**kw):
    return {**ENTRY, **kw}


def C(**kw):
    return {**CENTRY, **kw}


def fake_client(tmp_path, replies):
    """replies: list of dicts (or callables taking the user text) returned in order, then repeated."""
    state = {"i": 0, "seen": []}

    def handler(req):
        body = json.loads(req.content)
        user = body["messages"][-1]["content"]
        state["seen"].append(user)
        r = replies[min(state["i"], len(replies) - 1)]
        state["i"] += 1
        if callable(r):
            r = r(user)
        if r == "TRUNCATED":
            return httpx.Response(200, json={"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(r, ensure_ascii=False)},
                                                       "finish_reason": "stop"}]})

    c = LMStudioClient("http://x/v1", "m", log_path=tmp_path / "log.jsonl", transport=httpx.MockTransport(handler), backoff_s=0)
    c.state = state
    return c


DRAFT = (
    "عملاً بأحكام المادة (٥٥) من قانون الشركات رقم (٢٢) لسنة ٢٠٠٦ فإن الشركة تلتزم بتقديم ميزانيتها.\n\n"
    "وفي ذلك قضت محكمة النقض بأن الحق لا يسقط (نقض حقوق رقم ٧١٢ لسنة ٢٠١٠).\n\n"
    "وسنداً للمادة (٥٧) من القانون ذاته فإن للمساهم حق الاطلاع."
)


def test_chunking_covers_everything_and_overlaps():
    paras = [f"فقرة رقم {i} " + "كلمة " * 60 for i in range(20)]
    text = "\n\n".join(paras)
    chunks = split_chunks(text, 1500)
    assert len(chunks) > 3
    assert all(len(c.text) <= 1500 and c.text == text[c.start:c.end] for c in chunks)
    assert chunks[0].start == 0 and chunks[-1].end >= len(text.rstrip())
    covered = set()
    for c in chunks:
        covered.update(range(c.start, c.end))
    assert all(i in covered for i, ch in enumerate(text) if not ch.isspace())
    assert any(chunks[i + 1].start < chunks[i].end for i in range(len(chunks) - 1))  # overlap


def test_chunking_handles_one_giant_paragraph_and_short_text():
    assert len(split_chunks("نص قصير", 1000)) == 1
    giant = "جملة طويلة جداً " * 400
    chunks = split_chunks(giant, 1000)
    assert all(len(c.text) <= 1000 for c in chunks) and len(chunks) >= 6
    assert split_chunks("  ", 1000) == []


def test_halve():
    c = split_chunks("أ" * 100 + ".\n" + "ب" * 100, 1000)[0]
    a, b = halve(c)
    assert a.text + b.text == c.text and a.end == b.start


def test_extraction_with_grounding_same_law_and_sorting(tmp_path):
    reply = {
        "statute": [
            S(law_number="٢٢", year="٢٠٠٦", article="٥٥", content="تلتزم الشركة بتقديم ميزانيتها.",
              citation_text="المادة (٥٥) من قانون الشركات رقم (٢٢) لسنة ٢٠٠٦"),
            S(article="٥٧", content="للمساهم حق الاطلاع.", citation_text="للمادة (٥٧) من القانون ذاته"),  # law left null
        ],
        "cassation": [C(appeal_number="٧١٢", year="٢٠١٠", content="الحق لا يسقط.", citation_text="نقض حقوق رقم ٧١٢ لسنة ٢٠١٠")],
    }
    d = from_text(DRAFT)
    res = extract_citations(d, fake_client(tmp_path, [reply]))
    ids = [c.id for c in res.citations.statute] + [c.id for c in res.citations.cassation]
    assert ids == ["S:22/2006:55", "S:22/2006:57", "C:712/2010"]
    assert res.complete and res.llm_calls == 1 and res.n_chunks == 1
    s = res.citations.statute[1]
    assert s.origin == "llm" and DRAFT[s.span[0]:s.span[1]] == "للمادة (٥٧) من القانون ذاته"
    assert res.citations.statute[0].span[0] < s.span[0]


def test_garbled_year_is_repaired_from_quote(tmp_path):
    reply = {"statute": [S(law_number="22", year="٢�\xa0٨", article="55", content="x",
                           citation_text="المادة (٥٥) من قانون الشركات رقم (٢٢) لسنة ٢٠٠٦")], "cassation": []}
    res = extract_citations(from_text(DRAFT), fake_client(tmp_path, [reply]))
    assert res.citations.statute[0].id == "S:22/2006:55"
    assert any("repaired year" in w for w in res.warnings)


def test_invented_quote_is_dropped_and_wrong_number_is_corrected(tmp_path):
    reply = {"statute": [
        S(law_number="9", year="1999", article="1", content="invented", citation_text="المادة (١) من قانون رقم (٩) لسنة ١٩٩٩"),
        S(law_number="22", year="2006", article="55", content="x", citation_text="المادة (٥٥) من قانون الشركات رقم (٢٢) لسنة ٢٠٠٦"),
    ], "cassation": [C(appeal_number="999", year="2010", content="y", citation_text="نقض حقوق رقم ٧١٢ لسنة ٢٠١٠")]}
    res = extract_citations(from_text(DRAFT), fake_client(tmp_path, [reply]))
    assert [c.id for c in res.citations.cassation] == ["C:712/2010"]          # 999 corrected from the quote
    assert "S:9/1999:1" not in [c.id for c in res.citations.statute]
    assert any("dropped ungrounded" in w for w in res.warnings)


def test_regex_safety_net_adds_missed_citations(tmp_path):
    empty = {"statute": [], "cassation": []}
    res = extract_citations(from_text(DRAFT), fake_client(tmp_path, [empty]))
    assert [c.id for c in res.citations.statute] == ["S:22/2006:55", "S:22/2006:57"]
    assert [c.id for c in res.citations.cassation] == ["C:712/2010"]
    assert all(c.origin == "regex" for c in [*res.citations.statute, *res.citations.cassation])
    assert "ميزانيتها" in res.citations.statute[0].content   # claim = enclosing sentence
    res2 = extract_citations(from_text(DRAFT), fake_client(tmp_path, [empty]), regex_net=False)
    assert res2.citations.statute == [] and res2.citations.cassation == []


def test_multi_chunk_merge_dedupes_overlap(tmp_path):
    paras = [f"الفقرة {i} " + "كلمة " * 40 for i in range(12)]
    paras[3] += " عملاً بأحكام المادة (٥) من قانون رقم (٧) لسنة ٢٠٢٠ تلتزم الشركة."
    text = "\n\n".join(paras)

    def reply(user):
        if "المادة (٥) من قانون رقم (٧)" in user:
            return {"statute": [S(law_number="7", year="2020", article="5", content="تلتزم الشركة.",
                                  citation_text="المادة (٥) من قانون رقم (٧) لسنة ٢٠٢٠")], "cassation": []}
        return {"statute": [], "cassation": []}

    c = fake_client(tmp_path, [reply])
    res = extract_citations(from_text(text), c, max_chars=800, regex_net=False)
    assert res.n_chunks > 2 and res.llm_calls == res.n_chunks
    assert [x.id for x in res.citations.statute] == ["S:7/2020:5"]   # seen by 2 overlapping chunks, kept once


def test_truncated_reply_halves_the_chunk(tmp_path):
    ok = {"statute": [], "cassation": []}
    c = fake_client(tmp_path, ["TRUNCATED", ok, ok])
    text = ("جملة عادية في الحكم. " * 60 + "\n") * 2
    res = extract_citations(from_text(text), c, max_chars=5000, regex_net=False)
    assert res.complete and res.llm_calls == 2 and len(c.state["seen"]) == 3


def test_llm_failure_marks_result_incomplete_but_regex_still_works(tmp_path):
    def down(req):
        raise httpx.ConnectError("refused")

    c = LMStudioClient("http://x/v1", "m", log_path=tmp_path / "l.jsonl", transport=httpx.MockTransport(down),
                       max_retries=0, backoff_s=0)
    res = extract_citations(from_text(DRAFT), c)
    assert not res.complete and any("LLM failed" in w for w in res.warnings)
    assert len(res.citations.statute) == 2 and len(res.citations.cassation) == 1


def test_same_quote_entries_are_kept_for_plural_articles(tmp_path):
    t = "عملاً بالمادة (٥٥) من قانون الشركات رقم (٢٢) لسنة ٢٠٠٦. وسنداً للمادتين (٥٦) و(٥٦ مكرر) من القانون ذاته يحق الاطلاع."
    q = "للمادتين (٥٦) و(٥٦ مكرر) من القانون ذاته"
    reply = {"statute": [
        S(law_number="22", year="2006", article="55", content="a", citation_text="المادة (٥٥) من قانون الشركات رقم (٢٢) لسنة ٢٠٠٦"),
        S(article="56", content="يحق الاطلاع", citation_text=q), S(article="56 مكرر", content="يحق الاطلاع", citation_text=q),
    ], "cassation": []}
    res = extract_citations(from_text(t), fake_client(tmp_path, [reply]))
    assert [c.id for c in res.citations.statute] == ["S:22/2006:55", "S:22/2006:56", "S:22/2006:56bis"]


def test_folded_locate_ignores_digits_script_and_brackets():
    f = FoldedText("وعملاً بالمادة (٢٣) من قانون")
    hit = f.find("بالمادة 23 من")
    assert hit is not None and "وعملاً بالمادة (٢٣) من قانون"[hit[0]:hit[1]] == "بالمادة (٢٣) من"
    assert locate_quote(f, "غير موجود", 0, set()) is None


def test_result_serialises_to_shared_schema():
    cs = CitationSet.model_validate({"statute": [{"law_number": "1", "year": "2000", "article": "1", "span": [0, 5], "origin": "llm"}]})
    assert cs.model_dump(exclude_none=True)["statute"][0]["span"] == [0, 5]
