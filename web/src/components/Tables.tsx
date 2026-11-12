import { Fragment, useEffect, useRef } from "react";
import type { Entry, Finding, GoldItem, Status } from "../types";
import { STATUSES } from "../types";
import { compareGold, keyOf } from "../util";

export const StatusBadge = ({ status }: { status: Status }) => <span className={`badge s-${status}`}>{status.replace("_", " ")}</span>;

const useScrollTo = (selected: string | null) => {
  const ref = useRef<HTMLTableElement>(null);
  useEffect(() => {
    if (!selected || !ref.current) return;
    ref.current.querySelector<HTMLElement>(`tr[data-key="${CSS.escape(selected)}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected]);
  return ref;
};

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="kv">
      <span>{label}</span>
      <div dir="auto">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ extracted citations */
export function ExtractionTable({ entries, selected, onSelect }: { entries: Entry[]; selected: string | null; onSelect: (k: string) => void }) {
  const ref = useScrollTo(selected);
  if (!entries.length) return <p className="muted">No citations found.</p>;
  return (
    <table className="grid" ref={ref}>
      <thead>
        <tr>
          <th>Found by</th>
          <th>Kind</th>
          <th>ID</th>
          <th>Quote in the draft</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e, i) => {
          const key = keyOf(e.kind, e.span, e.id, i);
          return (
            <Fragment key={key + i}>
              <tr data-key={key} className={selected === key ? "sel" : ""} onClick={() => onSelect(key)}>
                <td><span className={`badge o-${e.origin ?? "llm"}`}>{e.origin ?? "llm"}</span></td>
                <td>{e.kind}</td>
                <td className="mono">{e.id ?? <span className="warn">no ID (incomplete)</span>}</td>
                <td dir="auto">{e.citation_text}</td>
              </tr>
              {selected === key && (
                <tr className="detail">
                  <td colSpan={4}>
                    <Detail label="Claim in the draft">{e.content || <em>none extracted</em>}</Detail>
                    <Detail label="Fields">
                      <span className="mono">
                        {e.kind === "statute"
                          ? `law ${e.law_number ?? "?"} / ${e.year ?? "?"}, article ${e.article ?? "?"}${e.law_name ? ` (${e.law_name})` : ""}${e.clause ? `, clause ${e.clause}` : ""}`
                          : `appeal ${e.appeal_number ?? "?"} / ${e.year ?? "?"}${e.chamber ? ` (${e.chamber})` : ""}${e.date ? `, ${e.date}` : ""}`}
                      </span>
                    </Detail>
                    {e.span && <Detail label="Position">characters {e.span[0]}–{e.span[1]}</Detail>}
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

/* ----------------------------------------------------------------------------- findings */
export function FindingsTable({ findings, gold, selected, onSelect }: {
  findings: Finding[]; gold: GoldItem[]; selected: string | null; onSelect: (k: string) => void;
}) {
  const ref = useScrollTo(selected);
  const cmp = gold.length ? compareGold(findings, gold) : null;
  const ordered = [...findings].sort((a, b) => STATUSES.indexOf(a.status) - STATUSES.indexOf(b.status));
  return (
    <>
      {cmp && (
        <div className={`goldbar ${cmp.correct === cmp.total ? "all" : "some"}`}>
          Gold labels: <b>{cmp.correct}/{cmp.total}</b> statuses match
          {cmp.missed.length > 0 && <> · missed (not extracted): {cmp.missed.map((m) => m.id).join(", ")}</>}
        </div>
      )}
      <table className="grid" ref={ref}>
        <thead>
          <tr>
            <th>Status</th>
            {cmp && <th>Gold</th>}
            <th>Kind</th>
            <th>ID</th>
            <th>Quote in the draft</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((f, i) => {
            const key = keyOf(f.kind, f.span, f.id, i);
            const g = f.id ? cmp?.rows.get(`${f.kind}|${f.id}`) : undefined;
            return (
              <Fragment key={key + i}>
                <tr data-key={key} className={selected === key ? "sel" : ""} onClick={() => onSelect(key)}>
                  <td><StatusBadge status={f.status} />{f.needs_review && <span className="warn"> review</span>}</td>
                  {cmp && (
                    <td className={g ? (g.ok ? "ok" : "bad") : ""}>
                      {g ? (g.ok ? "✓" : `✗ expected ${g.expected.replace("_", " ")}`) : "—"}
                    </td>
                  )}
                  <td>{f.kind}</td>
                  <td className="mono">{f.id ?? <span className="warn">no ID</span>}</td>
                  <td dir="auto">{f.citation_text}</td>
                </tr>
                {selected === key && (
                  <tr className="detail">
                    <td colSpan={cmp ? 5 : 4}>
                      <Detail label="Why">{f.reason || "—"}</Detail>
                      <Detail label="Claim in the draft">{f.claim || <em>none extracted</em>}</Detail>
                      {f.corpus_content && <Detail label={`Corpus text (${f.matched_corpus_id})`}>{f.corpus_content}</Detail>}
                      {f.closest_corpus_id && <Detail label="Closest corpus entry"><span className="mono">{f.closest_corpus_id}</span></Detail>}
                      {f.origin && <Detail label="Found by">{f.origin}</Detail>}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
