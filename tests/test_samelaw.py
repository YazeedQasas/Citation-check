from citation_check.extraction.samelaw import is_same_law_ref, resolve_same_law
from citation_check.schema import StatuteCitation


def S(article, quote, law=None, year=None, name=None):
    return StatuteCitation(law_number=law, year=year, article=article, law_name=name, citation_text=quote)


def test_detects_arabic_and_english_wording():
    for q in ("المادة (14) من القانون ذاته", "من القانون نفسه", "ذات القانون", "Article 15 of the same law", "said law"):
        assert is_same_law_ref(q), q
    assert not is_same_law_ref("المادة (14) من قانون رقم (15) لسنة 2015")
    assert not is_same_law_ref(None)


def test_fills_from_previous_full_citation_in_document_order():
    out, w = resolve_same_law([
        (50, S("77", "المادة (۷۷) من القانون ذاته")),                      # given out of order on purpose
        (0, S("31", "المادة (۳۱) من قانون رقم (۸) لسنة ۲۰۱۳", "8", "2013", "قانون العمل")),
    ])
    assert [e.id for e in out] == ["S:8/2013:31", "S:8/2013:77"]
    assert out[1].law_name == "قانون العمل" and w == []


def test_overrides_a_wrong_model_resolution_and_warns():
    out, w = resolve_same_law([
        (0, S("1", "Article 1 of Labour Law No. 8 of 2013", "8", "2013")),
        (40, S("2", "Article 2 of the same law", "99", "1999")),
    ])
    assert out[1].id == "S:8/2013:2" and len(w) == 1 and "resolved to 8/2013" in w[0]


def test_uses_nearest_earlier_law_not_the_first():
    out, _ = resolve_same_law([
        (0, S("1", "المادة 1 من قانون رقم 1 لسنة 2001", "1", "2001")),
        (30, S("2", "المادة 2 من قانون رقم 2 لسنة 2002", "2", "2002")),
        (60, S("3", "المادة 3 من القانون ذاته")),
    ])
    assert out[2].id == "S:2/2002:3"


def test_no_earlier_law_leaves_entry_without_id_and_warns():
    out, w = resolve_same_law([(0, S("5", "المادة (5) من القانون ذاته"))])
    assert out[0].id is None and len(w) == 1
