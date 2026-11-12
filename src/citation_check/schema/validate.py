"""One validator used by both layers (corpus builder, extraction output, verification input)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from .models import CitationSet, Corpus


class CitationFileError(ValueError):
    """Raised with a readable message when a citations JSON file is invalid."""


def validate_citation_data(data: dict, *, kind: Literal["corpus", "extracted"]) -> CitationSet:
    """Validate and canonicalise a parsed JSON object.

    ``corpus``    -> strict: every entry needs an ID and content, IDs unique.
    ``extracted`` -> lenient: entries may lack an ID (incomplete citation); the
                     verification layer reports those instead of crashing.
    """
    model = Corpus if kind == "corpus" else CitationSet
    try:
        return model.model_validate(data)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:5])
        raise CitationFileError(f"invalid {kind} JSON: {problems}") from e
    except ValueError as e:  # raised by Corpus checks
        raise CitationFileError(f"invalid {kind} JSON: {e}") from e


def load_citation_file(path: str | Path, *, kind: Literal["corpus", "extracted"]) -> CitationSet:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise CitationFileError(f"file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise CitationFileError(f"{path.name} is not valid JSON: {e}") from e
    return validate_citation_data(data, kind=kind)
