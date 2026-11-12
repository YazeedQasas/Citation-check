import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { LogEntry } from "../types";

/** What the model actually saw and said: the last LLM calls from logs/llm_calls.jsonl. */
export default function LogTab() {
  const [log, setLog] = useState<LogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const load = useCallback(() => {
    api.log(40).then(setLog).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  return (
    <div className="page">
      <div className="row between">
        <h2>LLM calls</h2>
        <button onClick={load}>Refresh</button>
      </div>
      <p className="muted">Newest first. Shows the last message sent to the model (set <code>LOG_FULL_PROMPT=1</code> before starting the API to see the whole prompt), its raw reply, and timing.</p>
      {error && <div className="err">{error}</div>}
      {log && log.length === 0 && <p className="muted">No calls logged yet. Run an LLM stage first.</p>}
      {log?.map((e, i) => (
        <div className="logrow" key={i}>
          <div className="logh" onClick={() => setOpen(open === i ? null : i)}>
            <span className={`badge ${e.outcome === "ok" ? "s-SUPPORTED" : "s-NOT_FOUND"}`}>{e.outcome ?? "?"}</span>
            <b>{e.purpose}</b>
            <span className="muted">{e.ts.replace("T", " ").replace("+00:00", " UTC")} · {e.seconds ?? "?"}s · attempt {e.attempt + 1}</span>
          </div>
          {open === i && (
            <div className="logb">
              {e.error && <div className="err">{e.error}</div>}
              <h4>Sent (last message)</h4>
              <pre dir="auto">{e.prompt?.map((m) => `[${m.role}]\n${m.content}`).join("\n\n")}</pre>
              <h4>Raw reply</h4>
              <pre dir="auto">{e.raw ?? ""}</pre>
              <p className="muted">{JSON.stringify({ finish: e.finish_reason, usage: e.usage, temperature: e.temperature, ...e.meta })}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
