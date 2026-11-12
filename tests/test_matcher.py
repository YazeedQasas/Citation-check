from citation_check import config
from citation_check.schema import CassationCitation, StatuteCitation
from citation_check.schema.validate import load_citation_file
from citation_check.verification.matcher import CorpusIndex, _edit_distance_le1

CORPUS = load_citation_file(config.CORPUS_PATH, kind="corpus")
IDX = CorpusIndex(CORPUS)


def S(n, y, a):
    return StatuteCitation(law_number=n, year=y, article=a)


def C(n, y):
    return CassationCitation(appeal_number=n, year=y)


def test_hits_return_the_corpus_entry_regardless_of_digit_script():
    r = IDX.lookup(S("٤١", "٢٠٠٨", "٢٣ مكرر"))
    assert r.exists and r.entry.id == "S:41/2008:23bis" and "يوقف ميعاد الطعن" in r.entry.content
    r = IDX.lookup(C("۴۵۶", "۲۰۱۵"))
    assert r.exists and r.entry.id == "C:456/2015"


def test_kind_matters_same_numbers_different_kind_do_not_match():
    # a cassation ID can never match a statute entry and vice versa
    assert not IDX.lookup(C("77", "2011")).exists


def test_not_found_article_of_known_law_lists_available_articles():
    r = IDX.lookup(S("77", "2011", "99"))
    assert not r.exists and r.closest_id.startswith("S:77/2011:")
    assert "article 99 is not" in r.hint and "12" in r.hint and "15" in r.hint


def test_not_found_one_digit_off():
    r = IDX.lookup(C("457", "2015"))
    assert not r.exists and r.closest_id == "C:456/2015" and "one digit" in r.hint
    r = IDX.lookup(S("63", "2010", "40"))          # year off by one digit
    assert r.closest_id == "S:63/2009:40"


def test_not_found_law_number_exists_for_another_year():
    r = IDX.lookup(S("8", "1990", "5"))
    assert not r.exists and "only for year" in r.hint


def test_not_found_nothing_close():
    r = IDX.lookup(C("5555", "2021"))
    assert not r.exists and r.closest_id is None and "no cassation decision" in r.hint
    assert IDX.lookup(S("500", "1980", "1")).hint == "law not found in the corpus"


def test_incomplete_citation_is_reported_as_such():
    r = IDX.lookup(StatuteCitation(article="5", citation_text="المادة (5) من قانون العمل"))
    assert not r.exists and "incomplete citation" in r.hint and "law number" in r.hint and "year" in r.hint
    assert "appeal number" in IDX.lookup(CassationCitation(year="2020")).hint


def test_edit_distance_helper():
    assert _edit_distance_le1("456", "457") and _edit_distance_le1("456", "4566") and _edit_distance_le1("456", "46")
    assert not _edit_distance_le1("456", "789") and not _edit_distance_le1("456", "45678")
