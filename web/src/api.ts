import type {
  CleanResult, ClaimResult, CitationSet, Extraction, Health, LogEntry, Report, SampleSet,
} from "./types";

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch(url, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Cannot reach the API. Start it with: python -m citation_check serve");
  }
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* keep the status text */
    }
    throw new Error(detail);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => req<Health>("GET", "/api/health"),
  corpus: () => req<CitationSet>("GET", "/api/corpus"),
  samples: () => req<SampleSet[]>("GET", "/api/samples"),
  clean: (text: string) => req<CleanResult>("POST", "/api/stage/clean", { text }),
  regex: (text: string) => req<Extraction>("POST", "/api/stage/regex", { text }),
  extract: (text: string, use_llm: boolean, regex_net: boolean) =>
    req<Extraction>("POST", "/api/stage/extract", { text, use_llm, regex_net }),
  verify: (extracted: CitationSet, draft_name?: string) =>
    req<Report>("POST", "/api/stage/verify", { extracted, draft_name }),
  claim: (body: { kind: string; id?: string; authoritative?: string; claim: string }) =>
    req<ClaimResult>("POST", "/api/claim", body),
  log: (limit = 30) => req<LogEntry[]>("GET", `/api/llm-log?limit=${limit}`),
  async upload(file: File): Promise<string> {
    const r = await fetch(`/api/upload?filename=${encodeURIComponent(file.name)}`, { method: "POST", body: await file.arrayBuffer() });
    const j = await r.json();
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : "upload failed");
    return j.text as string;
  },
};
