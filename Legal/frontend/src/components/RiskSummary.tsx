import { classNames } from "@/lib/utils";
import type { MSAAISuggestion, NegotiationChanges, NegotiationTask } from "@/types";

export function RiskSummary({
  riskScore,
  suggestions,
  changes,
  tasks,
}: {
  riskScore: number | null;
  suggestions: MSAAISuggestion[];
  changes: NegotiationChanges | null;
  tasks: NegotiationTask[];
}) {
  const sugCounts = countByFlag(suggestions);
  const chgCounts = countBySeverity(changes?.llm_narrative || []);
  const openTasks = tasks.filter((t) => t.status !== "resolved").length;
  const pendingSug = suggestions.filter((s) => s.decision === "pending").length;
  const totalSug = suggestions.length;
  const reviewPct = totalSug === 0 ? 0 : Math.round(((totalSug - pendingSug) / totalSug) * 100);

  const riskLabel = riskScore == null ? "—" : riskScore >= 70 ? "High" : riskScore >= 40 ? "Medium" : "Low";
  const riskClass =
    riskScore == null
      ? "text-label-secondary"
      : riskScore >= 70
        ? "text-error"
        : riskScore >= 40
          ? "text-amber-600"
          : "text-emerald-600";

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <Stat
        label="Overall risk"
        value={riskScore == null ? "—" : String(riskScore)}
        valueClass={riskClass}
        sub={riskLabel}
      />
      <Stat
        label="Clauses reviewed"
        value={`${totalSug - pendingSug} / ${totalSug}`}
        sub={`${reviewPct}% complete`}
        bar={{ pct: reviewPct, color: "bg-accent" }}
      />
      <Stat
        label="AI risk flags"
        value={String(sugCounts.high + sugCounts.medium + sugCounts.low)}
        sub={`${sugCounts.high} high · ${sugCounts.medium} med · ${sugCounts.low} low`}
        chips={[
          { count: sugCounts.high, color: "bg-red-500" },
          { count: sugCounts.medium, color: "bg-amber-500" },
          { count: sugCounts.low, color: "bg-blue-500" },
        ]}
      />
      <Stat
        label="Vendor changes"
        value={String(chgCounts.total)}
        sub={
          openTasks > 0
            ? `${openTasks} open task${openTasks === 1 ? "" : "s"}`
            : "All addressed"
        }
        chips={[
          { count: chgCounts.high, color: "bg-red-500" },
          { count: chgCounts.medium, color: "bg-amber-500" },
          { count: chgCounts.low, color: "bg-blue-500" },
        ]}
      />
    </div>
  );
}

function Stat({
  label,
  value,
  valueClass,
  sub,
  bar,
  chips,
}: {
  label: string;
  value: string;
  valueClass?: string;
  sub?: string;
  bar?: { pct: number; color: string };
  chips?: Array<{ count: number; color: string }>;
}) {
  return (
    <div className="bg-bg border border-separator/40 rounded-lg px-4 py-3">
      <div className="text-[11px] font-semibold text-label-secondary uppercase tracking-wide">
        {label}
      </div>
      <div className={classNames("text-2xl font-bold mt-1", valueClass || "text-label")}>
        {value}
      </div>
      {sub && <div className="text-xs text-label-secondary mt-0.5">{sub}</div>}
      {bar && (
        <div className="mt-2 h-1.5 bg-bg-secondary rounded-full overflow-hidden">
          <div
            className={classNames("h-full transition-all", bar.color)}
            style={{ width: `${bar.pct}%` }}
          />
        </div>
      )}
      {chips && chips.some((c) => c.count > 0) && (
        <div className="flex gap-1 mt-2">
          {chips.map((c, i) =>
            c.count > 0 ? (
              <span
                key={i}
                className={classNames(
                  "inline-flex items-center gap-1 text-[10px] font-semibold text-white px-1.5 py-0.5 rounded",
                  c.color,
                )}
              >
                {c.count}
              </span>
            ) : null,
          )}
        </div>
      )}
    </div>
  );
}

function countByFlag(suggestions: MSAAISuggestion[]) {
  const c = { high: 0, medium: 0, low: 0, none: 0 };
  for (const s of suggestions) {
    const k = (s.risk_flag || "none").toLowerCase() as keyof typeof c;
    if (k in c) c[k]++;
  }
  return c;
}

function countBySeverity(items: Array<{ severity: string }>) {
  const c = { high: 0, medium: 0, low: 0, total: items.length };
  for (const it of items) {
    const k = (it.severity || "").toLowerCase();
    if (k === "high") c.high++;
    else if (k === "medium") c.medium++;
    else if (k === "low") c.low++;
  }
  return c;
}
