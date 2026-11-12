"""Local HTTP API used by the web interface (web/). A thin layer over the existing pipeline:
every stage is its own endpoint so the UI can show, re-run and edit the output of each step.

Run:  python -m citation_check serve      (needs: pip install -e .[api])
"""
from __future__ import annotations

import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any, Literal

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .extraction import prompt as extraction_prompt
from .extraction.chunking import split_chunks
from .extraction.loader import DraftLoadError, from_text, load_draft
from .extraction.pipeline import extract_citations
from .extraction.text import _DROP
from .llm import LLMError, LMStudioClient
from .schema.validate import CitationFileError, load_citation_file, validate_citation_data
from .verification import claim as claim_mod
from .verification import verify
from .verification.matcher import CorpusIndex
from .verification.status import decide_status

log = logging.getLogger(__name__)
ROOT = config.ROOT
SAMPLE_SETS = [
    ("sample", "Sample drafts (data/drafts)", ROOT / "data" / "drafts"),
    ("heldout", "Held-out set (data/eval)", ROOT / "data" / "eval"),
    ("hard", "Hard stress set (data/eval_hard)", ROOT / "data" / "eval_hard"),
]

app = FastAPI(title="Citation Check", docs_url="/api/docs", openapi_url="/api/openapi.json")


# ------------------------------------------------------------------------------------------------ helpers
def make_client() -> LMStudioClient:
    """Factory (tests replace it with a fake)."""
    return LMStudioClient()


class _NoClient:
    """Stand-in for stages that never call the LLM."""
    calls = 0


def _corpus():
    try:
        return load_citation_file(config.CORPUS_PATH, kind="corpus")
    except CitationFileError as e:
        raise HTTPException(status_code=409, detail=f"{e}. Build it with: python -m citation_check corpus")


@app.exception_handler(LLMError)
async def _llm_error(_: Request, exc: LLMError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(DraftLoadError)
async def _draft_error(_: Request, exc: DraftLoadError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _dump(cs) -> dict:
    d = cs.model_dump(exclude_none=True)
    return {"statute": d.get("statute", []), "cassation": d.get("cassation", [])}


# -------------------------------------------------------------------------------------------------- info
@app.get("/api/health")
def health() -> dict:
    lm: dict[str, Any] = {"base_url": config.LMSTUDIO_BASE_URL, "model": config.LMSTUDIO_MODEL}
    try:
        with make_client() as c:
            c.ping()
        lm["ok"] = True
    except LLMError as e:
        lm.update(ok=False, error=str(e))
    corpus: dict[str, Any] = {"path": str(config.CORPUS_PATH)}
    try:
        cs = load_citation_file(config.CORPUS_PATH, kind="corpus")
        corpus.update(ok=True, statute=len(cs.statute), cassation=len(cs.cassation))
    except CitationFileError as e:
        corpus.update(ok=False, error=str(e))
    return {
        "lm_studio": lm, "corpus": corpus,
        "prompts": {"extraction": extraction_prompt.PROMPT_VERSION, "claim": claim_mod.PROMPT_VERSION},
        "chunk_max_chars": config.CHUNK_MAX_CHARS,
    }


@app.get("/api/corpus")
def corpus() -> dict:
    return _dump(_corpus())


@app.get("/api/samples")
def samples() -> list[dict]:
    out = []
    for key, label, folder in SAMPLE_SETS:
        if not folder.is_dir():
            continue
        gold_path = folder / "gold.json"
        gold = json.loads(gold_path.read_text(encoding="utf-8")) if gold_path.exists() else {}
        drafts = []
        for p in sorted(folder.glob("*.txt")):
            drafts.append({"name": p.name, "text": p.read_text(encoding="utf-8"), "gold": gold.get(p.name, [])})
        out.append({"key": key, "label": label, "drafts": drafts})
    return out


@app.post("/api/upload")
async def upload(request: Request, filename: str = Query(...)) -> dict:
    """Raw file bytes in the body (.txt or .docx) -> extracted text."""
    suffix = Path(filename).suffix.lower()
    data = await request.body()
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / f"upload{suffix}"
        p.write_bytes(data)
        draft = load_draft(p)
    return {"text": draft.raw, "filename": filename}


# ------------------------------------------------------------------------------------------------ stages
class TextIn(BaseModel):
    text: str


@app.post("/api/stage/clean")
def stage_clean(body: TextIn) -> dict:
    """Stage 1: text cleaning and chunk plan."""
    d = from_text(body.text)
    dropped = sum(1 for ch in body.text if ch in _DROP)
    chunks = split_chunks(d.text, config.CHUNK_MAX_CHARS)
    return {
        "cleaned": d.text,
        "raw_chars": len(body.text),
        "cleaned_chars": len(d.text),
        "removed": {"invisible_marks_and_tatweel": dropped,
                    "whitespace_and_other": max(0, len(body.text) - len(d.text) - dropped)},
        "chunks": [{"start": c.start, "end": c.end, "chars": len(c.text)} for c in chunks],
        "chunk_max_chars": config.CHUNK_MAX_CHARS,
    }


class ExtractIn(BaseModel):
    text: str
    use_llm: bool = True
    regex_net: bool = True


def _extraction_response(res) -> dict:
    return {
        "citations": _dump(res.citations), "warnings": res.warnings, "complete": res.complete,
        "n_chunks": res.n_chunks, "llm_calls": res.llm_calls, "seconds": res.seconds,
    }


@app.post("/api/stage/regex")
def stage_regex(body: TextIn) -> dict:
    """Stage 2: the code-only safety net (no LLM)."""
    res = extract_citations(from_text(body.text), _NoClient(), use_llm=False, regex_net=True)  # type: ignore[arg-type]
    return _extraction_response(res)


@app.post("/api/stage/extract")
def stage_extract(body: ExtractIn) -> dict:
    """Stage 3: extraction layer (LLM + grounding + same-law + regex net)."""
    if body.use_llm:
        with make_client() as client:
            client.ping()
            res = extract_citations(from_text(body.text), client, use_llm=True, regex_net=body.regex_net)
    else:
        res = extract_citations(from_text(body.text), _NoClient(), use_llm=False, regex_net=body.regex_net)  # type: ignore[arg-type]
    return _extraction_response(res)


class VerifyIn(BaseModel):
    extracted: dict
    draft_name: str | None = None


@app.post("/api/stage/verify")
def stage_verify(body: VerifyIn) -> dict:
    """Stage 4: verification layer. Takes the (possibly edited) extracted JSON."""
    try:
        extracted = validate_citation_data(body.extracted, kind="extracted")
    except CitationFileError as e:
        raise HTTPException(status_code=422, detail=str(e))
    corpus_set = _corpus()
    with make_client() as client:
        report = verify(extracted, corpus_set, client, draft_name=body.draft_name)
    return report.model_dump(mode="json", exclude_none=True)


# --------------------------------------------------------------------------------------- claim playground
class ClaimIn(BaseModel):
    kind: Literal["statute", "cassation"] = "statute"
    id: str | None = None                # a corpus ID ...
    authoritative: str | None = None     # ... or your own text to compare against
    claim: str


@app.post("/api/claim")
def claim_check(body: ClaimIn) -> dict:
    """Run only the claim comparison (Gemma) for one claim."""
    label = body.id or "custom text"
    authoritative = body.authoritative
    if body.id:
        idx = CorpusIndex(_corpus())
        entry = (idx.statute if body.kind == "statute" else idx.cassation).get(body.id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"no {body.kind} with ID {body.id} in the corpus")
        authoritative = entry.content
    if not (authoritative or "").strip():
        raise HTTPException(status_code=422, detail="give a corpus ID or an authoritative text")
    if not body.claim.strip():
        raise HTTPException(status_code=422, detail="the claim is empty")
    with make_client() as client:
        client.ping()
        j = claim_mod.judge_claim(client, body.kind, label, authoritative, body.claim)
    return {"status": decide_status(True, j.matches_claim, j.related).value, "matches_claim": j.matches_claim,
            "related": j.related, "reason": j.reason, "authoritative": authoritative}


# ---------------------------------------------------------------------------------------------- LLM log
@app.get("/api/llm-log")
def llm_log(limit: int = Query(30, ge=1, le=200)) -> list[dict]:
    """Most recent LLM calls (prompt, raw reply, timing, outcome), newest first."""
    path = config.LOG_DIR / "llm_calls.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ----------------------------------------------------------------------------------- static web build
_dist = ROOT / "web" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
