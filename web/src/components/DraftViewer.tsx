import { useEffect, useMemo, useRef } from "react";
import type { Status } from "../types";
import { SEVERITY } from "../types";

export interface ViewerItem {
  key: string;
  start: number;
  end: number;
  label: string;
  status?: Status;
  origin?: string;
}

interface Props {
  text: string;
  items: ViewerItem[];
  selected: string | null;
  onSelect: (key: string) => void;
}

/** The draft with every found citation highlighted (colour = status once verified, else who found it). */
export default function DraftViewer({ text, items, selected, onSelect }: Props) {
  const box = useRef<HTMLDivElement>(null);

  const segments = useMemo(() => {
    const pts = new Set<number>([0, text.length]);
    for (const i of items) {
      pts.add(Math.max(0, Math.min(text.length, i.start)));
      pts.add(Math.max(0, Math.min(text.length, i.end)));
    }
    const sorted = [...pts].sort((a, b) => a - b);
    const segs: { s: number; e: number; active: ViewerItem[] }[] = [];
    for (let k = 0; k < sorted.length - 1; k++) {
      const s = sorted[k];
      const e = sorted[k + 1];
      if (e <= s) continue;
      segs.push({ s, e, active: items.filter((i) => i.start <= s && i.end >= e) });
    }
    return segs;
  }, [text, items]);

  useEffect(() => {
    if (!selected || !box.current) return;
    const el = [...box.current.querySelectorAll<HTMLElement>("mark")].find((m) => (m.dataset.keys ?? "").split(" ").includes(selected));
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [selected]);

  return (
    <div className="viewer" ref={box} dir="auto">
      {segments.map(({ s, e, active }) => {
        const chunk = text.slice(s, e);
        if (!active.length) return <span key={s}>{chunk}</span>;
        const statuses = active.map((a) => a.status).filter((x): x is Status => !!x);
        const status = statuses.length ? statuses.reduce((a, b) => (SEVERITY[b] > SEVERITY[a] ? b : a)) : undefined;
        const cls = status ? `mk s-${status}` : `mk o-${active[0].origin ?? "llm"}`;
        const isSel = selected !== null && active.some((a) => a.key === selected);
        return (
          <mark
            key={s}
            className={`${cls}${isSel ? " sel" : ""}`}
            data-keys={active.map((a) => a.key).join(" ")}
            title={active.map((a) => a.label + (a.status ? ` — ${a.status}` : "")).join("\n")}
            onClick={() => onSelect(active[0].key)}
          >
            {chunk}
          </mark>
        );
      })}
    </div>
  );
}
