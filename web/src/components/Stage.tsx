import { useState, type ReactNode } from "react";
import type { StageState } from "../types";
import { fmtMs } from "../util";

interface Props<T> {
  n: number;
  title: string;
  hint: string;
  stage: StageState<T>;
  onRun: () => void;
  runLabel?: string;
  disabled?: boolean;
  summary?: ReactNode;
  children?: ReactNode;
}

export default function Stage<T>({ n, title, hint, stage, onRun, runLabel = "Run", disabled, summary, children }: Props<T>) {
  const [open, setOpen] = useState(true);
  const running = stage.state === "running";
  return (
    <section className={`stage st-${stage.state}`}>
      <header>
        <span className="num">{stage.state === "done" ? "✓" : n}</span>
        <div className="titles" onClick={() => setOpen(!open)}>
          <h3>{title}</h3>
          <p>{hint}</p>
        </div>
        <div className="meta">
          {running && <span className="spin" aria-label="running" />}
          {stage.state === "done" && <span className="ms">{fmtMs(stage.ms)}</span>}
          {stage.state === "error" && <span className="bad">failed</span>}
          <button onClick={onRun} disabled={disabled || running}>
            {running ? "Running…" : stage.state === "done" ? "Re-run" : runLabel}
          </button>
        </div>
      </header>
      {stage.state === "error" && <div className="err">{stage.error}</div>}
      {stage.state === "done" && summary && <div className="summary">{summary}</div>}
      {open && stage.state === "done" && <div className="body">{children}</div>}
    </section>
  );
}
