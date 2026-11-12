import pytest

from citation_check.schema import (
    CassationCitation,
    Corpus,
    StatuteCitation,
    build_cassation_id,
    build_statute_id,
    normalize_article,
    words_to_int,
)

STATUTE_CASES = [
    # (law_number, year, article, expected id)
    ("12", "2010", "23", "S:12/2010:23"),
    ("١٢", "٢٠١٠", "٢٣", "S:12/2010:23"),                    # Arabic-Indic digits
    ("۱۲", "۲۰۱۰", "۲۳", "S:12/2010:23"),                    # Persian digits
    ("012", "2010", "023", "S:12/2010:23"),                   # leading zeros
    (" (12) ", "(2010)", "(23)", "S:12/2010:23"),             # brackets / spaces
    ("١٢", "٢٠١٠", "المادة ٢٣", "S:12/2010:23"),              # 'المادة' prefix
    ("12", "2010", "23 مكرر", "S:12/2010:23bis"),
    ("12", "2010", "٢٣ مكرراً", "S:12/2010:23bis"),
    ("12", "2010", "23 مكرر (أ)", "S:12/2010:23bis-a"),
    ("12", "2010", "5", "S:12/2010:5"),
    ("12", "2010", None, None),                               # incomplete -> no ID
    (None, "2010", "5", None),
]

CASSATION_CASES = [
    ("456", "2015", "C:456/2015"),
    ("٤٥٦", "٢٠١٥", "C:456/2015"),
    ("۴۵۶", "۲۰۱۵", "C:456/2015"),
    ("0456", "2015", "C:456/2015"),
    (" (456) ", " 2015 ", "C:456/2015"),
    ("١", "٢٠٢٠", "C:1/2020"),
    ("1234", "1999", "C:1234/1999"),
    ("٧٨٩", "٢٠٠٨", "C:789/2008"),
    ("456", None, None),
    (None, "2015", None),
]


@pytest.mark.parametrize("law,year,art,expected", STATUTE_CASES)
def test_statute_id(law, year, art, expected):
    assert build_statute_id(law, year, art) == expected


@pytest.mark.parametrize("num,year,expected", CASSATION_CASES)
def test_cassation_id(num, year, expected):
    assert build_cassation_id(num, year) == expected


WORD_CASES = [
    ("الأولى", 1), ("الثانية", 2), ("الثالثة", 3), ("العاشرة", 10),
    ("الحادية عشرة", 11), ("الثانية عشرة", 12), ("الخامسة عشرة", 15), ("التاسعة عشرة", 19),
    ("العشرون", 20), ("الحادية والعشرون", 21), ("الثالثة والعشرون", 23),
    ("الأربعون", 40), ("التاسعة والتسعون", 99), ("ثلاثة", 3), ("الثالث والثلاثون", 33),
]


@pytest.mark.parametrize("text,expected", WORD_CASES)
def test_words_to_int(text, expected):
    assert words_to_int(text) == expected


def test_words_to_int_rejects_non_numbers():
    assert words_to_int("قانون") is None
    assert words_to_int("") is None


def test_article_in_words_and_english():
    assert normalize_article("المادة الثالثة والعشرون") == "23"
    assert normalize_article("المادة الثالثة والعشرون مكرراً") == "23bis"
    assert normalize_article("الخامسة عشرة مكرر (ب)") == "15bis-b"
    assert normalize_article("Article 23 bis") == "23bis"
    assert normalize_article("Art. 9") == "9"
    assert build_statute_id("Twelve?", "2010", "9") is None
    assert build_statute_id("الثانية عشرة", "2010", "الأولى") == "S:12/2010:1"


def test_normalisation_is_idempotent():
    """Models are re-validated whenever an entry is rebuilt or an extracted.json is read back: the canonical
    form must survive that unchanged (regression: '23bis-a' used to turn into '23')."""
    raw = ["23", "٢٣", "23 مكرر", "23 مكرر (أ)", "(٢٣ مكرر (أ))", "23bis", "23bis-a", "15bis-b", "الثالثة والعشرون مكرراً",
           "Article 23 bis", "المادة ٥", "  (7)  ", "12bis-c"]
    for r in raw:
        once = normalize_article(r)
        assert once is not None, r
        assert normalize_article(once) == once, (r, once, normalize_article(once))
    for law, year, art in [("41", "2008", "23bis-a"), ("12", "2010", "5bis")]:
        s = StatuteCitation(law_number=law, year=year, article=art)
        again = StatuteCitation.model_validate(s.model_dump(exclude={"id"}))
        assert again.id == s.id and again.article == s.article


def test_nested_and_stray_brackets_in_articles():
    assert normalize_article("(٢٣ مكرر (أ))") == "23bis-a"
    assert normalize_article("23 مكرر (ب)") == "23bis-b"
    assert normalize_article("((23))") == "23"
    assert normalize_article("[٥]") == "5"
    assert build_statute_id("41", "2008", "(٢٣ مكرر (أ))") == "S:41/2008:23bis-a"


def test_digit_scripts_collapse_to_same_id():
    a = StatuteCitation(law_number="١٢", year="٢٠١٠", article="٢٣")
    b = StatuteCitation(law_number="12", year="2010", article="23")
    assert a.id == b.id == "S:12/2010:23"


def test_model_never_trusts_input_id():
    s = StatuteCitation(id="S:999/1:1", law_number="12", year="2010", article="23")
    assert s.id == "S:12/2010:23"


def test_article_extras():
    assert normalize_article("مادة (٧)") == "7"
    assert normalize_article("garbage") is None


def test_corpus_rejects_duplicates_and_empty():
    c = {"statute": [
        {"law_number": "1", "year": "2000", "article": "1", "content": "x"},
        {"law_number": "١", "year": "٢٠٠٠", "article": "١", "content": "y"},
    ]}
    with pytest.raises(ValueError, match="duplicate"):
        Corpus.model_validate(c)
    with pytest.raises(ValueError, match="empty content"):
        Corpus.model_validate({"cassation": [{"appeal_number": "1", "year": "2000"}]})
    with pytest.raises(ValueError, match="no ID"):
        Corpus.model_validate({"cassation": [{"appeal_number": "1", "content": "x"}]})
