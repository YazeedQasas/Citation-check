"""Export the shared structure as JSON Schema files (for docs, editors, and LLM response_format)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from citation_check.schema import CitationSet  # noqa: E402

out = Path("src/citation_check/schema/citation_set.schema.json")
schema = CitationSet.model_json_schema()
schema["title"] = "CitationSet (extracted.json / corpus.json)"
out.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("wrote", out)
