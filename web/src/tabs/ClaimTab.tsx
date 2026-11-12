import { useEffect, useState } from "react";
import { api } from "../api";
import { StatusBadge } from "../components/Tables";
import type { CitationSet, ClaimResult, Kind } from "../types";

/** Test only the claim comparison: one claim against one corpus text (or your own text). */
export default function ClaimTab() {
  const [corpus, setCorpus] = useState<CitationSet | null>(null);
  const [kind, setKind] = useState<Kind>("statute");
  const [id, setId] = useState("");
  const [custom, setCustom] = useState(false);
  const [authoritative, setAuthoritative] = useState("");
  const [claim, setClaim] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ClaimResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.corpus().then(setCorpus).catch((e) => setError(e.message));
  }, []);
  const entries = corpus ? corpus[kind] : [];
  useEffect(() => {
    if (!custom && entries.length && !entries.some((e) => e.id === id)) setId(entries[0].id ?? "");
  }, [entries, id, custom]);
  const selected = entries.find((e) => e.id === id);

  const run = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.claim(custom ? { kind, authoritative, claim } : { kind, id, claim }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page narrow">
      <h2>Claim check</h2>
      <p className="muted">Compare one claim with one authoritative text. This is the step that decides SUPPORTED / CONTRADICTS / AMBIGUOUS.</p>
      <div className="row">
        <label>
          Kind
          <select value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
            <option value="statute">statute</option>
            <option value="cassation">cassation</option>
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={custom} onChange={(e) => setCustom(e.target.checked)} /> use my own text instead of the corpus
        </label>
      </div>
      {!custom ? (
        <>
          <label>
            Corpus entry
            <select value={id} onChange={(e) => setId(e.target.value)}>
              {entries.map((e) => (
                <option key={e.id} value={e.id}>{e.id} {e.law_name ? `· ${e.law_name}` : ""}</option>
              ))}
            </select>
          </label>
          {selected && <blockquote dir="auto">{selected.content}</blockquote>}
        </>
      ) : (
        <label>
          Authoritative text
          <textarea dir="auto" rows={4} value={authoritative} onChange={(e) => setAuthoritative(e.target.value)} />
        </label>
      )}
      <label>
        Claim made in the draft
        <textarea dir="auto" rows={4} value={claim} onChange={(e) => setClaim(e.target.value)} placeholder="e.g. ميعاد الاستئناف ستون يوماً من تاريخ التبليغ" />
      </label>
      <button className="primary" onClick={run} disabled={busy || !claim.trim() || (custom && !authoritative.trim())}>
        {busy ? "Checking…" : "Check claim"}
      </button>
      {error && <div className="err">{error}</div>}
      {result && (
        <div className="result">
          <StatusBadge status={result.status} />
          <span className="muted"> matches claim: <b>{String(result.matches_claim)}</b> · related: <b>{String(result.related)}</b></span>
          <p dir="auto">{result.reason}</p>
        </div>
      )}
    </div>
  );
}
