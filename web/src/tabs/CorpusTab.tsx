import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { CitationSet, Citation } from "../types";

export default function CorpusTab() {
  const [corpus, setCorpus] = useState<CitationSet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    api.corpus().then(setCorpus).catch((e) => setError(e.message));
  }, []);

  const match = (c: Citation) => !q.trim() || [c.id, c.law_name, c.content, c.chamber].some((v) => v?.toLowerCase().includes(q.trim().toLowerCase()));
  const filtered = useMemo(
    () => (corpus ? { statute: corpus.statute.filter(match), cassation: corpus.cassation.filter(match) } : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [corpus, q],
  );

  if (error) return <div className="page"><div className="err">{error}</div></div>;
  if (!filtered || !corpus) return <div className="page"><p className="muted">Loading…</p></div>;
  return (
    <div className="page">
      <h2>Corpus</h2>
      <p className="muted">
        {corpus.statute.length} statute articles and {corpus.cassation.length} cassation principles from <code>data/corpus/corpus.json</code> (built by{" "}
        <code>python -m citation_check corpus</code>). Currently synthetic seed data.
      </p>
      <input className="search" placeholder="Search IDs, law names, text…" value={q} onChange={(e) => setQ(e.target.value)} />
      {(["statute", "cassation"] as const).map((k) => (
        <div key={k}>
          <h3>{k === "statute" ? "Statutes" : "Cassation principles"} ({filtered[k].length})</h3>
          <table className="grid">
            <thead><tr><th>ID</th><th>{k === "statute" ? "Law" : "Chamber / date"}</th><th>Text</th></tr></thead>
            <tbody>
              {filtered[k].map((c) => (
                <tr key={c.id}>
                  <td className="mono">{c.id}</td>
                  <td dir="auto">{k === "statute" ? c.law_name : [c.chamber, c.date].filter(Boolean).join(" · ")}</td>
                  <td dir="auto">{c.content}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
