"""Command line: ``python -m citation_check <command>`` (or ``citation-check <command>``).

  check    DRAFT [-o findings.json]         full pipeline: draft -> findings
  extract  DRAFT [-o extracted.json]        extraction layer only: draft -> extracted.json
  verify   EXTRACTED.json [-o findings]     verification layer only: extracted.json + corpus -> findings
  corpus   [--sources DIR] [--out FILE]     build corpus.json from source files

Exit codes: 0 ok | 2 bad input (missing/unreadable draft or corpus) | 3 finished but part of the draft
could not be processed by the LLM (results may be incomplete) | 4 LM Studio unreachable or model not loaded.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import config
from .check import check_draft
from .extraction.loader import DraftLoadError, load_draft
from .extraction.output import write_extracted_json
from .extraction.pipeline import extract_citations
from .llm import LLMError, LMStudioClient
from .schema.validate import CitationFileError, load_citation_file
from .verification import render_summary, verify, write_findings_json


EXIT_BAD_INPUT = 2
EXIT_INCOMPLETE = 3
EXIT_LLM_UNAVAILABLE = 4


def _client(need_llm: bool = True) -> LMStudioClient:
    """A client, after checking LM Studio is reachable and has the model (raises LLMError with a clear message)."""
    client = LMStudioClient()
    if need_llm:
        try:
            client.ping()
        except LLMError:
            client.close()
            raise
    return client


def _extract(args) -> int:
    try:
        draft = load_draft(args.draft)
    except DraftLoadError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_BAD_INPUT
    out = Path(args.output) if args.output else Path(args.draft).with_suffix(".extracted.json")
    try:
        client_cm = _client(need_llm=not args.no_llm)
    except LLMError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_LLM_UNAVAILABLE
    with client_cm as client:
        result = extract_citations(draft, client, use_llm=not args.no_llm)
    write_extracted_json(result, out)
    n_s, n_c = len(result.citations.statute), len(result.citations.cassation)
    print(f"{args.draft}: {n_s} statute + {n_c} cassation citations -> {out} "
          f"({result.n_chunks} chunk(s), {result.llm_calls} LLM call(s), {result.seconds}s)")
    for w in result.warnings:
        print(f"  warning: {w}", file=sys.stderr)
    if not result.complete:
        print("  WARNING: some parts of the draft could not be processed by the LLM; results may be incomplete.", file=sys.stderr)
        return EXIT_INCOMPLETE
    return 0


def _print_outcome(report, out: Path) -> int:
    print(render_summary(report))
    print(f"\nfindings written to {out}")
    for w in report.warnings:
        print(f"  warning: {w}", file=sys.stderr)
    return 0 if report.extraction_complete else EXIT_INCOMPLETE


def _check(args) -> int:
    out = Path(args.output) if args.output else Path(args.draft).with_suffix(".findings.json")
    try:
        # inputs first, so a bad file is reported as a bad file even when LM Studio is down
        load_draft(args.draft)
        load_citation_file(args.corpus or config.CORPUS_PATH, kind="corpus")
    except (DraftLoadError, CitationFileError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_BAD_INPUT
    try:
        client_cm = _client()
    except LLMError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_LLM_UNAVAILABLE
    try:
        with client_cm as client:
            outcome = check_draft(args.draft, args.corpus, client=client, use_llm_extraction=not args.no_llm_extraction)
    except (DraftLoadError, CitationFileError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_BAD_INPUT
    write_findings_json(outcome.report, out)
    if args.extracted:
        write_extracted_json(outcome.extraction, args.extracted)
    return _print_outcome(outcome.report, out)


def _verify(args) -> int:
    """Verification layer on its own: extracted.json + corpus.json -> findings.json."""
    out = Path(args.output) if args.output else Path(args.extracted).with_suffix(".findings.json")
    try:
        extracted = load_citation_file(args.extracted, kind="extracted")
        corpus = load_citation_file(args.corpus or config.CORPUS_PATH, kind="corpus")
    except CitationFileError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_BAD_INPUT
    try:
        client_cm = _client()
    except LLMError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_LLM_UNAVAILABLE
    with client_cm as client:
        report = verify(extracted, corpus, client, draft_name=Path(args.extracted).name)
    write_findings_json(report, out)
    return _print_outcome(report, out)


def _serve(args) -> int:
    try:
        import uvicorn
        from . import api
    except ImportError:
        print("error: the web interface needs extra packages. Run: python -m pip install -e '.[api]'", file=sys.stderr)
        return EXIT_BAD_INPUT
    if not (config.ROOT / "web" / "dist").is_dir():
        print("note: web/dist not found. For the interface, run 'cd web && npm install && npm run dev' (dev, port 5173) "
              "or 'npm run build' and restart this command.", file=sys.stderr)
    print(f"API on http://{args.host}:{args.port}   (interface: http://localhost:5173 in dev, or this address once built)")
    uvicorn.run(api.app, host=args.host, port=args.port, log_level="warning")
    return 0


def _corpus(args) -> int:
    from .corpus.build import main as build_main
    argv = []
    if args.sources:
        argv += ["--sources", args.sources]
    if args.out:
        argv += ["--out", args.out]
    return build_main(argv)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="citation-check", description="Verify citations in draft judgments.")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract", help="extract statute/cassation citations from a draft")
    p.add_argument("draft")
    p.add_argument("-o", "--output")
    p.add_argument("--no-llm", action="store_true", help="regex safety net only (no LM Studio needed)")
    p.set_defaults(func=_extract)

    p = sub.add_parser("check", help="full pipeline: draft -> findings (SUPPORTED / CONTRADICTS / AMBIGUOUS / NOT_FOUND)")
    p.add_argument("draft")
    p.add_argument("-o", "--output", help="findings JSON path (default: <draft>.findings.json)")
    p.add_argument("--corpus", help="corpus.json (default: data/corpus/corpus.json)")
    p.add_argument("--extracted", help="also save the extraction layer's extracted.json here")
    p.add_argument("--no-llm-extraction", action="store_true", help="use the regex safety net only for extraction")
    p.set_defaults(func=_check)

    p = sub.add_parser("verify", help="verification layer only: extracted.json + corpus.json -> findings")
    p.add_argument("extracted")
    p.add_argument("-o", "--output")
    p.add_argument("--corpus")
    p.set_defaults(func=_verify)

    p = sub.add_parser("serve", help="start the local API for the web interface (web/)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=_serve)

    p = sub.add_parser("corpus", help="build corpus.json from data/corpus/source")
    p.add_argument("--sources")
    p.add_argument("--out")
    p.set_defaults(func=_corpus)

    args = ap.parse_args(argv)
    config.setup_logging(logging.DEBUG if args.verbose else logging.WARNING)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
