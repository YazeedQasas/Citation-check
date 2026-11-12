"""Extraction layer: draft in -> CitationSet (extracted.json) out.

Steps
  1. split the draft into chunks that fit one LLM call (halving a chunk again if the reply is truncated)
  2. LLM extraction per chunk (schema-constrained JSON, validated against the shared models)
  3. grounding: locate every quote in the draft (drop entries whose quote is not there),
     repair numbers that contradict the quote
  4. resolve 'the same law' references in code, in document order
  5. safety net: regex finds explicit citations the LLM missed and adds them (origin='regex')
  6. merge duplicates (same ID, same place or same claim) and sort in document order
IDs are always computed by the shared normaliser (the models do it on construction).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from citation_check import config
from citation_check.llm import LLMError, LMStudioClient, TruncatedOutputError
from citation_check.schema import CassationCitation, CitationSet, StatuteCitation

from . import prompt as prompt_mod
from .chunking import Chunk, halve, split_chunks
from .grounding import FoldedText, locate_quote, repair_from_quote
from .loader import Draft
from .patterns import (
    Candidate, find_cassation_candidates, find_statute_candidates, sentence_around,
)
from .samelaw import resolve_same_law

log = logging.getLogger(__name__)
MAX_HALVINGS = 3
SIMILAR = 0.8


@dataclass
class ExtractionResult:
    citations: CitationSet
    warnings: list[str] = field(default_factory=list)
    complete: bool = True            # False if some chunk could not be processed by the LLM
    n_chunks: int = 0
    llm_calls: int = 0
    seconds: float = 0.0


@dataclass
class _Item:
    entry: StatuteCitation | CassationCitation
    start: int                       # position in draft.text
    end: int
    origin: str


def _extract_chunk(chunk: Chunk, client: LMStudioClient, version: str, warnings: list[str], depth: int = 0):
    """Return [(entry, chunk_start)] for one chunk, halving it if the model's reply is truncated."""
    try:
        cs = client.complete_json(
            prompt_mod.build_messages(chunk.text, version),
            prompt_mod.response_format(),
            CitationSet.model_validate,
            purpose="extract",
            meta={"prompt_version": version, "chunk": [chunk.start, chunk.end]},
        )
    except TruncatedOutputError:
        if depth >= MAX_HALVINGS or len(chunk.text) < 400:
            warnings.append(f"chunk {chunk.start}-{chunk.end}: output truncated and chunk cannot be split further")
            return None
        out = []
        for part in halve(chunk):
            r = _extract_chunk(part, client, version, warnings, depth + 1)
            if r is None:
                return None
            out += r
        return out
    return [(e, chunk.start) for e in [*cs.statute, *cs.cassation]]


def _overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 < b1 and b0 < a1


def _claim_core(entry) -> str:
    """The claim without the citation wording itself. Regex-found entries use the whole sentence as the claim, and
    the citation boilerplate is identical in every repetition, so it must not make different claims look alike."""
    content = entry.content or ""
    if entry.citation_text:
        content = content.replace(entry.citation_text, " ")
    return FoldedText.fold(content)


def _same_claim(a, b) -> bool:
    ca, cb = _claim_core(a), _claim_core(b)
    if ca == cb:
        return True
    return SequenceMatcher(None, ca, cb).ratio() >= SIMILAR


def _cand_to_entry(c: Candidate, draft_text: str) -> StatuteCitation | CassationCitation:
    content = sentence_around(draft_text, c.start, c.end)
    if c.kind == "statute":
        return StatuteCitation(**c.fields, law_name=c.law_name, content=content, citation_text=c.quote)
    return CassationCitation(**c.fields, content=content, citation_text=c.quote)


def extract_citations(
    draft: Draft,
    client: LMStudioClient,
    *,
    max_chars: int | None = None,
    prompt_version: str = prompt_mod.PROMPT_VERSION,
    use_llm: bool = True,
    regex_net: bool = True,
) -> ExtractionResult:
    t0 = time.time()
    warnings: list[str] = []
    text = draft.text
    chunks = split_chunks(text, max_chars or config.CHUNK_MAX_CHARS)
    folded = FoldedText(text)
    calls_before = client.calls
    complete = True

    # 1-2. LLM extraction ------------------------------------------------------------------
    raw: list[tuple[StatuteCitation | CassationCitation, int]] = []
    if use_llm:
        for ch in chunks:
            try:
                got = _extract_chunk(ch, client, prompt_version, warnings)
            except LLMError as e:
                warnings.append(f"chunk {ch.start}-{ch.end}: LLM failed ({e})")
                got = None
            if got is None:
                complete = False
            else:
                raw += got

    # 3. grounding --------------------------------------------------------------------------
    items: list[_Item] = []
    used: set[tuple[int, int]] = set()
    for entry, chunk_start in raw:
        span = locate_quote(folded, entry.citation_text, chunk_start, used)
        if span is None:
            warnings.append(f"dropped ungrounded entry (quote not found in draft): {entry.citation_text!r}")
            continue
        used.add(span)
        entry, repairs = repair_from_quote(entry, text[span[0]:span[1]])
        for r in repairs:
            warnings.append(f"repaired {r}: {entry.citation_text!r}")
        items.append(_Item(entry, span[0], span[1], "llm"))
    # entries sharing one quote (e.g. 'المادتين (56) و(56 مكرر)') are all kept: `used` only steers the search

    # 4. same-law resolution (statutes, document order) ---------------------------------------
    items.sort(key=lambda it: it.start)
    stat_idx = [i for i, it in enumerate(items) if isinstance(it.entry, StatuteCitation)]
    if stat_idx:
        resolved, w = resolve_same_law([(items[i].start, items[i].entry) for i in stat_idx])
        warnings += w
        for i, e in zip(stat_idx, resolved):
            items[i].entry = e

    # 5. regex safety net ---------------------------------------------------------------------
    if regex_net:
        for c in [*find_statute_candidates(text), *find_cassation_candidates(text)]:
            e = _cand_to_entry(c, text)
            if e.id is None:
                continue
            covered = any(
                type(it.entry) is type(e) and it.entry.id == e.id and _overlaps(it.start, it.end, c.start, c.end)
                for it in items
            )
            if not covered:
                warnings.append(f"regex safety net added {e.id}: {c.quote!r}")
                items.append(_Item(e, c.start, c.end, "regex"))

    # 6. merge duplicates + order ------------------------------------------------------------
    items.sort(key=lambda it: (it.start, it.end))
    merged: list[_Item] = []
    for it in items:
        dup = None
        for m in merged:
            if type(m.entry) is not type(it.entry):
                continue
            same_id = it.entry.id is not None and m.entry.id == it.entry.id
            same_quote = it.entry.id is None and m.entry.id is None and \
                FoldedText.fold(m.entry.citation_text or "") == FoldedText.fold(it.entry.citation_text or "")
            if same_id and (_overlaps(m.start, m.end, it.start, it.end) or _same_claim(m.entry, it.entry)):
                dup = m
            elif same_quote:
                dup = m
            if dup:
                break
        if dup is None:
            merged.append(it)
        else:  # keep the LLM entry (or the one with the fuller claim) and the earlier position
            better = it if (dup.origin == "regex" and it.origin == "llm") or \
                (dup.origin == it.origin and len(it.entry.content) > len(dup.entry.content)) else dup
            dup.entry = better.entry
            dup.origin = better.origin if better.origin == "llm" else dup.origin

    stat, cass = [], []
    for it in merged:
        data = it.entry.model_dump(exclude={"id"})
        data["span"] = list(draft.raw_span(it.start, it.end))
        data["origin"] = it.origin
        e = type(it.entry).model_validate(data)
        (stat if isinstance(e, StatuteCitation) else cass).append(e)

    for e in [*stat, *cass]:
        if e.id is None:
            warnings.append(f"incomplete citation (no ID): {e.citation_text!r}")

    return ExtractionResult(
        citations=CitationSet(statute=stat, cassation=cass),
        warnings=warnings,
        complete=complete,
        n_chunks=len(chunks),
        llm_calls=client.calls - calls_before,
        seconds=round(time.time() - t0, 1),
    )
