import json

import pytest

from citation_check import config
from citation_check.schema.validate import load_citation_file
from citation_check.verification import claim

CORPUS = load_citation_file(config.CORPUS_PATH, kind="corpus")


def test_examples_cover_all_outcomes_and_languages():
    outs = [(e["output"]["matches_claim"], e["output"]["related"]) for e in claim.examples()]
    assert (True, True) in outs and (False, True) in outs and (False, False) in outs
    assert sum(e["kind"] == "cassation" for e in claim.examples()) >= 1
    assert any(e["claim"].isascii() for e in claim.examples())          # an English claim
    for e in claim.examples():
        claim.ClaimJudgement.model_validate(e["output"])


def test_examples_do_not_leak_corpus_text():
    corpus_texts = {c.content for c in [*CORPUS.statute, *CORPUS.cassation]}
    for e in claim.examples():
        assert e["authoritative"] not in corpus_texts


def test_messages_structure_and_content():
    msgs = claim.build_messages("statute", "المادة 9", "نص المادة", "ادعاء")
    assert [m["role"] for m in msgs] == ["system"] + ["user", "assistant"] * len(claim.examples()) + ["user"]
    last = msgs[-1]["content"]
    assert "نص المادة" in last and "ادعاء" in last and "statute article" in last
    assert "Court of Cassation" in claim.user_message("cassation", "x", "a", "b")
    json.loads(msgs[2]["content"])


def test_schema_has_reason_first_and_is_strict():
    s = claim.response_format()["json_schema"]
    assert s["strict"] is True
    assert list(s["schema"]["properties"]) == ["reason", "matches_claim", "related"]


def test_match_implies_related():
    j = claim.ClaimJudgement.model_validate({"reason": "x", "matches_claim": True, "related": False})
    assert j.related is True
    with pytest.raises(ValueError):
        claim.ClaimJudgement.model_validate({"reason": "x", "matches_claim": "maybe", "related": True})
