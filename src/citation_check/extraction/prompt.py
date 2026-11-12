"""Extraction prompt: system prompt + few-shot examples + response schema, all versioned.

Files live in ``prompts/`` and are named ``<PROMPT_VERSION>.*``. To change the prompt, copy
the files to a new version (e.g. ``extraction_v2.*``), edit, and bump PROMPT_VERSION, so
evaluation results can always be tied to the exact prompt that produced them.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PROMPT_VERSION = "extraction_v2"
PROMPT_DIR = Path(__file__).parent / "prompts"

STATUTE_FIELDS = ["law_number", "year", "article", "law_name", "clause", "content", "citation_text"]
CASSATION_FIELDS = ["appeal_number", "year", "chamber", "date", "content", "citation_text"]


def _entry_schema(fields: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {f: {"type": ["string", "null"]} for f in fields},
        "required": fields,
        "additionalProperties": False,
    }


def response_schema() -> dict:
    """JSON Schema the model must follow. Subset of the shared structure: no ``id`` / ``source``
    (IDs are computed by code, never by the model)."""
    return {
        "type": "object",
        "properties": {
            "statute": {"type": "array", "items": _entry_schema(STATUTE_FIELDS)},
            "cassation": {"type": "array", "items": _entry_schema(CASSATION_FIELDS)},
        },
        "required": ["statute", "cassation"],
        "additionalProperties": False,
    }


def response_format() -> dict:
    """The ``response_format`` argument for an OpenAI-compatible chat completion (LM Studio)."""
    return {
        "type": "json_schema",
        "json_schema": {"name": "citations", "strict": True, "schema": response_schema()},
    }


@lru_cache(maxsize=None)
def system_prompt(version: str = PROMPT_VERSION) -> str:
    return (PROMPT_DIR / f"{version}.system.md").read_text(encoding="utf-8").strip()


@lru_cache(maxsize=None)
def examples(version: str = PROMPT_VERSION) -> list[dict]:
    data = json.loads((PROMPT_DIR / f"{version}.examples.json").read_text(encoding="utf-8"))
    return [{"input": e["input"], "output": e["output"]} for e in data]


def build_messages(draft_text: str, version: str = PROMPT_VERSION) -> list[dict]:
    """Chat messages: system prompt, few-shot (user/assistant pairs), then the real passage."""
    msgs = [{"role": "system", "content": system_prompt(version)}]
    for ex in examples(version):
        msgs.append({"role": "user", "content": ex["input"]})
        msgs.append({"role": "assistant", "content": json.dumps(ex["output"], ensure_ascii=False)})
    msgs.append({"role": "user", "content": draft_text})
    return msgs
