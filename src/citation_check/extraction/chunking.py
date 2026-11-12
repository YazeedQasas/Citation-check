"""Split a long draft into chunks that fit one extraction call.

Chunks are contiguous slices ``draft.text[start:end]`` so every position maps straight back to the
draft. Splits happen at paragraph boundaries, then sentence boundaries, and only as a last resort
at a hard character limit. Consecutive chunks overlap by one paragraph/sentence so a citation that
sits on a boundary is seen whole by at least one chunk.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?<=[.؟!؛?])\s+")


@dataclass(frozen=True)
class Chunk:
    start: int
    end: int
    text: str


def _units(text: str, max_chars: int) -> list[tuple[int, int]]:
    """Smallest pieces we are willing to keep together: paragraphs, else sentences, else hard slices."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for para in text.split("\n"):
        start, end = pos, pos + len(para)
        pos = end + 1
        if not para.strip():
            continue
        if end - start <= max_chars:
            spans.append((start, end))
            continue
        s = start
        for m in _SENTENCE_END.finditer(para):
            e = start + m.start()
            if e > s:
                spans.append((s, e))
            s = start + m.end()
        if s < end:
            spans.append((s, end))
    # hard-split any unit still too long (e.g. one giant sentence)
    out: list[tuple[int, int]] = []
    for s, e in spans:
        while e - s > max_chars:
            out.append((s, s + max_chars))
            s += max_chars
        out.append((s, e))
    return out


def split_chunks(text: str, max_chars: int, overlap_chars: int | None = None) -> list[Chunk]:
    """Greedy packing of units into chunks of at most ``max_chars`` characters."""
    if max_chars < 200:
        raise ValueError("max_chars too small")
    if len(text) <= max_chars:
        return [Chunk(0, len(text), text)] if text.strip() else []
    if overlap_chars is None:
        overlap_chars = max_chars // 4
    units = _units(text, max_chars)
    chunks: list[Chunk] = []
    i = 0
    while i < len(units):
        j = i
        while j + 1 < len(units) and units[j + 1][1] - units[i][0] <= max_chars:
            j += 1
        start, end = units[i][0], units[j][1]
        chunks.append(Chunk(start, end, text[start:end]))
        if j + 1 >= len(units):
            break
        # next chunk starts at the last unit of this one if it is small enough to overlap, else after it
        k = j
        if units[k][1] - units[k][0] <= overlap_chars and k > i:
            i = k
        else:
            i = j + 1
    return chunks


def halve(chunk: Chunk) -> list[Chunk]:
    """Split a chunk in two at a paragraph/sentence boundary near the middle (used after truncation)."""
    t = chunk.text
    mid = len(t) // 2
    cut = -1
    for m in re.finditer(r"\n|(?<=[.؟!؛?])\s", t):
        if abs(m.start() - mid) < abs(cut - mid) or cut < 0:
            cut = m.start()
    if cut <= 0 or cut >= len(t) - 1:
        cut = mid
    a, b = t[:cut], t[cut:]
    return [c for c in (Chunk(chunk.start, chunk.start + len(a), a), Chunk(chunk.start + cut, chunk.end, b)) if c.text.strip()]
