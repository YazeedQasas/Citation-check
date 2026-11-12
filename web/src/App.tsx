import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { api } from "./api";
import DraftViewer, { type ViewerItem } from "./components/DraftViewer";
import Stage from "./components/Stage";
import { ExtractionTable, FindingsTable, StatusBadge } from "./components/Tables";
import ClaimTab from "./tabs/ClaimTab";
import CorpusTab from "./tabs/CorpusTab";
import LogTab from "./tabs/LogTab";
import type {
  CitationSet, CleanResult, Extraction, GoldItem, Health, Report, SampleSet, StageState,
} from "./types";
import { STATUSES } from "./types";
import { keyOf, sortedEntries } from "./util";

type Tab = "walk" | "claim" | "corpus" | "log";
const idle = <T,>(): StageState<T> => ({ state: "idle" });

async function runStage<T>(set: Dispatch<SetStateAction<StageState<T>>>, fn: () => Promise<T>): Promise<T | undefined> {
  set({ state: "running" });
  const t0 = performance.now();
  try {
    const data = await fn();
    set({ state: "done", data, ms: Math.round(performance.now() - t0) });
    return data;
  } catch (e) {
    set({ state: "error", error: (e as Error).message });
    return undefined;
  }
}

export default function App() {
  const [tab, setTab] = useState<Tab>("walk");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [samples, setSamples] = useState<SampleSet[]>([]);

  const [text, setText] = useState("");
  const [draftName, setDraftName] = useState("");
  const [gold, setGold] = useState<GoldItem[]>([]);
  const [sampleKey, setSampleKey] = useState("");
  const [editing, setEditing] = useState(true);
  const [useLlm, setUseLlm] = useState(true);
  const [regexNet, setRegexNet] = useState(true);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [clean, setClean] = useState<StageState<CleanResult>>(idle());
  const [regex, setRegex] = useState<StageState<Extraction>>(idle());
  const [extract, setExtract] = useState<StageState<Extraction>>(idle());
  const [verify, setVerify] = useState<StageState<Report>>(idle());
  const [extractedJson, setExtractedJson] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [busyAll, setBusyAll] = useState(false);

  const refreshHealth = useCallback(() => {
    api.health().then((h) => { setHealth(h); setHealthError(null); }).catch((e) => setHealthError(e.message));
  }, []);
  useEffect(() => {
    refreshHealth();
    api.samples().then(setSamples).catch(() => undefined);
  }, [refreshHealth]);

  const resetStages = () => {
    setClean(idle()); setRegex(idle()); setExtract(idle()); setVerify(idle());
    setExtractedJson(""); setSelected(null);
  };
  const changeText = (t: string) => { setText(t); resetStages(); };

  const loadSample = (value: string) => {
    setSampleKey(value);
    const [set, name] = value.split("/");
    const d = samples.find((s) => s.key === set)?.drafts.find((x) => x.name === name);
    if (!d) return;
    changeText(d.text);
    setDraftName(d.name);
    setGold(d.gold);
    setEditing(false);
  };

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    setUploadError(null);
    try {
      const t = await f.name.toLowerCase().endsWith(".txt") ? await f.text() : await api.upload(f);
      changeText(t); setDraftName(f.name); setGold([]); setSampleKey(""); setEditing(false);
    } catch (e) {
      setUploadError((e as Error).message);
    }
  };

  // ------------------------------------------------------------------ stages
  const runClean = () => runStage(setClean, () => api.clean(text));
  const runRegex = () => runStage(setRegex, () => api.regex(text));
  const runExtract = async () => {
    const r = await runStage(setExtract, () => api.extract(text, useLlm, regexNet));
    if (r) setExtractedJson(JSON.stringify(r.citations, null, 2));
    return r;
  };
  const runVerifyWith = (cs: CitationSet) => runStage(setVerify, () => api.verify(cs, draftName || undefined));
  const runVerify = async () => {
    let cs: CitationSet;
    try {
      cs = JSON.parse(extractedJson);
    } catch {
      setVerify({ state: "error", error: extractedJson.trim() ? "The verification input is not valid JSON." : "Nothing to verify yet: run the extraction first (or load the regex result below)." });
      return;
    }
    await runVerifyWith(cs);
  };
  const runAll = async () => {
    if (!text.trim()) return;
    setBusyAll(true);
    setSelected(null);
    await runClean();
    await runRegex();
    const ex = await runExtract();
    if (ex) await runVerifyWith(ex.citations);
    setBusyAll(false);
  };

  // ------------------------------------------------------- highlights in the draft
  const items: ViewerItem[] = useMemo(() => {
    if (verify.data) {
      return verify.data.findings.flatMap((f, i) =>
        f.span ? [{ key: keyOf(f.kind, f.span, f.id, i), start: f.span[0], end: f.span[1], label: f.id ?? "incomplete citation", status: f.status, origin: f.origin }] : []);
    }
    const src = extract.data ?? regex.data;
    if (!src) return [];
    return sortedEntries(src.citations).flatMap((e, i) =>
      e.span ? [{ key: keyOf(e.kind, e.span, e.id, i), start: e.span[0], end: e.span[1], label: e.id ?? "incomplete citation", origin: e.origin }] : []);
  }, [verify.data, extract.data, regex.data]);

  const llmDown = useLlm && health && !health.lm_studio.ok;

  return (
    <div className="app">
      <header className="top">
        <h1>Citation Check</h1>
        <nav>
          {([["walk", "Walk the pipeline"], ["claim", "Claim check"], ["corpus", "Corpus"], ["log", "LLM calls"]] as [Tab, string][]).map(([k, label]) => (
            <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>
          ))}
        </nav>
        <div className="health" onClick={refreshHealth} title="Click to refresh">
          {healthError ? (
            <span className="pill bad">API not running</span>
          ) : health ? (
            <>
              <span className={`pill ${health.lm_studio.ok ? "good" : "bad"}`} title={health.lm_studio.error ?? health.lm_studio.model}>
                LM Studio {health.lm_studio.ok ? "ready" : "unavailable"}
              </span>
              <span className={`pill ${health.corpus.ok ? "good" : "bad"}`} title={health.corpus.error ?? health.corpus.path}>
                corpus {health.corpus.ok ? `${health.corpus.statute}+${health.corpus.cassation}` : "missing"}
              </span>
            </>
          ) : null}
        </div>
      </header>
      {healthError && <div className="banner">{healthError}. In a terminal: <code>python -m citation_check serve</code></div>}
      {llmDown && tab === "walk" && (
        <div className="banner">LM Studio is not reachable ({health?.lm_studio.error}). Untick “Use LLM” to try the code-only stages, or start the LM Studio server.</div>
      )}

      {tab === "walk" && (
        <main className="walk">
          <div className="left">
            <section className="card draft">
              <div className="row between">
                <h2>Draft</h2>
                <button className="link" onClick={() => setEditing(!editing)} disabled={!text && editing}>{editing ? "View with highlights" : "Edit text"}</button>
              </div>
              <div className="row">
                <select value={sampleKey} onChange={(e) => loadSample(e.target.value)}>
                  <option value="">Load a sample draft…</option>
                  {samples.map((s) => (
                    <optgroup key={s.key} label={s.label}>
                      {s.drafts.map((d) => <option key={d.name} value={`${s.key}/${d.name}`}>{d.name}{d.gold.length ? ` (${d.gold.length} labelled)` : ""}</option>)}
                    </optgroup>
                  ))}
                </select>
                <label className="file">Upload .txt / .docx<input type="file" accept=".txt,.docx" onChange={(e) => onFile(e.target.files?.[0])} hidden /></label>
              </div>
              {uploadError && <div className="err">{uploadError}</div>}
              {editing ? (
                <textarea className="draftbox" dir="auto" value={text} placeholder="Paste a draft judgment here (Arabic, English fragments are fine)…"
                  onChange={(e) => { changeText(e.target.value); setSampleKey(""); setGold([]); }} />
              ) : (
                <DraftViewer text={text} items={items} selected={selected} onSelect={setSelected} />
              )}
              <div className="legend">
                {verify.data ? STATUSES.map((s) => <span key={s} className={`badge s-${s}`}>{s.replace("_", " ")}</span>) :
                  <><span className="badge o-regex">regex</span><span className="badge o-llm">llm</span></>}
                <span className="muted">click a highlight to see its details</span>
              </div>
              <div className="row opts">
                <label className="check"><input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> Use LLM for extraction</label>
                <label className="check"><input type="checkbox" checked={regexNet} onChange={(e) => setRegexNet(e.target.checked)} /> Regex safety net</label>
              </div>
              <button className="primary" onClick={runAll} disabled={!text.trim() || busyAll}>{busyAll ? "Running all stages…" : "Run all stages"}</button>
            </section>
          </div>

          <div className="right">
            <Stage n={1} title="Clean the text" hint="Removes noise (tatweel, invisible marks, odd spaces). Digits and wording stay as written."
              stage={clean} onRun={runClean} disabled={!text.trim()}
              summary={clean.data && <>{clean.data.raw_chars} → {clean.data.cleaned_chars} characters · {clean.data.chunks.length} chunk(s) of up to {clean.data.chunk_max_chars}</>}>
              {clean.data && (
                <>
                  <p className="muted">
                    Removed: {clean.data.removed.invisible_marks_and_tatweel} invisible marks/tatweel, {clean.data.removed.whitespace_and_other} spaces/line breaks.
                    {clean.data.chunks.length > 1 && <> Chunks: {clean.data.chunks.map((c) => `${c.start}–${c.end}`).join(", ")}.</>}
                  </p>
                  <pre className="textbox" dir="auto">{clean.data.cleaned}</pre>
                </>
              )}
            </Stage>

            <Stage n={2} title="Regex safety net (code only)" hint="Finds explicit citations without any LLM. Fast and predictable, but only knows the phrasings it was written for."
              stage={regex} onRun={runRegex} disabled={!text.trim()}
              summary={regex.data && <>{regex.data.citations.statute.length} statute + {regex.data.citations.cassation.length} cassation</>}>
              {regex.data && <ExtractionTable entries={sortedEntries(regex.data.citations)} selected={selected} onSelect={setSelected} />}
            </Stage>

            <Stage n={3} title="Extraction layer" hint="Gemma reads the draft and returns citations as JSON; code then checks quotes, fixes numbers, resolves “the same law”, and adds what the model missed."
              stage={extract} onRun={runExtract} disabled={!text.trim() || (useLlm && !!health && !health.lm_studio.ok)}
              summary={extract.data && <>
                {extract.data.citations.statute.length} statute + {extract.data.citations.cassation.length} cassation · {extract.data.llm_calls} LLM call(s) · {extract.data.n_chunks} chunk(s) · {extract.data.seconds}s
                {!extract.data.complete && <span className="bad"> · incomplete</span>}
              </>}>
              {extract.data && (
                <>
                  {extract.data.warnings.length > 0 && (
                    <details className="warns" open>
                      <summary>{extract.data.warnings.length} note(s) from the code safety checks</summary>
                      <ul>{extract.data.warnings.map((w, i) => <li key={i} dir="auto">{w}</li>)}</ul>
                    </details>
                  )}
                  <ExtractionTable entries={sortedEntries(extract.data.citations)} selected={selected} onSelect={setSelected} />
                </>
              )}
            </Stage>

            <details className="vinput">
              <summary>Input to verification (editable JSON){extractedJson ? "" : " — empty until extraction runs"}</summary>
              <div className="row">
                <button onClick={() => extract.data && setExtractedJson(JSON.stringify(extract.data.citations, null, 2))} disabled={!extract.data}>Load LLM extraction</button>
                <button onClick={() => regex.data && setExtractedJson(JSON.stringify(regex.data.citations, null, 2))} disabled={!regex.data}>Load regex result</button>
              </div>
              <textarea className="json" spellCheck={false} value={extractedJson} onChange={(e) => setExtractedJson(e.target.value)}
                placeholder='{"statute": [{"law_number": "41", "year": "2008", "article": "23", "content": "…"}], "cassation": []}' />
              <p className="muted">Edit a claim, change an article number, or delete an entry, then run stage 4 to see how the verdict changes. IDs are always recomputed from the number fields.</p>
            </details>

            <Stage n={4} title="Verification layer" hint="Matches each ID with the corpus (no LLM). For IDs that exist, Gemma compares the draft's claim with the corpus text."
              stage={verify} onRun={runVerify} disabled={!extractedJson.trim() || (!!health && !health.lm_studio.ok)}
              summary={verify.data && <span className="counts">
                {STATUSES.map((s) => <span key={s}><StatusBadge status={s} /> {verify.data!.counts[s]}</span>)}
              </span>}>
              {verify.data && (
                <>
                  {verify.data.warnings.length > 0 && <p className="muted">{verify.data.warnings.length} extraction note(s) carried over (see stage 3).</p>}
                  <FindingsTable findings={verify.data.findings} gold={gold} selected={selected} onSelect={setSelected} />
                </>
              )}
            </Stage>
          </div>
        </main>
      )}
      {tab === "claim" && <ClaimTab />}
      {tab === "corpus" && <CorpusTab />}
      {tab === "log" && <LogTab />}
    </div>
  );
}
