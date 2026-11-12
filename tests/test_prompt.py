import json
import re

import pytest

from citation_check import config
from citation_check.extraction import prompt
from citation_check.schema import CitationSet
from citation_check.schema.validate import load_citation_file

PHRASINGS = prompt.PROMPT_DIR / "phrasings.json"


def test_phrasings_cover_both_kinds_and_languages():
    p = json.loads(PHRASINGS.read_text(encoding="utf-8"))
    for kind in ("statute", "cassation"):
        for lang in ("ar", "en"):
            assert len(p[kind][lang]) >= 3, (kind, lang)


def test_system_prompt_mentions_the_key_rules():
    s = prompt.system_prompt()
    for needle in ("Never invent", "القانون ذاته", "citation_text", "null", "محكمة النقض", "Court of Cassation"):
        assert needle in s, needle


def test_response_schema_fields_exist_in_shared_models_and_exclude_id():
    sch = prompt.response_schema()
    stat = set(sch["properties"]["statute"]["items"]["properties"])
    cass = set(sch["properties"]["cassation"]["items"]["properties"])
    assert "id" not in stat | cass and "source" not in stat | cass
    assert stat <= set(CitationSet.model_fields["statute"].annotation.__args__[0].model_fields)
    assert cass <= set(CitationSet.model_fields["cassation"].annotation.__args__[0].model_fields)
    # every property required + nullable (strict mode)
    for sub in (sch["properties"]["statute"]["items"], sch["properties"]["cassation"]["items"]):
        assert set(sub["required"]) == set(sub["properties"])
        assert all(v == {"type": ["string", "null"]} for v in sub["properties"].values())


def test_few_shot_outputs_are_valid_and_build_expected_ids():
    ids = []
    for ex in prompt.examples():
        cs = CitationSet.model_validate(ex["output"])
        ids += [s.id for s in cs.statute] + [c.id for c in cs.cassation]
        # citation_text must be a literal quote of the example input
        for it in [*cs.statute, *cs.cassation]:
            assert it.citation_text in ex["input"], it.citation_text
    assert ids == ["S:22/2006:55", "S:22/2006:56", "S:22/2006:56bis", "C:712/2010",
                   "S:9/2004:14", "S:9/2004:15", "C:118/2012", None,
                   "S:5/2001:12", "S:5/2001:13", "C:77/2003"]


def test_few_shot_does_not_leak_corpus_or_gold_ids():
    corpus = load_citation_file(config.CORPUS_PATH, kind="corpus")
    corpus_ids = {c.id for c in [*corpus.statute, *corpus.cassation]}
    for ex in prompt.examples():
        cs = CitationSet.model_validate(ex["output"])
        for it in [*cs.statute, *cs.cassation]:
            assert it.id not in corpus_ids


def test_build_messages_structure():
    msgs = prompt.build_messages("نص الحكم")
    roles = [m["role"] for m in msgs]
    assert roles == ["system"] + ["user", "assistant"] * len(prompt.examples()) + ["user"]
    assert msgs[-1]["content"] == "نص الحكم"
    json.loads(msgs[2]["content"])  # assistant turns are valid JSON


def test_null_content_from_llm_is_accepted():
    cs = CitationSet.model_validate({"statute": [{"law_number": "1", "year": "2000", "article": "1", "content": None}]})
    assert cs.statute[0].content == "" and cs.statute[0].id == "S:1/2000:1"


def test_old_prompt_versions_stay_loadable_for_comparison():
    assert prompt.system_prompt("extraction_v1") != prompt.system_prompt("extraction_v2")
    assert len(prompt.examples("extraction_v1")) == 3 and len(prompt.examples("extraction_v2")) == 4


def test_version_is_in_file_names():
    assert (prompt.PROMPT_DIR / f"{prompt.PROMPT_VERSION}.system.md").exists()
    assert (prompt.PROMPT_DIR / f"{prompt.PROMPT_VERSION}.examples.json").exists()
    assert re.fullmatch(r"extraction_v\d+", prompt.PROMPT_VERSION)
