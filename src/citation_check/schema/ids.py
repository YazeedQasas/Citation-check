"""Canonical citation IDs and the normaliser that produces them.

Both the corpus builder and the extraction layer MUST build IDs through this
module, so the two JSONs match by construction.

ID shapes
---------
Statute   ``S:{law_number}/{year}:{article}``     e.g. ``S:12/2010:23``, ``S:12/2010:23bis``
Cassation ``C:{appeal_number}/{year}``            e.g. ``C:456/2015``

* Digits are always ASCII, without leading zeros (Arabic-Indic, Persian,
  fullwidth digits are all accepted on input).
* ``مكرر`` on an article becomes ``bis``; a following Arabic letter becomes a
  Latin one (``23 مكرر (أ)`` -> ``23bis-a``).
* Clause (فقرة), chamber and decision date are NOT part of the ID. They are
  stored as metadata. Reason: drafts often omit them, and an ID that needs
  them would turn a correct citation into a false NOT_FOUND.
* Numbers written in words are accepted for 1..99 (``الثالثة والعشرون`` -> 23,
  ``الخامسة عشرة`` -> 15), for articles and for other numbers.
* English forms work too: ``Article 23 bis`` -> ``23bis``, ``Law No. 12 of 2010``.
* A citation missing a required part has no ID (``None``).
"""
from __future__ import annotations

import re
import unicodedata

# Arabic-Indic (U+0660..0669), Eastern/Persian (U+06F0..06F9), fullwidth (U+FF10..FF19)
_DIGIT_MAP = {}
for _base in (0x0660, 0x06F0, 0xFF10):
    for _i in range(10):
        _DIGIT_MAP[_base + _i] = str(_i)

_DIACRITICS = re.compile(r"[ً-ٰٟۖ-ۭـ]")  # harakat, superscript alef, tatweel

_LETTER_MAP = {
    "أ": "a", "ا": "a", "إ": "a", "آ": "a",
    "ب": "b", "ج": "c", "د": "d", "هـ": "e", "ه": "e", "و": "f", "ز": "g",
}

_ARTICLE_RE = re.compile(
    r"""^\s*\(?\s*(?P<num>\d+)\s*\)?          # 23  or (23)
        (?:\s*(?P<bis>مكرر|bis)\s*)?          # مكرر
        (?:[\s\-]*\(?\s*(?P<letter>[^\W\d_])\s*\)?)? # (أ)   or '-a' (our own canonical form, so normalisation is idempotent)
        \s*$""",
    re.VERBOSE | re.IGNORECASE,
)


def normalize_digits(text: str) -> str:
    """Map any digit script to ASCII digits."""
    return str(text).translate(_DIGIT_MAP)


# ---------------------------------------------------------------- number words
# Ordinals (الثالثة والعشرون) and simple cardinals (ثلاثة) -> int, for 1..99.
# Keys are stored in a normalised spelling (see _norm_word) so alef/yaa/taa-marbuta
# variants and the definite article all collapse to one form.

def _norm_word(w: str) -> str:
    w = unicodedata.normalize("NFKC", w)
    w = _DIACRITICS.sub("", w)
    w = re.sub(r"[أإآٱ]", "ا", w).replace("ى", "ي").replace("ة", "ه")
    return w


_UNIT_WORDS = {
    1: ["اول", "اولى", "واحد", "واحده", "حادي", "حاديه", "احد", "احدى"],
    2: ["ثان", "ثاني", "ثانيه", "اثنان", "اثنين", "اثنتان", "اثنا", "اثنتا"],
    3: ["ثالث", "ثالثه", "ثلاثه", "ثلاث"],
    4: ["رابع", "رابعه", "اربعه", "اربع"],
    5: ["خامس", "خامسه", "خمسه", "خمس"],
    6: ["سادس", "سادسه", "سته", "ست"],
    7: ["سابع", "سابعه", "سبعه", "سبع"],
    8: ["ثامن", "ثامنه", "ثمانيه", "ثماني", "ثمان"],
    9: ["تاسع", "تاسعه", "تسعه", "تسع"],
    10: ["عاشر", "عاشره", "عشره"],
}
_TEN_WORDS = {
    20: ["عشرون", "عشرين"], 30: ["ثلاثون", "ثلاثين"], 40: ["اربعون", "اربعين"],
    50: ["خمسون", "خمسين"], 60: ["ستون", "ستين"], 70: ["سبعون", "سبعين"],
    80: ["ثمانون", "ثمانين"], 90: ["تسعون", "تسعين"],
}
_UNITS = {_norm_word(w): n for n, ws in _UNIT_WORDS.items() for w in ws}
_TENS = {_norm_word(w): n for n, ws in _TEN_WORDS.items() for w in ws}
_TEEN_MARK = {"عشر", "عشره"}


def words_to_int(text: str) -> int | None:
    """'الثالثة والعشرون' -> 23, 'الخامسة عشرة' -> 15, 'العاشرة' -> 10. None if not a number phrase."""
    s = _norm_word(normalize_text(str(text)))
    s = re.sub(r"[()\[\]،,.:]", " ", s)
    tokens = []
    for tok in s.split():
        if tok.startswith("و") and (tok[1:] in _UNITS or tok[1:] in _TENS or tok[1:].startswith("ال")):
            tok = tok[1:]                      # "والعشرون" -> "العشرون"
        if tok.startswith("ال") and len(tok) > 3:
            tok = tok[2:]                      # drop the definite article
        tokens.append(tok)
    if not tokens:
        return None
    total, i = 0, 0
    while i < len(tokens):
        t = tokens[i]
        if t in _TENS:
            total += _TENS[t]
        elif t in _UNITS:
            n = _UNITS[t]
            if i + 1 < len(tokens) and tokens[i + 1] in _TEEN_MARK and n < 10:
                total += 10 + n               # الخامسة عشرة -> 15
                i += 1
            else:
                total += n
        else:
            return None
        i += 1
    return total if 0 < total < 100 else None


def normalize_text(text: str) -> str:
    """Strip diacritics/tatweel, unify alef/yaa/taa-marbuta-free forms, collapse whitespace.

    Used for comparing free text and cleaning ID parts. Not for display.
    """
    t = unicodedata.normalize("NFKC", str(text))
    t = _DIACRITICS.sub("", t)
    t = re.sub(r"[أإآٱ]", "ا", t)
    t = t.replace("ى", "ي")
    return re.sub(r"\s+", " ", t).strip()


def normalize_number(value: object) -> str | None:
    """'٠١٢' -> '12', ' (456) ' -> '456', 'الخامسة عشرة' -> '15'. Returns None if no number."""
    if value is None:
        return None
    m = re.search(r"\d+", normalize_digits(str(value)))
    if m:
        return str(int(m.group(0)))
    n = words_to_int(str(value))
    return str(n) if n else None


def normalize_year(value: object) -> str | None:
    """Same as normalize_number; kept separate so year rules can evolve (e.g. 2-digit years)."""
    return normalize_number(value)


def normalize_article(value: object) -> str | None:
    """'٢٣' -> '23', '23 مكرر' -> '23bis', '(23) مكرراً (أ)' -> '23bis-a'."""
    if value is None:
        return None
    s = normalize_text(normalize_digits(str(value)))
    s = s.replace("مكررا", "مكرر").replace("مكررً", "مكرر")
    s = re.sub(r"[()\[\]]", " ", s)            # '(23 مكرر (أ))' -> '23 مكرر  أ '  (brackets, even nested, carry no meaning)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^\s*(?:المادة|مادة|م\.|article|art\.?)\s*", "", s, flags=re.IGNORECASE)
    if not re.search(r"\d", s):
        # number written in words: 'الثالثة والعشرون مكرراً' -> '23 مكرر'
        m = re.match(r"^(?P<w>.+?)\s*(?P<rest>مكرر.*|bis.*)?$", s, flags=re.IGNORECASE)
        n = words_to_int(m.group("w")) if m else None
        if n:
            s = f"{n} {m.group('rest') or ''}".strip()
    m = _ARTICLE_RE.match(s)
    if not m:
        n = normalize_number(s)  # fall back to the bare number
        return n
    out = str(int(m.group("num")))
    if m.group("bis"):
        out += "bis"
    letter = m.group("letter")
    if letter and not m.group("bis"):
        # a bare trailing letter without 'مكرر' is ambiguous; ignore it
        letter = None
    if letter:
        out += "-" + _LETTER_MAP.get(letter, letter.lower())
    return out


def build_statute_id(law_number: object, year: object, article: object) -> str | None:
    n, y, a = normalize_number(law_number), normalize_year(year), normalize_article(article)
    if not (n and y and a):
        return None
    return f"S:{n}/{y}:{a}"


def build_cassation_id(appeal_number: object, year: object) -> str | None:
    n, y = normalize_number(appeal_number), normalize_year(year)
    if not (n and y):
        return None
    return f"C:{n}/{y}"
