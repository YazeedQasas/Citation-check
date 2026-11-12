"""LM Studio client: schema-constrained JSON calls with retries, validation and logging.

``complete_json`` returns an already-validated object (via the ``validate`` callable you pass)
or raises :class:`LLMError`. Every attempt is appended to a JSONL log (prompt, raw response,
usage, timing, outcome) so any result can be traced back.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

import httpx

from . import config

log = logging.getLogger(__name__)
T = TypeVar("T")


class LLMError(RuntimeError):
    """The model could not be reached or never produced valid output."""


class TruncatedOutputError(LLMError):
    """The reply hit the token limit (finish_reason == 'length'); retrying the same input won't help."""


class LMStudioClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        *,
        timeout: float | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        log_path: Path | str | None = None,
        transport: httpx.BaseTransport | None = None,
        backoff_s: float = 1.0,
    ):
        self.base_url = (base_url or config.LMSTUDIO_BASE_URL).rstrip("/")
        self.model = model or config.LMSTUDIO_MODEL
        self.temperature = config.LLM_TEMPERATURE if temperature is None else temperature
        self.max_tokens = max_tokens or config.LLM_MAX_TOKENS
        self.max_retries = config.LLM_MAX_RETRIES if max_retries is None else max_retries
        self.backoff_s = backoff_s
        self.log_path = Path(log_path) if log_path else config.LOG_DIR / "llm_calls.jsonl"
        self._http = httpx.Client(timeout=timeout or config.LLM_TIMEOUT_S, transport=transport)
        self.calls = 0  # successful calls, for reporting

    # ------------------------------------------------------------------ logging
    def _log(self, record: dict) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:  # logging must never break a run
            log.warning("could not write LLM log: %s", e)

    # ------------------------------------------------------------------ preflight
    def ping(self) -> None:
        """Fail early with a clear message if LM Studio is unreachable or the configured model is not available."""
        try:
            resp = self._http.get(f"{self.base_url}/models", timeout=10)
            resp.raise_for_status()
            ids = [m.get("id") for m in resp.json().get("data", [])]
        except (httpx.HTTPError, ValueError) as e:
            raise LLMError(
                f"cannot reach LM Studio at {self.base_url} ({type(e).__name__}). "
                f"Start the local server in LM Studio (Developer tab) and load '{self.model}'."
            ) from e
        if self.model not in ids:
            shown = ", ".join(i for i in ids if i) or "none"
            raise LLMError(f"model '{self.model}' is not available in LM Studio (available: {shown}). "
                           f"Load it, or set LMSTUDIO_MODEL.")

    # --------------------------------------------------------------------- call
    def complete_json(
        self,
        messages: list[dict],
        response_format: dict,
        validate: Callable[[Any], T] | None = None,
        *,
        purpose: str = "",
        max_tokens: int | None = None,
        meta: dict | None = None,
    ) -> T:
        """Call the model and return ``validate(parsed_json)``.

        Retries (up to ``max_retries``) on connection/timeout/5xx errors and on replies that are not
        valid JSON or fail ``validate``. Temperature is raised slightly on retries so a retry is not
        a byte-identical repeat. Raises :class:`TruncatedOutputError` at once if the reply was cut off.
        """
        last_error = "unknown"
        for attempt in range(self.max_retries + 1):
            temp = self.temperature + 0.2 * attempt
            body = {
                "model": self.model,
                "messages": messages,
                "temperature": temp,
                "max_tokens": max_tokens or self.max_tokens,
                "response_format": response_format,
            }
            rec = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "purpose": purpose, "model": self.model, "attempt": attempt, "temperature": temp,
                "meta": meta or {},
                "prompt": messages if config.LOG_FULL_PROMPT else messages[-1:],
                "n_messages": len(messages),
            }
            t0 = time.time()
            try:
                resp = self._http.post(f"{self.base_url}/chat/completions", json=body)
                rec["seconds"] = round(time.time() - t0, 2)
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
                resp.raise_for_status()
                data = resp.json()
                choice = data["choices"][0]
                raw = choice["message"]["content"] or ""
                rec.update(raw=raw, usage=data.get("usage", {}), finish_reason=choice.get("finish_reason"))
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, httpx.HTTPStatusError) as e:
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:
                    rec.update(outcome="http_error", error=str(e))
                    self._log(rec)
                    raise LLMError(f"LM Studio returned {e.response.status_code}: {e.response.text[:300]}") from e
                last_error = f"{type(e).__name__}: {e}"
                rec.update(seconds=round(time.time() - t0, 2), outcome="transport_error", error=last_error)
                self._log(rec)
                log.warning("LLM attempt %d failed (%s)", attempt + 1, last_error)
                if attempt < self.max_retries:
                    time.sleep(self.backoff_s * (attempt + 1))
                continue
            except (KeyError, IndexError, ValueError) as e:  # malformed envelope
                rec.update(outcome="bad_envelope", error=repr(e))
                self._log(rec)
                last_error = f"malformed response envelope: {e!r}"
                continue

            if rec["finish_reason"] == "length":
                rec["outcome"] = "truncated"
                self._log(rec)
                raise TruncatedOutputError("model output was cut off at the token limit")
            try:
                parsed = json.loads(raw)
                result = validate(parsed) if validate else parsed
            except Exception as e:  # invalid JSON or schema/validation failure
                last_error = f"invalid output: {type(e).__name__}: {str(e)[:200]}"
                rec.update(outcome="invalid", error=last_error)
                self._log(rec)
                log.warning("LLM attempt %d gave %s", attempt + 1, last_error)
                continue
            rec["outcome"] = "ok"
            self._log(rec)
            self.calls += 1
            return result
        raise LLMError(f"LLM call failed after {self.max_retries + 1} attempts: {last_error}")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "LMStudioClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
