"""Grounding: check LLM output against the draft text, in code.

1. The quote (``citation_text``) must exist in the draft (compared on a folded view that ignores
   digit script, diacritics, alef/yaa variants, brackets and spacing). Entries whose quote cannot be
   found are not grounded and are dropped by the pipeline.
2. The numbers the LLM returned are cross-checked against what the quote itself states. When the quote
   states a value and the LLM disagrees (e.g. a garbled year), the value from the quote wins.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

from citation_check.schema import CassationCitation, StatuteCitation
from citation_check.schema.ids import normalize_article, normalize_digits, normalize_number

from .patterns import find_cassation_candidates, find_statute_candidates

_FOLD_DROP = re.compile(r"[ً-ٰٟۖ-ۭـ()\[\]{}\"'«»“”]")


class FoldedText:
    """Normalised view of a string with a map back to indices in the original string."""

    def __init__(self, text: str):
        out: list[str] = []
        idx: list[int] = []
        for i, ch in enumerate(text):
            if _FOLD_DROP.match(ch):
                continue
            ch = normalize_digits(ch)
            if ch in "أإآٱ":
                ch = "ا"
            elif ch == "ى":
                ch = "ي"
            if ch.isspace():
                if not out or out[-1] == " ":
                    continue
                ch = " "
            out.append(ch.lower())
            idx.append(i)
        self.text = "".join(out)
        self.index = idx

    @staticmethod
    def fold(s: str) -> str:
        return FoldedText(s).text.strip()

    def find(self, needle: str, start_orig: int = 0) -> tuple[int, int] | None:
        """Find ``needle`` (folded) at or after original index ``start_orig``; returns (start, end) in the original."""
        n = self.fold(needle)
        if not n:
            return None
        first = bisect.bisect_left(self.index, start_orig)
        pos = self.text.find(n, first)
        if pos < 0:
            return None
        return self.index[pos], self.index[pos + len(n) - 1] + 1


@dataclass
class Grounding:
    span: tuple[int, int] | None          # span of the quote in draft.text, or None if not found
    repairs: list[str] = field(default_factory=list)


def locate_quote(folded: FoldedText, quote: str | None, search_from: int, used: set[tuple[int, int]]) -> tuple[int, int] | None:
    """Find the quote, preferring the first unused occurrence at/after ``search_from``, then anywhere."""
    if not quote or not quote.strip():
        return None
    first_any: tuple[int, int] | None = None
    for start in (search_from, 0):
        pos = start
        while True:
            hit = folded.find(quote, pos)
            if hit is None:
                break
            if hit not in used:
                return hit
            first_any = first_any or hit      # all occurrences used: entries may legitimately share a quote
            pos = hit[0] + 1
        if start == 0:
            break
    return first_any


def _same(a, b, norm) -> bool:
    return norm(a) == norm(b)


def repair_from_quote(entry, quote_text: str):
    """Return ``(entry, repairs)`` where numeric fields contradicting the quote are replaced by the quote's values."""
    repairs: list[str] = []
    changes: dict[str, str] = {}
    if isinstance(entry, StatuteCitation):
        cands = find_statute_candidates(quote_text)
        if not cands:
            return entry, repairs
        match = [c for c in cands if normalize_article(c.fields["article"]) == entry.article]
        cand = match[0] if match else (cands[0] if len(cands) == 1 else None)
        if cand is None:
            return entry, repairs
        if not match:
            changes["article"] = cand.fields["article"]
        for f in ("law_number", "year"):
            v = cand.fields[f]
            if v is not None and not _same(entry.__dict__[f], v, normalize_number):
                changes[f] = v
    else:
        cands = find_cassation_candidates(quote_text)
        if len(cands) != 1:
            return entry, repairs
        for f in ("appeal_number", "year"):
            v = cands[0].fields[f]
            if v is not None and not _same(entry.__dict__[f], v, normalize_number):
                changes[f] = v
    if not changes:
        return entry, repairs
    for f, v in changes.items():
        repairs.append(f"{f}: {entry.__dict__[f]!r} -> {v!r} (from quote)")
    data = entry.model_dump(exclude={"id"})
    data.update(changes)
    return type(entry).model_validate(data), repairs
