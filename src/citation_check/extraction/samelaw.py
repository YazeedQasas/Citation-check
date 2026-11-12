"""Resolve 'the same law' references in code.

Works on statute entries in DOCUMENT order. An entry whose quote says "القانون ذاته" / "the same law"
takes law_number, year and law_name from the nearest earlier statute entry that names its law
explicitly (no such wording, has both law_number and year). This overrides whatever the LLM
returned, because the model resolves such references unreliably and chunking hides earlier
context from it.
"""
from __future__ import annotations

from citation_check.schema import StatuteCitation

from .patterns import SAME_LAW


def is_same_law_ref(quote: str | None) -> bool:
    return bool(quote and SAME_LAW.search(quote))


def resolve_same_law(entries: list[tuple[int, StatuteCitation]]) -> tuple[list[StatuteCitation], list[str]]:
    """``entries``: (position in draft, entry). Returns (entries in the same order, warnings)."""
    out: list[StatuteCitation] = []
    warnings: list[str] = []
    last: StatuteCitation | None = None
    for _, e in sorted(entries, key=lambda t: t[0]):
        if is_same_law_ref(e.citation_text):
            if last is None:
                if e.law_number or e.year:
                    pass  # no earlier law to take from: keep what the model said
                else:
                    warnings.append(f"'same law' reference with no earlier law named: {e.citation_text!r}")
            else:
                changes = {k: getattr(last, k) for k in ("law_number", "year", "law_name")}
                if (e.law_number, e.year) != (last.law_number, last.year):
                    if e.law_number or e.year:
                        warnings.append(
                            f"'same law' reference resolved to {last.law_number}/{last.year} "
                            f"(model said {e.law_number}/{e.year}): {e.citation_text!r}"
                        )
                    data = e.model_dump(exclude={"id"})
                    data.update(changes)
                    e = StatuteCitation.model_validate(data)
        elif e.law_number and e.year:
            last = e
        out.append(e)
    return out, warnings
