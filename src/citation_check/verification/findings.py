"""Findings: the output of the verification layer."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .status import Status


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["statute", "cassation"]
    id: str | None                           # canonical ID (None for an incomplete citation)
    status: Status
    citation_text: str | None = None         # the citation as written in the draft
    claim: str = ""                          # what the draft says the provision/decision provides
    reason: str = ""                         # why this status
    matched_corpus_id: str | None = None     # set when the citation exists in the corpus
    corpus_content: str | None = None        # the corpus text it was compared with
    closest_corpus_id: str | None = None     # near miss, for NOT_FOUND
    span: list[int] | None = None            # [start, end) of the citation in the ORIGINAL draft
    origin: str | None = None                # 'llm' | 'regex'
    needs_review: bool = False               # True if the check itself failed and a human must look


class FindingsReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    extraction_complete: bool = True         # False: the LLM could not process part of the draft

    def recount(self) -> None:
        c = Counter(f.status.value for f in self.findings)
        self.counts = {s.value: c.get(s.value, 0) for s in Status}


_ORDER = [Status.NOT_FOUND, Status.CONTRADICTS, Status.AMBIGUOUS, Status.SUPPORTED]  # most worrying first


def render_summary(report: FindingsReport, max_text: int = 70) -> str:
    lines = [f"Citation check: {report.draft or 'draft'}"]
    lines.append("  " + "   ".join(f"{s.value}: {report.counts.get(s.value, 0)}" for s in Status)
                 + f"   (total {len(report.findings)})")
    if not report.extraction_complete:
        lines.append("  WARNING: part of the draft could not be processed by the LLM; the list may be incomplete.")
    for status in _ORDER:
        group = [f for f in report.findings if f.status == status]
        if not group:
            continue
        lines.append(f"\n{status.value} ({len(group)})")
        for f in group:
            quote = (f.citation_text or "").replace("\n", " ")
            quote = quote if len(quote) <= max_text else quote[: max_text - 1] + "…"
            lines.append(f"  [{f.kind}] {f.id or '(no ID)'}  {quote}")
            if f.reason:
                lines.append(f"      {f.reason}")
            if f.needs_review:
                lines.append("      -> needs manual review")
    return "\n".join(lines)


def write_findings_json(report: FindingsReport, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path
