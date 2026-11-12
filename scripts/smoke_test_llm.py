"""Smoke-test LM Studio + Gemma 4 E4B: Arabic, English, and schema-constrained JSON."""
import json
import sys
import time

import httpx

sys.path.insert(0, "src")
from citation_check import config  # noqa: E402

URL = f"{config.LMSTUDIO_BASE_URL}/chat/completions"


def call(messages, response_format=None, max_tokens=400):
    body = {
        "model": config.LMSTUDIO_MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if response_format:
        body["response_format"] = response_format
    t0 = time.time()
    r = httpx.post(URL, json=body, timeout=config.LLM_TIMEOUT_S)
    dt = time.time() - t0
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"], data.get("usage", {}), dt


def main():
    print("== English ==")
    out, usage, dt = call([{"role": "user", "content": "Reply with one short sentence: what is a cassation court?"}])
    print(out, usage, f"{dt:.1f}s")

    print("\n== Arabic ==")
    out, usage, dt = call([{"role": "user", "content": "أجب بجملة واحدة: ما هي محكمة النقض؟"}])
    print(out, usage, f"{dt:.1f}s")
    if usage.get("completion_tokens"):
        print(f"tokens/sec ~ {usage['completion_tokens'] / dt:.1f}")

    print("\n== Structured output ==")
    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "citations",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "statute": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "law_number": {"type": "string"},
                                "year": {"type": "string"},
                                "article": {"type": "string"},
                            },
                            "required": ["law_number", "year", "article"],
                            "additionalProperties": False,
                        },
                    },
                    "cassation": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "appeal_number": {"type": "string"},
                                "year": {"type": "string"},
                            },
                            "required": ["appeal_number", "year"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["statute", "cassation"],
                "additionalProperties": False,
            },
        },
    }
    text = "عملاً بأحكام المادة (٢٣) من قانون رقم (١٢) لسنة ٢٠١٠، وحيث استقر قضاء محكمة النقض في الطعن رقم ٤٥٦ لسنة ٢٠١٥."
    out, usage, dt = call(
        [
            {"role": "system", "content": "Extract statute and cassation citations as JSON. Use only what is in the text."},
            {"role": "user", "content": text},
        ],
        response_format=schema,
        max_tokens=600,
    )
    print(out, usage, f"{dt:.1f}s")
    parsed = json.loads(out)
    assert set(parsed) == {"statute", "cassation"}, "schema keys missing"
    print("\nOK: structured output parsed and matches schema keys.")


if __name__ == "__main__":
    main()
