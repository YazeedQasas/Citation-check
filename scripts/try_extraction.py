"""Quick dev check of the extraction prompt against LM Studio (NOT the formal evaluation).

Usage: python scripts/try_extraction.py [draft_01.txt ...]
Prints the model's raw JSON and compares computed IDs with data/drafts/gold.json.
The proper client (retries, logging, chunking) and the formal evaluation are separate tasks.
"""
import json
import sys
import time

import httpx

from citation_check import config
from citation_check.extraction import prompt
from citation_check.extraction.loader import load_draft
from citation_check.schema import CitationSet

gold = json.loads((config.DRAFTS_DIR / "gold.json").read_text(encoding="utf-8"))
names = sys.argv[1:] or sorted(k for k in gold if not k.startswith("_"))

for name in names:
    draft = load_draft(config.DRAFTS_DIR / name)
    body = {
        "model": config.LMSTUDIO_MODEL,
        "messages": prompt.build_messages(draft.text),
        "temperature": config.LLM_TEMPERATURE,
        "max_tokens": 2500,
        "response_format": prompt.response_format(),
    }
    t0 = time.time()
    r = httpx.post(f"{config.LMSTUDIO_BASE_URL}/chat/completions", json=body, timeout=config.LLM_TIMEOUT_S * 3)
    r.raise_for_status()
    data = r.json()
    raw = data["choices"][0]["message"]["content"]
    dt = time.time() - t0
    cs = CitationSet.model_validate(json.loads(raw))
    got = {c.id for c in [*cs.statute, *cs.cassation] if c.id}
    no_id = [c for c in [*cs.statute, *cs.cassation] if not c.id]
    want = {g["id"] for g in gold[name]}
    print(f"\n=== {name}  ({dt:.0f}s, {data.get('usage', {})})")
    print("missing :", sorted(want - got))
    print("extra   :", sorted(got - want))
    print("no id   :", [(c.citation_text) for c in no_id])
    if "--raw" in names or len(sys.argv) == 2:
        print(raw)
