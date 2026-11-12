"""Edge cases from the roadmap: no citations, incomplete citations, repetition, mixed languages, LM Studio problems."""
import json

import httpx
import pytest

from citation_check import config
from citation_check.check import check_draft
from citation_check.cli import main
from citation_check.llm import LLMError, LMStudioClient
from citation_check.verification import Status, render_summary, write_findings_json

ENTRY = {"law_number": None, "year": None, "article": None, "law_name": None, "clause": None, "content": "", "citation_text": None}


def llm(tmp_path, reply, *, max_retries=0):
    """Fake LM Studio. reply: dict -> extraction JSON for every extraction call, or 'GARBAGE' for invalid JSON.
    Claim checks always answer 'matches'."""
    def handler(req):
        body = json.loads(req.content)
        if body["response_format"]["json_schema"]["name"] == "claim_judgement":
            out = {"reason": "ok", "matches_claim": True, "related": True}
        elif reply == "GARBAGE":
            return httpx.Response(200, json={"choices": [{"message": {"content": "not json at all"}, "finish_reason": "stop"}]})
        else:
            out = reply
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(out, ensure_ascii=False)}, "finish_reason": "stop"}]})

    return LMStudioClient("http://x/v1", "m", log_path=tmp_path / "l.jsonl", transport=httpx.MockTransport(handler),
                          max_retries=max_retries, backoff_s=0)


def draft_file(tmp_path, text, name="d.txt"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


EMPTY = {"statute": [], "cassation": []}


def test_draft_with_no_citations_gives_empty_findings(tmp_path):
    d = draft_file(tmp_path, "المحكمة: بعد الاطلاع على الأوراق قررت المحكمة رد الدعوى لعدم الثبوت.")
    out = check_draft(d, client=llm(tmp_path, EMPTY))
    r = out.report
    assert r.findings == [] and r.counts == {"SUPPORTED": 0, "CONTRADICTS": 0, "AMBIGUOUS": 0, "NOT_FOUND": 0}
    assert r.extraction_complete and "total 0" in render_summary(r)
    assert json.loads(write_findings_json(r, tmp_path / "f.json").read_text(encoding="utf-8"))["findings"] == []


def test_citation_without_enough_detail_is_reported_not_dropped_or_guessed(tmp_path):
    d = draft_file(tmp_path, "وعملاً بأحكام المادة (5) من قانون العمل فإن العامل يستحق الإجازة.")
    reply = {"statute": [{**ENTRY, "article": "5", "law_name": "قانون العمل", "content": "يستحق العامل الإجازة",
                          "citation_text": "المادة (5) من قانون العمل"}], "cassation": []}
    out = check_draft(d, client=llm(tmp_path, reply))
    f = out.report.findings
    assert len(f) == 1 and f[0].status is Status.NOT_FOUND and f[0].id is None
    assert "incomplete citation" in f[0].reason and "law number" in f[0].reason
    assert any("incomplete citation" in w for w in out.report.warnings)


def test_same_citation_repeated(tmp_path):
    s = "وعملاً بأحكام المادة (9) من قانون المالكين والمستأجرين رقم (15) لسنة 2015 لا يجوز الإخلاء قبل الإنذار الكتابي."
    d = draft_file(tmp_path, "\n\n".join([s, "وقائع أخرى.", s, "وقائع ثالثة.", s]))
    out = check_draft(d, client=llm(tmp_path, EMPTY))          # regex net only
    assert [f.id for f in out.report.findings] == ["S:15/2015:9"]     # identical sentence three times -> one finding

    different = [f"وعملاً بأحكام المادة (9) من قانون المالكين والمستأجرين رقم (15) لسنة 2015 {c}." for c in
                 ("يلزم الإنذار الكتابي قبل الإخلاء", "تبدأ مدة التقادم من تاريخ العقد", "يحق للمؤجر رفع الأجرة كل سنة")]
    d2 = draft_file(tmp_path, "\n\n".join(different), "d2.txt")
    out2 = check_draft(d2, client=llm(tmp_path, EMPTY))
    assert [f.id for f in out2.report.findings] == ["S:15/2015:9"] * 3     # different claims about it: each is checked


def test_mixed_arabic_and_english_in_one_sentence(tmp_path):
    d = draft_file(tmp_path, "استند الدفاع إلى Article 40 of Commercial Law No. 63 of 2009 وإلى المادة (٩) من قانون المالكين والمستأجرين رقم (١٥) لسنة ٢٠١٥ وإلى Cassation Decision No. 87 of 2018 الصادر عن محكمة النقض.")
    out = check_draft(d, client=llm(tmp_path, EMPTY))
    assert sorted(f.id for f in out.report.findings) == ["C:87/2018", "S:15/2015:9", "S:63/2009:40"]
    assert all(f.status is Status.SUPPORTED for f in out.report.findings)


def test_llm_returning_garbage_degrades_safely(tmp_path):
    d = draft_file(tmp_path, "عملاً بأحكام المادة (9) من قانون المالكين والمستأجرين رقم (15) لسنة 2015 لا يجوز الإخلاء إلا بعد إنذار كتابي.")
    out = check_draft(d, client=llm(tmp_path, "GARBAGE"))
    assert not out.extraction.complete and not out.report.extraction_complete
    assert any("LLM failed" in w for w in out.report.warnings)
    assert [x.id for x in out.report.findings] == ["S:15/2015:9"]      # the regex net still found the citation


# ----------------------------------------------------------------------------- LM Studio availability
def test_ping_reports_unreachable_and_missing_model():
    def down(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMError, match="cannot reach LM Studio"):
        LMStudioClient("http://x/v1", "m", transport=httpx.MockTransport(down)).ping()

    models = httpx.MockTransport(lambda req: httpx.Response(200, json={"data": [{"id": "other-model"}]}))
    with pytest.raises(LLMError, match="'m' is not available.*other-model"):
        LMStudioClient("http://x/v1", "m", transport=models).ping()
    ok = httpx.MockTransport(lambda req: httpx.Response(200, json={"data": [{"id": "m"}]}))
    LMStudioClient("http://x/v1", "m", transport=ok).ping()


def test_cli_exit_codes_when_lm_studio_is_down(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "LMSTUDIO_BASE_URL", "http://127.0.0.1:9/v1")      # nothing listens on port 9
    d = draft_file(tmp_path, "عملاً بأحكام المادة (9) من قانون المالكين والمستأجرين رقم (15) لسنة 2015.")
    assert main(["check", str(d), "-o", str(tmp_path / "f.json")]) == 4
    err = capsys.readouterr().err
    assert "cannot reach LM Studio" in err and "Start the local server" in err
    assert not (tmp_path / "f.json").exists()                                   # no half-baked report
    assert main(["extract", str(d), "-o", str(tmp_path / "e.json")]) == 4
    assert main(["extract", str(d), "-o", str(tmp_path / "e.json"), "--no-llm"]) == 0   # regex-only needs no LM Studio


def test_bad_input_is_reported_before_lm_studio_is_contacted(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "LMSTUDIO_BASE_URL", "http://127.0.0.1:9/v1")
    assert main(["check", str(tmp_path / "missing.txt")]) == 2
    assert "not found" in capsys.readouterr().err
    d = draft_file(tmp_path, "نص الحكم كاملاً هنا")
    assert main(["check", str(d), "--corpus", str(tmp_path / "no_corpus.json")]) == 2
    assert "corpus" in capsys.readouterr().err
