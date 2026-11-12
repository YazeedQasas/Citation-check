"""Shared structure for the Corpus JSON and the Extraction JSON.

Both files have the same top level::

    {"statute": [StatuteCitation, ...], "cassation": [CassationCitation, ...]}

``content`` means:
  * in the corpus: what the law / the cassation principle actually says
  * in the extraction: what the draft judgment CLAIMS it says
The verification layer compares the two.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .ids import (
    build_cassation_id,
    build_statute_id,
    normalize_article,
    normalize_number,
    normalize_year,
)

Kind = Literal["statute", "cassation"]


def _none_to_empty(v):
    return "" if v is None else v


class StatuteCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    _content_none = field_validator("content", mode="before")(_none_to_empty)  # LLM may return null

    id: str | None = None                 # computed from the fields below; never trusted from input
    law_number: str | None = None
    year: str | None = None
    article: str | None = None            # '23', '23bis', '23bis-a'
    law_name: str | None = None
    clause: str | None = None             # فقرة / بند, metadata only (not in the ID)
    content: str = ""                     # see module docstring
    citation_text: str | None = None      # exact wording in the draft (extraction only)
    span: list[int] | None = None         # [start, end) of citation_text in the ORIGINAL draft (extraction only)
    origin: str | None = None             # 'llm' | 'regex' (extraction only)
    source: str | None = None             # provenance (corpus only)

    @model_validator(mode="after")
    def _canonicalise(self) -> "StatuteCitation":
        self.law_number = normalize_number(self.law_number)
        self.year = normalize_year(self.year)
        self.article = normalize_article(self.article)
        self.id = build_statute_id(self.law_number, self.year, self.article)
        return self


class CassationCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    _content_none = field_validator("content", mode="before")(_none_to_empty)  # LLM may return null

    id: str | None = None
    appeal_number: str | None = None
    year: str | None = None               # judicial year (السنة القضائية)
    chamber: str | None = None            # مدني / جزائي / تجاري ..., metadata only
    date: str | None = None               # decision date, metadata only
    content: str = ""                     # the principle (corpus) or the claim made in the draft
    citation_text: str | None = None
    span: list[int] | None = None
    origin: str | None = None
    source: str | None = None             # provenance (corpus only)

    @model_validator(mode="after")
    def _canonicalise(self) -> "CassationCitation":
        self.appeal_number = normalize_number(self.appeal_number)
        self.year = normalize_year(self.year)
        self.id = build_cassation_id(self.appeal_number, self.year)
        return self


class CitationSet(BaseModel):
    """The shared top-level shape. Used for extracted.json and corpus.json."""

    model_config = ConfigDict(extra="forbid")

    statute: list[StatuteCitation] = Field(default_factory=list)
    cassation: list[CassationCitation] = Field(default_factory=list)


class Corpus(CitationSet):
    """A corpus additionally requires every entry to have a unique ID and some content."""

    @model_validator(mode="after")
    def _check(self) -> "Corpus":
        for kind, items in (("statute", self.statute), ("cassation", self.cassation)):
            seen: set[str] = set()
            for it in items:
                if not it.id:
                    raise ValueError(f"corpus {kind} entry has no ID (missing number/year/article): {it!r}")
                if it.id in seen:
                    raise ValueError(f"duplicate corpus {kind} ID: {it.id}")
                if not it.content.strip():
                    raise ValueError(f"corpus {kind} entry {it.id} has empty content")
                seen.add(it.id)
        return self
