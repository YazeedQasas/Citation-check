"""Regex patterns for explicit citations (Arabic + English).

Used in two places, both as a SAFETY NET around the LLM, never as the main extractor:
  * cross-checking/repairing the numbers the LLM returned against its own quote (grounding)
  * finding explicit citations the LLM missed (recall check)

Only fully explicit citations are matched (digits for numbers). Citations whose numbers are
written in words are left to the LLM, except article numbers, which are handled via words_to_int.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from citation_check.schema.ids import normalize_digits, normalize_text, words_to_int

D = r"[0-9٠-٩۰-۹]"
_DIAC = r"[ً-ٟ]*"

SAME_LAW = re.compile(
    r"(?:القانون\s+ذاته|القانون\s+نفسه|ذات\s+القانون|نفس\s+القانون|the\s+same\s+law|said\s+law|the\s+aforementioned\s+law)",
    re.IGNORECASE,
)

_LAW_AR = re.compile(
    rf"(?:ال)?(?:قانون|نظام){_DIAC}\b(?P<name>[^.\n؛(]{{0,60}}?)\s*رقم\s*\(?\s*(?P<n>{D}+)\s*\)?\s*لسنة\s*\(?\s*(?P<y>{D}+)\s*\)?"
)
_LAW_EN = re.compile(
    rf"(?P<name>(?:[A-Z][A-Za-z]*\s+){{0,5}})Law\s*No\.?\s*\(?\s*(?P<n>{D}+)\s*\)?\s*(?:of|/)\s*\(?\s*(?P<y>{D}+)\s*\)?"
)
_ARTKW = re.compile(
    r"(?:للمادتين|بالمادتين|المادتين|مادتين|للمادة|بالمادة|المادة|مادة|للمواد|المواد|Articles?\b|Art\.)",
    re.IGNORECASE,
)
_ART_TOKEN = re.compile(
    rf"(?P<num>{D}+)(?P<bis>\s*(?:مكرر{_DIAC}[اًٌٍ]?|bis\b)(?:\s*\(?\s*(?P<letter>[أ-ي])\s*\)?)?)?",
    re.IGNORECASE,
)
_CLAUSE = re.compile(rf"(?:فقرة|فقرتين|بند|البند|الفقرة|paragraph|clause|para\.?)\s*\(?\s*{D}+\s*\)?", re.IGNORECASE)

_CASS_REF = re.compile(
    rf"(?:(?P<kw>القرار|قرارها|قرار|الطعن|نقض\s+\S+|Cassation\s+Appeal|Decision|Appeal)\s*)?"
    rf"(?:رقم|No\.?)\s*\(?\s*(?P<n>{D}+)\s*\)?\s*(?:لسنة|/|of)\s*\(?\s*(?P<y>{D}+)\s*\)?",
    re.IGNORECASE,
)
_CASS_CONTEXT = re.compile(r"النقض|نقض|Cassation|التمييز|تمييز", re.IGNORECASE)
_OTHER_COURT = re.compile(
    r"الاستئناف|البداية|الدستورية|العليا|الإدارية|الابتدائية|Appeal\s+Court|Court\s+of\s+Appeal|First\s+Instance|Constitutional|Supreme\s+Administrative",
    re.IGNORECASE,
)
_SENT_START = re.compile(r"[.؟!?\n]")


@dataclass
class Candidate:
    kind: str                       # 'statute' | 'cassation'
    fields: dict[str, str | None]
    start: int
    end: int
    quote: str
    same_law: bool = False          # statute refers to 'the same law'
    law_name: str | None = None
    extra: dict = field(default_factory=dict)


def _norm_article(num: str, bis: str | None, letter: str | None) -> str:
    out = str(int(normalize_digits(num)))
    if bis:
        out += " مكرر"
        if letter:
            out += f" ({letter})"
    return out


def _sentence_floor(text: str, pos: int, limit: int) -> int:
    """Start index of the sentence containing ``pos``, but not further back than ``limit``."""
    lo = max(0, limit)
    best = lo
    for m in _SENT_START.finditer(text, lo, pos):
        best = m.end()
    return best


def _law_refs(text: str) -> list[tuple[int, int, dict]]:
    refs: list[tuple[int, int, dict]] = []
    for rx in (_LAW_AR, _LAW_EN):
        for m in rx.finditer(text):
            name = (m.group("name") or "").strip() or None
            refs.append((m.start(), m.end(), {"law_number": m.group("n"), "year": m.group("y"), "law_name": name, "same": False}))
    for m in SAME_LAW.finditer(text):
        refs.append((m.start(), m.end(), {"law_number": None, "year": None, "law_name": None, "same": True}))
    refs.sort(key=lambda r: r[0])
    # drop refs nested inside an earlier one
    out: list[tuple[int, int, dict]] = []
    for r in refs:
        if out and r[0] < out[-1][1]:
            continue
        out.append(r)
    return out


def find_statute_candidates(text: str) -> list[Candidate]:
    cands: list[Candidate] = []
    last_law: dict | None = None
    prev_end = 0
    for s, e, law in _law_refs(text):
        floor = _sentence_floor(text, s, max(prev_end, s - 160))
        window = text[floor:s]
        kws = list(_ARTKW.finditer(window))
        if kws:
            kw = kws[-1]
            seg_start = floor + kw.start()
            segment = text[floor + kw.end():s]
            segment_clean = _CLAUSE.sub(" ", segment)
            tokens = list(_ART_TOKEN.finditer(segment_clean))
            articles: list[str] = []
            if tokens:
                articles = [_norm_article(t.group("num"), t.group("bis"), t.group("letter")) for t in tokens]
            else:  # article number written in words: 'الثالثة والعشرين مكرراً'
                words = re.split(r"\s+(?:من|of)\s*$|\bمن\b", segment_clean.strip())[0]
                bis = re.search(r"مكرر", words)
                n = words_to_int(re.sub(r"مكرر\S*", " ", normalize_text(words)))
                if n:
                    articles = [str(n) + (" مكرر" if bis else "")]
            if articles:
                use = last_law if (law["same"] and last_law) else law
                quote = text[seg_start:e].rstrip()          # the law regex may swallow trailing spaces
                for a in articles:
                    cands.append(Candidate(
                        kind="statute",
                        fields={"law_number": use["law_number"], "year": use["year"], "article": a},
                        start=seg_start, end=seg_start + len(quote), quote=quote,
                        same_law=law["same"], law_name=use.get("law_name"),
                    ))
        if not law["same"]:
            last_law = law
        prev_end = e
    return cands


def find_cassation_candidates(text: str) -> list[Candidate]:
    law_spans = [(s, e) for s, e, _ in _law_refs(text)]
    cands: list[Candidate] = []
    for m in _CASS_REF.finditer(text):
        if any(s <= m.start() < e or s < m.end() <= e for s, e in law_spans):
            continue
        floor = _sentence_floor(text, m.start(), m.start() - 220)
        before = text[floor:m.start()]
        core_start = m.start()
        # the 30 characters right before the number phrase must not name another court
        near = text[max(floor, core_start - 30):core_start + 12]
        if _OTHER_COURT.search(near) and not _CASS_CONTEXT.search(near):
            continue
        # cassation context: before the number, in the phrase itself, or (only when the phrase starts with a decision
        # keyword such as 'القرار') right after it, as in 'وفي القرار رقم (2210) لسنة 2019 قررت محكمة النقض'
        after = text[m.end():m.end() + 40]
        after = _SENT_START.split(after, 1)[0]
        if not (_CASS_CONTEXT.search(before) or _CASS_CONTEXT.search(m.group(0)) or
                (m.group("kw") and _CASS_CONTEXT.search(after))):
            continue
        quote = m.group(0).rstrip()
        cands.append(Candidate(
            kind="cassation",
            fields={"appeal_number": m.group("n"), "year": m.group("y")},
            start=m.start(), end=m.start() + len(quote), quote=quote,
        ))
    return cands


def sentence_around(text: str, start: int, end: int) -> str:
    a = _sentence_floor(text, start, max(0, start - 400))
    m = _SENT_START.search(text, end)
    b = m.start() + (0 if text[m.start()] == "\n" else 1) if m else len(text)
    return text[a:min(b, a + 600)].strip()
