"""Load a draft judgment (.txt or .docx) into a :class:`Draft`.

PDF is intentionally not supported: Arabic PDF text extraction often returns
visually-ordered / reversed text, which would silently corrupt citations.
Convert the PDF to .docx or .txt first.
"""
from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from .text import normalize_with_offsets

log = logging.getLogger(__name__)

SUPPORTED = (".txt", ".docx")
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DraftLoadError(ValueError):
    """The draft could not be read as text."""


@dataclass
class Draft:
    path: Path | None
    raw: str                      # text exactly as read from the file
    text: str                     # normalised text: this is what goes to the LLM
    offsets: list[int] = field(repr=False)  # offsets[i] = index in raw of text[i]

    def raw_span(self, start: int, end: int) -> tuple[int, int]:
        """Map a ``text[start:end]`` span back to ``raw[a:b]``."""
        if not (0 <= start < end <= len(self.text)):
            raise IndexError(f"span {start}:{end} outside text of length {len(self.text)}")
        return self.offsets[start], self.offsets[end - 1] + 1

    def raw_snippet(self, start: int, end: int) -> str:
        a, b = self.raw_span(start, end)
        return self.raw[a:b]

    def find(self, needle: str, start: int = 0) -> tuple[int, int] | None:
        """Locate ``needle`` in the normalised text; returns ``(start, end)`` or None."""
        i = self.text.find(needle, start)
        return None if i < 0 else (i, i + len(needle))


def from_text(raw: str, path: Path | None = None) -> Draft:
    text, offsets = normalize_with_offsets(raw)
    return Draft(path=path, raw=raw, text=text, offsets=offsets)


def _decode(data: bytes, path: Path) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        log.warning("%s is not UTF-8; falling back to Windows-1256 (Arabic)", path.name)
        try:
            return data.decode("cp1256")
        except UnicodeDecodeError as e:
            raise DraftLoadError(f"{path.name}: cannot decode as UTF-8 or Windows-1256") from e


def _docx_text(path: Path) -> str:
    """Extract paragraph text from word/document.xml (body, tables, text boxes), one paragraph per line."""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise DraftLoadError(f"{path.name}: not a valid .docx file") from e
    root = ET.fromstring(xml)
    paragraphs = []
    for p in root.iter(f"{_W}p"):
        parts = []
        for el in p.iter():
            if el.tag == f"{_W}t":
                parts.append(el.text or "")
            elif el.tag == f"{_W}tab":
                parts.append("\t")
            elif el.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def load_draft(path: str | Path) -> Draft:
    path = Path(path)
    if not path.exists():
        raise DraftLoadError(f"file not found: {path}")
    ext = path.suffix.lower()
    if ext == ".txt":
        raw = _decode(path.read_bytes(), path)
    elif ext == ".docx":
        raw = _docx_text(path)
    elif ext == ".pdf":
        raise DraftLoadError(f"{path.name}: PDF is not supported (Arabic PDF text is unreliable). Convert to .docx or .txt.")
    else:
        raise DraftLoadError(f"{path.name}: unsupported file type {ext!r}; use {', '.join(SUPPORTED)}")
    draft = from_text(raw, path)
    if not re.search(r"\w", draft.text):
        raise DraftLoadError(f"{path.name}: no text found")
    return draft


def load_drafts(directory: str | Path) -> list[Draft]:
    """Load every supported file in a directory, sorted by name."""
    files = sorted(p for p in Path(directory).iterdir() if p.suffix.lower() in SUPPORTED)
    return [load_draft(p) for p in files]
