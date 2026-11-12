"""Build data/corpus/corpus.json from raw source files.

Each source file is JSON: ``{"statute": [...], "cassation": [...]}`` with raw records
(any digit script, messy article strings). IDs are produced by the shared normaliser,
so the corpus matches the extraction output by construction.

Usage:  python -m citation_check.corpus.build [--sources DIR] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from citation_check import config
from citation_check.schema import Corpus
from citation_check.schema.validate import validate_citation_data

log = logging.getLogger(__name__)

DEFAULT_SOURCES = config.ROOT / "data" / "corpus" / "source"


def load_sources(sources_dir: Path) -> dict:
    merged: dict[str, list] = {"statute": [], "cassation": []}
    files = sorted(sources_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no source *.json files in {sources_dir}")
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        unknown = set(data) - set(merged)
        if unknown:
            raise ValueError(f"{f.name}: unknown top-level keys {sorted(unknown)}")
        for kind in merged:
            merged[kind].extend(data.get(kind, []))
        log.info("read %s", f.name)
    return merged


def build(sources_dir: Path = DEFAULT_SOURCES, out: Path = config.CORPUS_PATH) -> Corpus:
    corpus = validate_citation_data(load_sources(sources_dir), kind="corpus")  # normalises + validates
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(corpus.model_dump(exclude_none=True), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    log.info("wrote %s: %d statute, %d cassation", out, len(corpus.statute), len(corpus.cassation))
    return corpus


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    ap.add_argument("--out", type=Path, default=config.CORPUS_PATH)
    args = ap.parse_args(argv)
    config.setup_logging()
    try:
        build(args.sources, args.out)
    except (ValueError, FileNotFoundError) as e:
        print(f"corpus build failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
