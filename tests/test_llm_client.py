import json

import httpx
import pytest

from citation_check.llm import LLMError, LMStudioClient, TruncatedOutputError

FMT = {"type": "json_schema", "json_schema": {"name": "x", "strict": True, "schema": {"type": "object"}}}
MSGS = [{"role": "system", "content": "s"}, {"role": "user", "content": "نص"}]


def _ok(content, finish="stop"):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": finish}],
                                     "usage": {"completion_tokens": 5}})


def _client(tmp_path, handler, **kw):
    return LMStudioClient("http://x/v1", "m", log_path=tmp_path / "log.jsonl",
                          transport=httpx.MockTransport(handler), backoff_s=0, **kw)


def _log(tmp_path):
    return [json.loads(line) for line in (tmp_path / "log.jsonl").read_text(encoding="utf-8").splitlines()]


def test_success_sends_schema_and_temperature_zero_and_logs(tmp_path):
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return _ok('{"a": 1}')

    c = _client(tmp_path, handler)
    assert c.complete_json(MSGS, FMT, purpose="t") == {"a": 1}
    assert seen["temperature"] == 0 and seen["response_format"] == FMT and seen["model"] == "m"
    rec = _log(tmp_path)[0]
    assert rec["outcome"] == "ok" and rec["raw"] == '{"a": 1}' and rec["seconds"] >= 0
    assert rec["prompt"] == MSGS[-1:] and rec["purpose"] == "t"


def test_retries_on_invalid_json_then_succeeds_with_higher_temperature(tmp_path):
    replies = iter(["not json", '{"a": 2}'])
    temps = []

    def handler(req):
        temps.append(json.loads(req.content)["temperature"])
        return _ok(next(replies))

    c = _client(tmp_path, handler)
    assert c.complete_json(MSGS, FMT) == {"a": 2}
    assert temps == [0, 0.2]
    assert [r["outcome"] for r in _log(tmp_path)] == ["invalid", "ok"]


def test_validation_failure_is_retried_then_raises(tmp_path):
    def validate(obj):
        raise ValueError("bad shape")

    c = _client(tmp_path, lambda req: _ok('{"a": 1}'), max_retries=2)
    with pytest.raises(LLMError, match="after 3 attempts"):
        c.complete_json(MSGS, FMT, validate)
    assert len(_log(tmp_path)) == 3


def test_retries_on_server_error_but_not_on_client_error(tmp_path):
    n = {"i": 0}

    def flaky(req):
        n["i"] += 1
        return httpx.Response(503) if n["i"] == 1 else _ok("{}")

    assert _client(tmp_path, flaky).complete_json(MSGS, FMT) == {}
    with pytest.raises(LLMError, match="400"):
        _client(tmp_path, lambda req: httpx.Response(400, text="bad request")).complete_json(MSGS, FMT)


def test_connection_error_retries_then_fails_cleanly(tmp_path):
    def down(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMError, match="ConnectError"):
        _client(tmp_path, down, max_retries=1).complete_json(MSGS, FMT)
    assert [r["outcome"] for r in _log(tmp_path)] == ["transport_error"] * 2


def test_truncation_raises_immediately_without_retry(tmp_path):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return _ok('{"a": [1, 2', finish="length")

    with pytest.raises(TruncatedOutputError):
        _client(tmp_path, handler).complete_json(MSGS, FMT)
    assert calls["n"] == 1 and _log(tmp_path)[0]["outcome"] == "truncated"
