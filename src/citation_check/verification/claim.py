"""The claim check: does the draft's claim match the corpus text?  (LLM, only for citations that exist.)

Answers the two flowchart questions in one structured call:
    matches_claim  -> 'Correct claim?'
    related        -> 'Is it related?'
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator

from citation_check.llm import LMStudioClient

PROMPT_VERSION = "claim_v1"
PROMPT_DIR = Path(__file__).parent / "prompts"


class ClaimJudgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    matches_claim: bool
    related: bool

    @model_validator(mode="after")
    def _consistent(self) -> "ClaimJudgement":
        if self.matches_claim and not self.related:   # rule 3 of the prompt: a match is always related
            self.related = True
        return self


def response_format() -> dict:
    schema = {
        "type": "object",
        # 'reason' first so the model states its analysis before committing to the booleans
        "properties": {
            "reason": {"type": "string"},
            "matches_claim": {"type": "boolean"},
            "related": {"type": "boolean"},
        },
        "required": ["reason", "matches_claim", "related"],
        "additionalProperties": False,
    }
    return {"type": "json_schema", "json_schema": {"name": "claim_judgement", "strict": True, "schema": schema}}


@lru_cache(maxsize=None)
def system_prompt(version: str = PROMPT_VERSION) -> str:
    return (PROMPT_DIR / f"{version}.system.md").read_text(encoding="utf-8").strip()


@lru_cache(maxsize=None)
def examples(version: str = PROMPT_VERSION) -> list[dict]:
    return json.loads((PROMPT_DIR / f"{version}.examples.json").read_text(encoding="utf-8"))


def user_message(kind: str, label: str, authoritative: str, claim: str) -> str:
    what = "statute article" if kind == "statute" else "Court of Cassation decision (principle it established)"
    return (
        f"Type: {what}\n"
        f"Citation: {label}\n\n"
        f"AUTHORITATIVE TEXT:\n\"\"\"\n{authoritative.strip()}\n\"\"\"\n\n"
        f"CLAIM IN THE DRAFT:\n\"\"\"\n{claim.strip()}\n\"\"\""
    )


def build_messages(kind: str, label: str, authoritative: str, claim: str, version: str = PROMPT_VERSION) -> list[dict]:
    msgs = [{"role": "system", "content": system_prompt(version)}]
    for ex in examples(version):
        msgs.append({"role": "user", "content": user_message(ex["kind"], ex["label"], ex["authoritative"], ex["claim"])})
        msgs.append({"role": "assistant", "content": json.dumps(ex["output"], ensure_ascii=False)})
    msgs.append({"role": "user", "content": user_message(kind, label, authoritative, claim)})
    return msgs


def judge_claim(client: LMStudioClient, kind: str, label: str, authoritative: str, claim: str,
                version: str = PROMPT_VERSION) -> ClaimJudgement:
    return client.complete_json(
        build_messages(kind, label, authoritative, claim, version),
        response_format(),
        ClaimJudgement.model_validate,
        purpose="claim_check",
        max_tokens=400,
        meta={"prompt_version": version, "citation": label},
    )
