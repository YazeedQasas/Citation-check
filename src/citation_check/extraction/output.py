"""Output stage: write the extraction result as extracted.json (the shared CitationSet shape)."""
from __future__ import annotations

import json
from pathlib import Path

from citation_check.schema import CitationSet
from citation_check.schema.validate import validate_citation_data

from .pipeline import ExtractionResult


def to_json_dict(result: ExtractionResult) -> dict:
    """Plain dict with exactly two top-level sections: ``statute`` and ``cassation``."""
    d = result.citations.model_dump(exclude_none=True)
    # re-validate the serialised form so a file we write is always one we can read back
    validate_citation_data(d, kind="extracted")
    return {"statute": d.get("statute", []), "cassation": d.get("cassation", [])}


def write_extracted_json(result: ExtractionResult, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_json_dict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_extracted_json(path: str | Path) -> CitationSet:
    from citation_check.schema.validate import load_citation_file
    return load_citation_file(path, kind="extracted")
