"""The whole pipeline in one call: draft -> extraction layer -> verification layer -> findings."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import config
from .extraction.loader import load_draft
from .extraction.pipeline import ExtractionResult, extract_citations
from .llm import LMStudioClient
from .schema.validate import CitationFileError, load_citation_file
from .verification import FindingsReport, verify


@dataclass
class CheckOutcome:
    extraction: ExtractionResult
    report: FindingsReport


def check_draft(
    draft_path: str | Path,
    corpus_path: str | Path | None = None,
    *,
    client: LMStudioClient,
    use_llm_extraction: bool = True,
) -> CheckOutcome:
    """Raises DraftLoadError / CitationFileError for bad inputs."""
    corpus_path = Path(corpus_path or config.CORPUS_PATH)
    if not corpus_path.exists():
        raise CitationFileError(f"corpus not found: {corpus_path} (build it with: python -m citation_check corpus)")
    corpus = load_citation_file(corpus_path, kind="corpus")
    draft = load_draft(draft_path)
    extraction = extract_citations(draft, client, use_llm=use_llm_extraction)
    report = verify(
        extraction.citations, corpus, client,
        draft_name=Path(draft_path).name,
        extraction_complete=extraction.complete,
        extraction_warnings=extraction.warnings,
    )
    return CheckOutcome(extraction, report)
