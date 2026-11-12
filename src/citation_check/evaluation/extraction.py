"""Evaluate the extraction layer against gold labels (data/drafts/gold.json).

A citation counts as found when its canonical ID matches a gold ID of the same kind in the same draft.
Entries the pipeline produced without an ID can never match, so they count as false positives.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from citation_check import config
from citation_check.extraction.loader import load_draft
from citation_check.extraction.pipeline import extract_citations
from citation_check.llm import LMStudioClient


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 1.0


@dataclass
class ExtractionEval:
    label: str
    overall: Counts = field(default_factory=Counts)
    by_kind: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    by_lang: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    misses: list[str] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)
    seconds: float = 0.0
    incomplete_drafts: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        def row(c: Counts) -> dict:
            return {"tp": c.tp, "fp": c.fp, "fn": c.fn, "precision": round(c.precision, 3), "recall": round(c.recall, 3)}
        return {
            "label": self.label,
            "overall": row(self.overall),
            "by_kind": {k: row(v) for k, v in sorted(self.by_kind.items())},
            "by_lang": {k: row(v) for k, v in sorted(self.by_lang.items())},
            "misses": self.misses,
            "false_positives": self.false_positives,
            "incomplete_drafts": self.incomplete_drafts,
            "seconds": round(self.seconds, 1),
        }


def load_gold(path: Path | None = None) -> dict[str, list[dict]]:
    g = json.loads((path or config.DRAFTS_DIR / "gold.json").read_text(encoding="utf-8"))
    return {k: v for k, v in g.items() if not k.startswith("_")}


def evaluate_extraction(label: str, *, use_llm: bool = True, regex_net: bool = True, prompt_version: str | None = None,
                        gold: dict[str, list[dict]] | None = None, client: LMStudioClient | None = None,
                        drafts_dir: Path | None = None) -> ExtractionEval:
    drafts_dir = Path(drafts_dir or config.DRAFTS_DIR)
    gold = gold or load_gold(drafts_dir / "gold.json")
    ev = ExtractionEval(label)
    own = client is None
    client = client or LMStudioClient()
    try:
        for name, items in gold.items():
            draft = load_draft(drafts_dir / name)
            kwargs = {"use_llm": use_llm, "regex_net": regex_net}
            if prompt_version:
                kwargs["prompt_version"] = prompt_version
            res = extract_citations(draft, client, **kwargs)
            ev.seconds += res.seconds
            if not res.complete:
                ev.incomplete_drafts.append(name)
            got = {("statute", e.id) for e in res.citations.statute if e.id} | \
                  {("cassation", e.id) for e in res.citations.cassation if e.id}
            no_id = [e for e in [*res.citations.statute, *res.citations.cassation] if not e.id]
            want = {(i["kind"], i["id"]): i.get("lang", "ar") for i in items}
            for key, lang in want.items():
                hit = key in got
                for bucket in (ev.overall, ev.by_kind[key[0]], ev.by_lang[lang]):
                    if hit:
                        bucket.tp += 1
                    else:
                        bucket.fn += 1
                if not hit:
                    ev.misses.append(f"{name}: {key[1]}")
            for key in got - set(want):
                for bucket in (ev.overall, ev.by_kind[key[0]]):
                    bucket.fp += 1
                ev.false_positives.append(f"{name}: {key[1]}")
            for e in no_id:
                kind = "statute" if hasattr(e, "law_number") else "cassation"
                for bucket in (ev.overall, ev.by_kind[kind]):
                    bucket.fp += 1
                ev.false_positives.append(f"{name}: (no ID) {e.citation_text!r}")
    finally:
        if own:
            client.close()
    return ev
