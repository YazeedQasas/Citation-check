"""Verification layer: extracted.json + corpus.json -> findings."""
from __future__ import annotations

import logging

from citation_check.llm import LLMError, LMStudioClient
from citation_check.schema import CitationSet, StatuteCitation

from . import claim as claim_mod
from .findings import Finding, FindingsReport
from .matcher import CorpusIndex, Entry, kind_of
from .status import Status, decide_status

log = logging.getLogger(__name__)


def citation_label(e: Entry) -> str:
    if isinstance(e, StatuteCitation):
        return f"article {e.article} of law {e.law_number}/{e.year}"
    return f"Court of Cassation decision {e.appeal_number}/{e.year}"


def verify(
    extracted: CitationSet,
    corpus: CitationSet,
    client: LMStudioClient | None,
    *,
    draft_name: str | None = None,
    extraction_complete: bool = True,
    extraction_warnings: list[str] | None = None,
) -> FindingsReport:
    index = CorpusIndex(corpus)
    entries: list[Entry] = [*extracted.statute, *extracted.cassation]
    entries.sort(key=lambda e: (e.span[0] if e.span else 10**12))   # document order; stable for equal/missing spans
    report = FindingsReport(draft=draft_name, extraction_complete=extraction_complete,
                            warnings=list(extraction_warnings or []))
    cache: dict[tuple[str, str, str], claim_mod.ClaimJudgement] = {}

    for e in entries:
        kind = kind_of(e)
        base = dict(kind=kind, id=e.id, citation_text=e.citation_text, claim=e.content, span=e.span, origin=e.origin)
        m = index.lookup(e)

        if not m.exists:   # 'Exists?' -> no: NOT_FOUND, and the LLM is not called
            status = decide_status(False)
            report.findings.append(Finding(**base, status=status, reason=m.hint or "", closest_corpus_id=m.closest_id))
            continue

        corpus_entry = m.entry
        found = dict(matched_corpus_id=corpus_entry.id, corpus_content=corpus_entry.content)
        if not (e.content or "").strip():
            report.findings.append(Finding(**base, **found, status=Status.AMBIGUOUS, needs_review=True,
                                           reason="the draft's claim about this citation could not be extracted, so it cannot be compared"))
            continue
        key = (kind, corpus_entry.id, e.content)
        try:
            if key not in cache:
                if client is None:
                    raise LLMError("no LLM client available")
                cache[key] = claim_mod.judge_claim(client, kind, citation_label(e), corpus_entry.content, e.content)
            j = cache[key]
        except LLMError as err:
            log.warning("claim check failed for %s: %s", e.id, err)
            report.findings.append(Finding(**base, **found, status=Status.AMBIGUOUS, needs_review=True,
                                           reason=f"claim check failed ({err}); needs manual review"))
            continue
        report.findings.append(Finding(**base, **found, status=decide_status(True, j.matches_claim, j.related), reason=j.reason))

    _apply_cited_together(report, client, cache)
    report.recount()
    return report


def _apply_cited_together(report: FindingsReport, client: LMStudioClient | None, cache: dict) -> None:
    """Articles cited together ('المادتين (23) و(23 مكرر)') share ONE claim, usually describing them jointly or
    only one of them, so judging it against each article alone would wrongly contradict the others.

    For each such group (same quote, at least two articles that exist in the corpus) that is not already all
    SUPPORTED:
      1. judge the claim against the articles READ TOGETHER; if it matches, every existing article is SUPPORTED;
      2. otherwise, if the claim matches at least one article, the other existing articles are SUPPORTED too
         (the reason says why);
      3. otherwise each keeps its own status.
    NOT_FOUND members are never changed.
    """
    # cluster statute findings whose quotes overlap (the same sentence cited by the LLM and by the regex net
    # can differ by a character or two, so identical spans are not required)
    clusters: list[list[Finding]] = []
    bound = -1
    for f in sorted((f for f in report.findings if f.kind == "statute" and f.span), key=lambda f: f.span[0]):
        if clusters and f.span[0] < bound:
            clusters[-1].append(f)
            bound = max(bound, f.span[1])
        else:
            clusters.append([f])
            bound = f.span[1]
    for members in clusters:
        # one citation expression = one claim; two occurrences of the same article inside one cluster are not 'together'
        if len({f.id for f in members}) < 2:
            continue
        existing = [f for f in members if f.matched_corpus_id]
        if len(existing) < 2 or all(f.status is Status.SUPPORTED for f in existing):
            continue

        if client is not None and existing[0].claim.strip():
            uniq = list({f.matched_corpus_id: f for f in existing}.values())
            joined = "\n".join(f"[{f.matched_corpus_id}] {f.corpus_content}" for f in uniq)
            label = "articles " + ", ".join(f.matched_corpus_id for f in uniq) + " (cited together)"
            key = ("statute-group", joined, existing[0].claim)
            try:
                if key not in cache:
                    cache[key] = claim_mod.judge_claim(client, "statute", label, joined, existing[0].claim)
                j = cache[key]
            except LLMError as err:
                log.warning("combined claim check failed: %s", err)
                j = None
            if j is not None and j.matches_claim:
                for f in existing:
                    if f.status is not Status.SUPPORTED:
                        f.reason = f"the claim matches these articles read together ({j.reason}). (On its own: {f.reason})"
                        f.status = Status.SUPPORTED
                continue

        winners = [f for f in existing if f.status is Status.SUPPORTED]
        if winners:
            for f in existing:
                if f.status in (Status.CONTRADICTS, Status.AMBIGUOUS):
                    f.reason = f"cited together with {winners[0].id}, which the shared claim matches. (On its own: {f.reason})"
                    f.status = Status.SUPPORTED
