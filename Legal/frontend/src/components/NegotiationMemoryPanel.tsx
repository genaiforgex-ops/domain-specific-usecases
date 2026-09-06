import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { NegotiationMemoryEntry } from "@/types";

const KIND_LABELS: Record<string, string> = {
  guideline: "Guideline",
  decision: "Decision",
  edit_summary: "Edit",
  glossary: "Glossary",
  bot_qa: "LegalBot Q&A",
};

export function NegotiationMemoryPanel({ trackerId }: { trackerId: number }) {
  const [rows, setRows] = useState<NegotiationMemoryEntry[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api
      .listMSAMemory(trackerId)
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [open, trackerId]);

  return (
    <div className="rounded-xl border border-separator/40 bg-bg overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-bg-secondary/60"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-sm font-semibold text-label">Negotiation memory</span>
        <span className="text-xs text-label-secondary">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-separator/30 px-4 py-3 max-h-64 overflow-y-auto">
          {loading && <p className="text-xs text-label-secondary">Loading…</p>}
          {!loading && rows.length === 0 && (
            <p className="text-xs text-label-secondary">
              Guidelines, decisions, and edits will appear here as the negotiation progresses.
            </p>
          )}
          <ul className="space-y-2">
            {rows.map((r) => (
              <li key={r.id} className="text-xs border-l-2 border-accent/30 pl-2">
                <div className="flex items-center gap-2 text-label-secondary">
                  <span className="font-semibold text-label">
                    {KIND_LABELS[r.kind] || r.kind}
                  </span>
                  <span>{formatDate(r.created_at)}</span>
                </div>
                <p className="text-label-secondary mt-0.5 whitespace-pre-wrap line-clamp-4">
                  {formatMemoryContent(r)}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function formatMemoryContent(row: NegotiationMemoryEntry): string {
  if (row.kind === "decision" || row.kind === "bot_qa") {
    try {
      const parsed = JSON.parse(row.content) as Record<string, unknown>;
      if (row.kind === "bot_qa") {
        return `Q: ${String(parsed.q || "")}\nA: ${String(parsed.a || "").slice(0, 200)}`;
      }
      return `Suggestion #${parsed.suggestion_id}: ${parsed.decision}`;
    } catch {
      return row.content;
    }
  }
  return row.content;
}
