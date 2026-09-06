import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { classNames } from "@/lib/utils";
import type { ReviewFinding } from "@/types";

export function PlaybookDeviationPanel({
  suggestions,
  contractType,
  clauseCount,
}: {
  suggestions: ReviewFinding[];
  contractType: string;
  clauseCount?: number;
}) {
  const [open, setOpen] = useState(false);
  const grouped = useMemo(() => {
    const map = new Map<string, ReviewFinding[]>();
    for (const s of suggestions) {
      const key = s.playbook_clause_type || s.category || "Other";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(s);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [suggestions]);

  const withPlaybook = suggestions.filter((s) => s.playbook_clause_type || s.standard_position_excerpt);

  if (withPlaybook.length === 0) return null;

  return (
    <div className="rounded-xl border border-separator/40 bg-bg overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-bg-secondary/60"
        onClick={() => setOpen((v) => !v)}
      >
        <div>
          <span className="text-sm font-semibold text-label">Playbook deviations</span>
          <p className="text-xs text-label-secondary mt-0.5">
            Reviewing against {contractType} playbook
            {clauseCount != null ? ` (${clauseCount} clauses)` : ""} · {withPlaybook.length} linked
            finding(s)
          </p>
        </div>
        <span className="text-xs text-label-secondary">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-separator/30 px-4 py-3 space-y-3 max-h-80 overflow-y-auto">
          {grouped.map(([clauseType, items]) => (
            <div key={clauseType} className="border border-separator/30 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-sm font-medium text-label">{clauseType}</span>
                <Badge className="bg-bg-secondary text-label-secondary text-[10px]">
                  {items.length}
                </Badge>
              </div>
              {items.map((s) => (
                <DeviationRow key={s.order_index} finding={s} />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DeviationRow({ finding }: { finding: ReviewFinding }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="text-xs border-t border-separator/20 pt-2 mt-2 first:border-0 first:pt-0 first:mt-0">
      <button
        type="button"
        className="text-accent hover:underline"
        onClick={() => setExpanded((v) => !v)}
      >
        {finding.heading || `Finding #${finding.order_index + 1}`} — compare positions
      </button>
      {expanded && (
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
          <CompareCol title="Standard position" text={finding.standard_position_excerpt} tone="accent" />
          <CompareCol title="Draft excerpt" text={finding.original_text || finding.clause_text} />
          <CompareCol title="Proposed" text={finding.proposed_text || finding.ai_suggestion} tone="emerald" />
        </div>
      )}
      {finding.regulatory_ref && (
        <p className="text-label-secondary mt-1">Regulatory: {finding.regulatory_ref}</p>
      )}
    </div>
  );
}

function CompareCol({
  title,
  text,
  tone,
}: {
  title: string;
  text?: string | null;
  tone?: "accent" | "emerald";
}) {
  return (
    <div
      className={classNames(
        "rounded-md p-2 bg-bg-secondary",
        tone === "accent" && "border border-accent/20",
        tone === "emerald" && "border border-emerald-500/20",
      )}
    >
      <div className="font-semibold text-label-secondary mb-1">{title}</div>
      <p className="text-label whitespace-pre-wrap line-clamp-6">{text || "—"}</p>
    </div>
  );
}
