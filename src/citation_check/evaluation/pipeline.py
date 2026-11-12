"""End-to-end evaluation: final STATUS per citation versus gold labels.

For every gold citation (draft, kind, id) the actual status is the worst status among the findings with that ID
(NOT_FOUND > CONTRADICTS > AMBIGUOUS > SUPPORTED); no finding at all counts as MISSED (extraction failure).
Findings whose ID is not in the gold list are reported as extras (possible false positives).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from citation_check import config
from citation_check.check import check_draft
from citation_check.llm import LMStudioClient
from citation_check.verification.status import Status

STATUSES = ["SUPPORTED", "CONTRADICTS", "AMBIGUOUS", "NOT_FOUND", "MISSED"]
_SEVERITY = {"SUPPORTED": 0, "AMBIGUOUS": 1, "CONTRADICTS": 2, "NOT_FOUND": 3}


@dataclass
class PipelineEval:
    label: str
    matrix: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))   # expected -> Counter(actual)
    by_kind: dict[str, list[int]] = field(default_factory=lambda: defaultdict(lambda: [0, 0]))   # [correct, total]
    by_lang: dict[str, list[int]] = field(default_factory=lambda: defaultdict(lambda: [0, 0]))
    errors: list[str] = field(default_factory=list)
    extras: list[str] = field(default_factory=list)
    needs_review: list[str] = field(default_factory=list)
    seconds: float = 0.0
    n_drafts: int = 0

    @property
    def total(self) -> int:
        return sum(sum(c.values()) for c in self.matrix.values())

    @property
    def correct(self) -> int:
        return sum(self.matrix[s][s] for s in self.matrix)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 1.0

    def per_status(self) -> dict[str, dict]:
        out = {}
        for s in STATUSES[:4]:
            tp = self.matrix[s][s]
            fn = sum(self.matrix[s].values()) - tp
            fp = sum(self.matrix[e][s] for e in self.matrix if e != s)
            out[s] = {
                "support": tp + fn, "tp": tp, "fn": fn, "fp": fp,
                "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            }
        return out

    def summary(self) -> dict:
        return {
            "label": self.label, "drafts": self.n_drafts, "citations": self.total, "correct": self.correct,
            "accuracy": round(self.accuracy, 3),
            "confusion_matrix_expected_to_actual": {e: dict(self.matrix[e]) for e in STATUSES if e in self.matrix},
            "per_status": self.per_status(),
            "by_kind": {k: {"correct": v[0], "total": v[1], "accuracy": round(v[0] / v[1], 3)} for k, v in sorted(self.by_kind.items())},
            "by_lang": {k: {"correct": v[0], "total": v[1], "accuracy": round(v[0] / v[1], 3)} for k, v in sorted(self.by_lang.items())},
            "errors": self.errors, "extras": self.extras, "needs_review": self.needs_review,
            "seconds": round(self.seconds, 1),
        }

    def render_matrix(self) -> str:
        w = 12
        lines = ["expected \\ actual".ljust(18) + "".join(s.rjust(w) for s in STATUSES)]
        for e in STATUSES[:4]:
            if e in self.matrix:
                lines.append(e.ljust(18) + "".join(str(self.matrix[e][a]).rjust(w) for a in STATUSES))
        return "\n".join(lines)


def evaluate_pipeline(label: str, *, drafts_dir: Path | None = None, gold_path: Path | None = None,
                      corpus_path: Path | None = None, client: LMStudioClient | None = None,
                      use_llm_extraction: bool = True) -> PipelineEval:
    drafts_dir = Path(drafts_dir or config.DRAFTS_DIR)
    gold = json.loads(Path(gold_path or drafts_dir / "gold.json").read_text(encoding="utf-8"))
    gold = {k: v for k, v in gold.items() if not k.startswith("_")}
    ev = PipelineEval(label)
    own = client is None
    client = client or LMStudioClient()
    try:
        for name, items in gold.items():
            outcome = check_draft(drafts_dir / name, corpus_path, client=client, use_llm_extraction=use_llm_extraction)
            ev.n_drafts += 1
            ev.seconds += outcome.extraction.seconds
            actual: dict[tuple[str, str], str] = {}
            for f in outcome.report.findings:
                if f.needs_review:
                    ev.needs_review.append(f"{name}: {f.id}")
                if not f.id:
                    ev.extras.append(f"{name}: (no ID) {f.citation_text!r}")
                    continue
                k = (f.kind, f.id)
                if k not in actual or _SEVERITY[f.status.value] > _SEVERITY[actual[k]]:
                    actual[k] = f.status.value
            want_keys = set()
            for it in items:
                k = (it["kind"], it["id"])
                want_keys.add(k)
                exp = it["expected_status"]
                got = actual.get(k, "MISSED")
                ev.matrix[exp][got] += 1
                ok = got == exp
                for bucket in (ev.by_kind[it["kind"]], ev.by_lang[it.get("lang", "ar")]):
                    bucket[0] += ok
                    bucket[1] += 1
                if not ok:
                    ev.errors.append(f"{name} {it['id']}: expected {exp}, got {got}")
            for k in set(actual) - want_keys:
                ev.extras.append(f"{name}: {k[1]} -> {actual[k]}")
    finally:
        if own:
            client.close()
    return ev
