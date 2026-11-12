import json

import pytest

from citation_check import config
from citation_check.schema.validate import CitationFileError, load_citation_file, validate_citation_data

SAMPLE = config.ROOT / "data" / "samples" / "extracted.sample.json"


def test_sample_extracted_file_is_valid_and_ids_are_recomputed():
    cs = load_citation_file(SAMPLE, kind="extracted")
    assert [s.id for s in cs.statute] == ["S:15/2015:9"]
    assert [c.id for c in cs.cassation] == ["C:87/2018"]


def test_extracted_allows_incomplete_citation_but_corpus_does_not():
    data = {"statute": [{"law_number": "5", "year": "2000", "content": "x"}]}  # no article
    cs = validate_citation_data(data, kind="extracted")
    assert cs.statute[0].id is None
    with pytest.raises(CitationFileError, match="no ID"):
        validate_citation_data(data, kind="corpus")


def test_unknown_fields_are_rejected_with_readable_error():
    with pytest.raises(CitationFileError, match="invalid extracted JSON"):
        validate_citation_data({"statute": [{"bogus": 1}]}, kind="extracted")


def test_bad_files(tmp_path):
    with pytest.raises(CitationFileError, match="not found"):
        load_citation_file(tmp_path / "nope.json", kind="corpus")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(CitationFileError, match="not valid JSON"):
        load_citation_file(bad, kind="corpus")


def test_built_corpus_loads_strictly():
    cs = load_citation_file(config.CORPUS_PATH, kind="corpus")
    assert len(cs.statute) == 8 and len(cs.cassation) == 6
    json.dumps(cs.model_dump(exclude_none=True), ensure_ascii=False)  # serialisable
