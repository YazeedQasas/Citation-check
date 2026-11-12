export type Kind = "statute" | "cassation";
export type Status = "SUPPORTED" | "CONTRADICTS" | "AMBIGUOUS" | "NOT_FOUND";
export const STATUSES: Status[] = ["NOT_FOUND", "CONTRADICTS", "AMBIGUOUS", "SUPPORTED"]; // most worrying first
export const SEVERITY: Record<Status, number> = { NOT_FOUND: 3, CONTRADICTS: 2, AMBIGUOUS: 1, SUPPORTED: 0 };

export interface Citation {
  id?: string;
  law_number?: string;
  year?: string;
  article?: string;
  law_name?: string;
  clause?: string;
  appeal_number?: string;
  chamber?: string;
  date?: string;
  content?: string;
  citation_text?: string;
  span?: [number, number];
  origin?: string;
  source?: string;
}
export interface CitationSet {
  statute: Citation[];
  cassation: Citation[];
}
export interface Entry extends Citation {
  kind: Kind;
}

export interface Extraction {
  citations: CitationSet;
  warnings: string[];
  complete: boolean;
  n_chunks: number;
  llm_calls: number;
  seconds: number;
}
export interface CleanResult {
  cleaned: string;
  raw_chars: number;
  cleaned_chars: number;
  removed: Record<string, number>;
  chunks: { start: number; end: number; chars: number }[];
  chunk_max_chars: number;
}
export interface Finding {
  kind: Kind;
  id?: string | null;
  status: Status;
  citation_text?: string;
  claim: string;
  reason: string;
  matched_corpus_id?: string;
  corpus_content?: string;
  closest_corpus_id?: string;
  span?: [number, number];
  origin?: string;
  needs_review: boolean;
}
export interface Report {
  draft?: string;
  counts: Record<Status, number>;
  findings: Finding[];
  warnings: string[];
  extraction_complete: boolean;
}
export interface GoldItem {
  kind: Kind;
  id: string;
  expected_status: Status;
  lang?: string;
  claim?: string;
}
export interface SampleSet {
  key: string;
  label: string;
  drafts: { name: string; text: string; gold: GoldItem[] }[];
}
export interface Health {
  lm_studio: { ok: boolean; error?: string; base_url: string; model: string };
  corpus: { ok: boolean; error?: string; path: string; statute?: number; cassation?: number };
  prompts: { extraction: string; claim: string };
  chunk_max_chars: number;
}
export interface ClaimResult {
  status: Status;
  matches_claim: boolean;
  related: boolean;
  reason: string;
  authoritative: string;
}
export interface LogEntry {
  ts: string;
  purpose: string;
  model: string;
  attempt: number;
  temperature: number;
  seconds?: number;
  outcome?: string;
  error?: string;
  finish_reason?: string;
  usage?: Record<string, unknown>;
  prompt?: { role: string; content: string }[];
  n_messages?: number;
  raw?: string;
  meta?: Record<string, unknown>;
}

export type StageState<T> = { state: "idle" | "running" | "done" | "error"; data?: T; error?: string; ms?: number };
