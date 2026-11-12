import zipfile

import pytest

from citation_check import config
from citation_check.extraction.loader import DraftLoadError, from_text, load_draft, load_drafts
from citation_check.extraction.text import normalize_with_offsets


def test_whitespace_and_line_endings():
    raw = "  سطر أول \t  \r\n\r\n\r\n\r\nسطر   ثان  \r\nثالث\r"
    text, _ = normalize_with_offsets(raw)
    assert text == "سطر أول\n\nسطر ثان\nثالث"


def test_removes_invisible_marks_and_tatweel():
    raw = "المــادة‏ (‎٢٣) من قانون﻿"
    text, _ = normalize_with_offsets(raw)
    assert text == "المادة (٢٣) من قانون"


def test_presentation_forms_are_normalised():
    text, _ = normalize_with_offsets("ﻻ")  # lam-alef ligature
    assert text == "لا"


def test_citation_wording_is_untouched():
    raw = "عملاً بأحكام المادة (٢٣ مكرر) من قانون رقم (۱۲) لسنة 2010 وأإآ ىي ة"
    text, _ = normalize_with_offsets(raw)
    assert text == raw  # digits, alef/yaa/taa variants and diacritics are not rewritten


def test_diacritics_are_kept():
    raw = "عَمَلاً بِأَحْكَامِ"
    assert normalize_with_offsets(raw)[0] == raw


def test_offsets_map_back_to_original():
    raw = "  المــادة   (٢٣) \r\n من‏ قانون  "
    d = from_text(raw)
    s, e = d.find("(٢٣)")
    assert d.raw_snippet(s, e) == "(٢٣)"
    s, e = d.find("المادة")
    assert d.raw_snippet(s, e) == "المــادة"       # tatweel is inside the raw span
    s, e = d.find("من")
    assert d.raw_snippet(s, e) == "من"
    assert all(a < b for a, b in zip(d.offsets, d.offsets[1:]))  # strictly increasing


def test_raw_span_bounds():
    d = from_text("abc")
    with pytest.raises(IndexError):
        d.raw_span(2, 9)


def test_sample_drafts_load_and_citations_trace_back():
    drafts = load_drafts(config.DRAFTS_DIR)
    assert len(drafts) == 6
    d = load_draft(config.DRAFTS_DIR / "draft_01.txt")
    s, e = d.find("المادة (9) من قانون رقم (15) لسنة 2015")
    assert d.raw_snippet(s, e) == "المادة (9) من قانون رقم (15) لسنة 2015"
    d5 = load_draft(config.DRAFTS_DIR / "draft_05.txt")
    assert "(۳۱)" in d5.text and "(۸)" in d5.text      # Persian digits preserved as written


def _make_docx(path, paragraphs):
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{p}</w:t></w:r></w:p>" for p in paragraphs
    )
    table = "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>خلية</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document {ns}><w:body>{body}{table}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


def test_docx(tmp_path):
    p = tmp_path / "d.docx"
    _make_docx(p, ["الفقرة الأولى", "الفقرة (٢) من المادة ٥"])
    d = load_draft(p)
    assert d.text == "الفقرة الأولى\nالفقرة (٢) من المادة ٥\nخلية"


def test_txt_encodings(tmp_path):
    s = "المادة (٥) من قانون رقم (٧) لسنة ٢٠٢٠"
    (tmp_path / "utf8.txt").write_bytes(s.encode("utf-8"))
    (tmp_path / "bom.txt").write_bytes(b"\xef\xbb\xbf" + s.encode("utf-8"))
    (tmp_path / "utf16.txt").write_bytes(s.encode("utf-16"))
    (tmp_path / "cp1256.txt").write_bytes("المادة (5) من قانون".encode("cp1256"))
    assert load_draft(tmp_path / "utf8.txt").text == s
    assert load_draft(tmp_path / "bom.txt").text == s
    assert load_draft(tmp_path / "utf16.txt").text == s
    assert load_draft(tmp_path / "cp1256.txt").text == "المادة (5) من قانون"


def test_errors(tmp_path):
    with pytest.raises(DraftLoadError, match="not found"):
        load_draft(tmp_path / "missing.txt")
    (tmp_path / "x.pdf").write_bytes(b"%PDF")
    with pytest.raises(DraftLoadError, match="PDF is not supported"):
        load_draft(tmp_path / "x.pdf")
    (tmp_path / "x.rtf").write_text("hi")
    with pytest.raises(DraftLoadError, match="unsupported"):
        load_draft(tmp_path / "x.rtf")
    (tmp_path / "empty.txt").write_text("  \n ‏ ", encoding="utf-8")
    with pytest.raises(DraftLoadError, match="no text"):
        load_draft(tmp_path / "empty.txt")
    (tmp_path / "bad.docx").write_bytes(b"not a zip")
    with pytest.raises(DraftLoadError, match="not a valid .docx"):
        load_draft(tmp_path / "bad.docx")
