import json

from citation_check import config
from citation_check.corpus.build import build
from citation_check.schema import normalize_digits


def test_build_corpus_and_gold_consistency(tmp_path):
    corpus = build(out=tmp_path / "corpus.json")
    ids = {c.id for c in corpus.statute} | {c.id for c in corpus.cassation}
    assert len(corpus.statute) == 8 and len(corpus.cassation) == 6

    gold = json.loads((config.DRAFTS_DIR / "gold.json").read_text(encoding="utf-8"))
    n = 0
    for name, items in gold.items():
        if name.startswith("_"):
            continue
        assert (config.DRAFTS_DIR / name).exists(), name
        for it in items:
            n += 1
            in_corpus = it["id"] in ids
            assert in_corpus == (it["expected_status"] != "NOT_FOUND"), it
    assert n == 22


def test_drafts_are_arabic_with_mixed_digit_scripts():
    text = "".join(p.read_text(encoding="utf-8") for p in config.DRAFTS_DIR.glob("draft_*.txt"))
    assert any("٠" <= ch <= "٩" for ch in text)   # Arabic-Indic
    assert any("۰" <= ch <= "۹" for ch in text)   # Persian
    assert any(ch.isascii() and ch.isdigit() for ch in text)  # Western
    assert normalize_digits("۱٥") == "15"
