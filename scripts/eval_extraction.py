"""Evaluate the extraction layer on the gold-labelled sample drafts.

Usage: python scripts/eval_extraction.py [--no-llm-runs] [--out reports/extraction_eval.json]
Runs three configurations so each part's contribution is visible:
  full        LLM + grounding + same-law + regex safety net   (what ships)
  llm_only    LLM + grounding + same-law, no regex net
  regex_only  no LLM
"""
import argparse
import json
import sys
from pathlib import Path

from citation_check import config
from citation_check.evaluation.extraction import evaluate_extraction

ap = argparse.ArgumentParser()
ap.add_argument("--no-llm-runs", action="store_true", help="only the regex-only configuration (no LM Studio)")
ap.add_argument("--drafts", default=str(config.DRAFTS_DIR), help="folder with drafts and gold.json")
ap.add_argument("--out", default=str(config.ROOT / "reports" / "extraction_eval.json"))
args = ap.parse_args()

runs = [evaluate_extraction("regex_only", use_llm=False, drafts_dir=args.drafts)]
if not args.no_llm_runs:
    runs.insert(0, evaluate_extraction("full", drafts_dir=args.drafts))
    runs.insert(1, evaluate_extraction("llm_only", regex_net=False, drafts_dir=args.drafts))

out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps([r.summary() for r in runs], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for r in runs:
    s = r.summary()
    o = s["overall"]
    print(f"\n== {s['label']}: precision {o['precision']:.3f}  recall {o['recall']:.3f}  (tp {o['tp']} fp {o['fp']} fn {o['fn']})  {s['seconds']}s")
    for k, v in s["by_kind"].items():
        print(f"   {k:10s} P {v['precision']:.3f} R {v['recall']:.3f}")
    for k, v in s["by_lang"].items():
        print(f"   lang={k:3s}   P {v['precision']:.3f} R {v['recall']:.3f}")
    print("   misses:", s["misses"] or "none")
    print("   false positives:", s["false_positives"] or "none")
    if s["incomplete_drafts"]:
        print("   INCOMPLETE:", s["incomplete_drafts"])
print("\nwrote", out)
sys.exit(0)
