import json

from citation_check import config
from citation_check.cli import main
from citation_check.extraction.loader import load_draft
from citation_check.extraction.output import read_extracted_json, to_json_dict, write_extracted_json
from citation_check.extraction.pipeline import extract_citations
from citation_check.llm import LMStudioClient


def _regex_only(draft_name):
    with LMStudioClient("http://unused/v1", "m") as c:
        return extract_citations(load_draft(config.DRAFTS_DIR / draft_name), c, use_llm=False)


def test_output_has_two_sections_and_roundtrips(tmp_path):
    res = _regex_only("draft_05.txt")
    out = write_extracted_json(res, tmp_path / "sub" / "extracted.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert set(data) == {"statute", "cassation"}
    ids = [s["id"] for s in data["statute"]] + [c["id"] for c in data["cassation"]]
    assert sorted(ids) == sorted(["S:8/2013:31", "S:8/2013:77", "S:77/2011:15", "C:912/2014"])
    back = read_extracted_json(out)
    assert [s.id for s in back.statute] == [s["id"] for s in data["statute"]]
    assert all(s["origin"] == "regex" and len(s["span"]) == 2 for s in data["statute"])
    assert "المادة" in out.read_text(encoding="utf-8")  # Arabic is written as Arabic, not as escapes


def test_empty_result_still_valid(tmp_path):
    from citation_check.extraction.loader import from_text
    with LMStudioClient("http://unused/v1", "m") as c:
        res = extract_citations(from_text("حكم لا يحتوي على أي استشهاد قانوني."), c, use_llm=False)
    assert to_json_dict(res) == {"statute": [], "cassation": []}


def test_cli_extract_no_llm(tmp_path, capsys):
    out = tmp_path / "e.json"
    code = main(["extract", str(config.DRAFTS_DIR / "draft_02.txt"), "-o", str(out), "--no-llm"])
    assert code == 0
    assert "3 statute + 1 cassation" in capsys.readouterr().out
    data = json.loads(out.read_text(encoding="utf-8"))
    # article 23 is cited twice in draft_02 (alone, and in 'المادتين 23 و23 مكرر'): two occurrences, both kept
    assert sorted(s["id"] for s in data["statute"]) == ["S:41/2008:23", "S:41/2008:23", "S:41/2008:23bis"]
    assert [c["id"] for c in data["cassation"]] == ["C:1203/2017"]


def test_cli_reports_bad_input(tmp_path, capsys):
    assert main(["extract", str(tmp_path / "missing.txt")]) == 2
    assert "not found" in capsys.readouterr().err
