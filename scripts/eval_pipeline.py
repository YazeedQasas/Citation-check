"""End-to-end evaluation: draft -> findings, compared with gold statuses.

Usage: python scripts/eval_pipeline.py [--drafts DIR] [--gold FILE] [--out FILE] [--label NAME]
Prints the confusion matrix (expected vs actual status) and every disagreement.
"""
import argparse
import json
from pathlib import Path

from citation_check import config
from citation_check.evaluation.pipeline import evaluate_pipeline

ap = argparse.ArgumentParser()
ap.add_argument("--drafts", default=str(config.DRAFTS_DIR))
ap.add_argument("--gold")
ap.add_argument("--corpus")
ap.add_argument("--label", default="sample_drafts")
ap.add_argument("--out", default=str(config.ROOT / "reports" / "pipeline_eval.json"))
args = ap.parse_args()

ev = evaluate_pipeline(args.label, drafts_dir=Path(args.drafts), gold_path=Path(args.gold) if args.gold else None,
                       corpus_path=Path(args.corpus) if args.corpus else None)
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(ev.summary(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

s = ev.summary()
print(f"\n{s['label']}: {s['correct']}/{s['citations']} statuses correct  (accuracy {s['accuracy']:.3f}, {s['drafts']} drafts, {s['seconds']}s extraction)\n")
print(ev.render_matrix())
print("\nper status:")
for k, v in s["per_status"].items():
    print(f"  {k:12s} support {v['support']:3d}  precision {v['precision']}  recall {v['recall']}")
for k, v in s["by_kind"].items():
    print(f"  kind={k:10s} {v['correct']}/{v['total']}")
for k, v in s["by_lang"].items():
    print(f"  lang={k:10s} {v['correct']}/{v['total']}")
print("\nerrors:", s["errors"] or "none")
print("extras (findings not in gold):", s["extras"] or "none")
print("needs manual review:", s["needs_review"] or "none")
print("\nwrote", out)
