"""Light text normalisation for draft judgments, with an offset map back to the original.

Goal: remove noise that confuses the LLM or the chunker, WITHOUT changing the
wording of any citation. So we do NOT touch:
  * digits (the ID normaliser handles every digit script later),
  * letters (alef/yaa/taa-marbuta variants stay as written),
  * diacritics (rare in judgments; keeping them keeps quotes faithful).

What we do change:
  * Unicode compatibility forms (NFKC): Arabic presentation forms, ligatures, fullwidth chars, NBSP
  * drop tatweel (ـ), zero-width and bidi control characters, soft hyphen, BOM
  * unify line endings to \\n, collapse runs of spaces/tabs, trim spaces around newlines,
    allow at most one blank line between paragraphs, strip leading/trailing whitespace

Every character of the normalised text keeps the index of the original character it came from.
"""
from __future__ import annotations

import unicodedata

_DROP = {
    "ـ",                                   # tatweel
    "​", "‌", "‍", "⁠",     # zero-width space / non-joiner / joiner / word joiner
    "‎", "‏", "؜",               # LRM, RLM, Arabic letter mark
    "‪", "‫", "‬", "‭", "‮",  # bidi embeddings/overrides
    "⁦", "⁧", "⁨", "⁩",     # bidi isolates
    "­", "﻿",                         # soft hyphen, BOM
}
_SPACES = {" ", "\t", "\x0b", "\x0c", " ", " ", "　"} | {chr(c) for c in range(0x2000, 0x200B)}


def normalize_with_offsets(raw: str) -> tuple[str, list[int]]:
    """Return ``(text, offsets)`` where ``offsets[i]`` is the index in ``raw`` of ``text[i]``."""
    out: list[str] = []
    idx: list[int] = []

    def emit(ch: str, i: int) -> None:
        if ch == "\n":
            while out and out[-1] == " ":          # no trailing spaces on a line
                out.pop(); idx.pop()
            if not out or out[-2:] == ["\n", "\n"]:  # no leading newline, max one blank line
                return
        elif ch == " ":
            if not out or out[-1] in (" ", "\n"):    # no leading/doubled spaces
                return
        out.append(ch)
        idx.append(i)

    n = len(raw)
    i = 0
    while i < n:
        ch = raw[i]
        if ch == "\r":
            emit("\n", i)
            if i + 1 < n and raw[i + 1] == "\n":
                i += 1
        elif ch == "\n":
            emit("\n", i)
        elif ch in _SPACES:
            emit(" ", i)
        elif ch in _DROP:
            pass
        else:
            for c in unicodedata.normalize("NFKC", ch):
                if c in _DROP:
                    continue
                emit(" " if c in _SPACES else c, i)
        i += 1

    while out and out[-1] in (" ", "\n"):            # strip trailing whitespace
        out.pop(); idx.pop()
    return "".join(out), idx
