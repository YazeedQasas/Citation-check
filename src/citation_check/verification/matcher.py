"""The 'Exists?' step: match extracted citations to the corpus by canonical ID. Pure code, no LLM.

A citation exists when its (kind, ID) is in the corpus. When it does not, we add a hint so a human
can see why, e.g. the law exists but not that article, or an ID that differs from a corpus ID by one digit.
"""
from __future__ import annotations

from dataclasses import dataclass

from citation_check.schema import CassationCitation, CitationSet, StatuteCitation

Entry = StatuteCitation | CassationCitation


def kind_of(entry: Entry) -> str:
    return "statute" if isinstance(entry, StatuteCitation) else "cassation"


@dataclass
class MatchResult:
    exists: bool
    entry: Entry | None = None            # the matched corpus entry
    closest_id: str | None = None         # near-miss corpus ID (only when not found)
    hint: str | None = None               # human-readable explanation when not found


def _edit_distance_le1(a: str, b: str) -> bool:
    """True if strings differ by at most one substitution/insertion/deletion."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    i = j = diff = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
        else:
            diff += 1
        j += 1
        if diff > 1:
            return False
    return True


def _missing_parts(entry: Entry) -> list[str]:
    if isinstance(entry, StatuteCitation):
        parts = {"law number": entry.law_number, "year": entry.year, "article": entry.article}
    else:
        parts = {"appeal number": entry.appeal_number, "year": entry.year}
    return [k for k, v in parts.items() if not v]


class CorpusIndex:
    def __init__(self, corpus: CitationSet):
        self.statute = {s.id: s for s in corpus.statute if s.id}
        self.cassation = {c.id: c for c in corpus.cassation if c.id}

    def _table(self, kind: str) -> dict:
        return self.statute if kind == "statute" else self.cassation

    def lookup(self, entry: Entry) -> MatchResult:
        kind = kind_of(entry)
        if not entry.id:
            missing = ", ".join(_missing_parts(entry)) or "identifying details"
            return MatchResult(False, hint=f"incomplete citation: {missing} not stated, so it cannot be matched to the corpus")
        hit = self._table(kind).get(entry.id)
        if hit is not None:
            return MatchResult(True, entry=hit)
        closest, hint = self._near_miss(entry)
        return MatchResult(False, closest_id=closest, hint=hint or "no corpus entry with this ID")

    # -------------------------------------------------------------------------------- near misses
    def _near_miss(self, e: Entry) -> tuple[str | None, str | None]:
        if isinstance(e, StatuteCitation):
            same_law = [s for s in self.statute.values() if (s.law_number, s.year) == (e.law_number, e.year)]
            if same_law:
                arts = ", ".join(sorted((s.article or "" for s in same_law), key=lambda a: (len(a), a)))
                return same_law[0].id, f"law {e.law_number}/{e.year} is in the corpus but article {e.article} is not (corpus has: {arts})"
            for s in self.statute.values():
                if s.article == e.article and (
                    (s.law_number == e.law_number and _edit_distance_le1(s.year or "", e.year or ""))
                    or (s.year == e.year and _edit_distance_le1(s.law_number or "", e.law_number or ""))
                ):
                    return s.id, f"differs from corpus ID {s.id} by one digit"
            same_number = [s for s in self.statute.values() if s.law_number == e.law_number]
            if same_number:
                years = ", ".join(sorted({s.year or "" for s in same_number}))
                return same_number[0].id, f"law number {e.law_number} exists in the corpus only for year(s): {years}"
            return None, "law not found in the corpus"
        for c in self.cassation.values():
            same_n = c.appeal_number == e.appeal_number
            same_y = c.year == e.year
            if (same_n and _edit_distance_le1(c.year or "", e.year or "")) or \
               (same_y and _edit_distance_le1(c.appeal_number or "", e.appeal_number or "")):
                return c.id, f"differs from corpus ID {c.id} by one digit"
        return None, "no cassation decision with this number and year in the corpus"
