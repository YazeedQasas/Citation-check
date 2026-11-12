import type { CitationSet, Entry, Finding, GoldItem, Kind, Status } from "./types";
import { SEVERITY } from "./types";

export const flatten = (cs: CitationSet): Entry[] => [
  ...cs.statute.map((c) => ({ ...c, kind: "statute" as Kind })),
  ...cs.cassation.map((c) => ({ ...c, kind: "cassation" as Kind })),
];

/** Same key for an extracted entry and the finding made from it, so selection links the tables and the draft. */
export const keyOf = (kind: Kind, span: [number, number] | undefined, id: string | null | undefined, i: number) =>
  `${kind}|${span ? span.join("-") : `x${i}`}|${id ?? ""}`;

export const sortedEntries = (cs: CitationSet): Entry[] =>
  flatten(cs).sort((a, b) => (a.span?.[0] ?? 1e12) - (b.span?.[0] ?? 1e12));

export const worst = (statuses: Status[]): Status | undefined =>
  statuses.length ? statuses.reduce((a, b) => (SEVERITY[b] > SEVERITY[a] ? b : a)) : undefined;

export interface GoldCompare {
  rows: Map<string, { expected: Status; ok: boolean }>; // keyed kind|id
  correct: number;
  total: number;
  missed: GoldItem[];
}

/** Compare findings with gold labels: per gold item the actual status is the worst among findings with that ID. */
export function compareGold(findings: Finding[], gold: GoldItem[]): GoldCompare {
  const rows = new Map<string, { expected: Status; ok: boolean }>();
  const missed: GoldItem[] = [];
  let correct = 0;
  for (const g of gold) {
    const hits = findings.filter((f) => f.kind === g.kind && f.id === g.id).map((f) => f.status);
    const actual = worst(hits);
    if (actual === undefined) {
      missed.push(g);
      continue;
    }
    const ok = actual === g.expected_status;
    rows.set(`${g.kind}|${g.id}`, { expected: g.expected_status, ok });
    if (ok) correct++;
  }
  return { rows, correct, total: gold.length, missed };
}

export const fmtMs = (ms?: number) => (ms === undefined ? "" : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`);

export const short = (s: string | undefined, n = 90) => (!s ? "" : s.length > n ? s.slice(0, n - 1) + "…" : s);
