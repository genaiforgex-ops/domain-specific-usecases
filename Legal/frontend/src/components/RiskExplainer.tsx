import { useState, type ReactNode } from "react";

import { Icon } from "@/components/Icons";
import { classNames } from "@/lib/utils";
import type { GroundTruthCheck, MSAAISuggestion, MSARiskBreakdown } from "@/types";

export function RiskExplainer({
  breakdown,
  suggestions,
  onJumpToSuggestion,
}: {
  breakdown: MSARiskBreakdown | null | undefined;
  suggestions: MSAAISuggestion[];
  onJumpToSuggestion?: (orderIndex: number) => void;
}) {
  const [open, setOpen] = useState(false);
  if (!breakdown) return null;

  const weights = { high: 90, medium: 60, low: 30 };
  const gtFailed = breakdown.ground_truth_checks.filter((g) => !g.passed);

  return (
    <div className="rounded-xl border border-separator/40 bg-bg overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-bg-secondary/60 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <Icon.Shield className="w-4 h-4 text-accent shrink-0" />
          <span className="text-sm font-semibold text-label">How risk is calculated</span>
        </div>
        <span className="text-xs text-label-secondary">
          Overall {breakdown.overall.toFixed(1)} / 100
          <span className="ml-2">{open ? "▲" : "▼"}</span>
        </span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-separator/30 pt-3">
          <Step
            n={1}
            title="AI clause review vs playbook"
            body={
              <>
                Clause-level flags contribute a weighted score. AI-only score:{" "}
                <strong>{breakdown.from_ai_clauses.toFixed(1)}</strong>.
                <div className="flex gap-2 mt-2 flex-wrap">
                  <SeverityChip label="high" count={breakdown.by_severity.high} color="bg-red-500" />
                  <SeverityChip label="medium" count={breakdown.by_severity.medium} color="bg-amber-500" />
                  <SeverityChip label="low" count={breakdown.by_severity.low} color="bg-blue-500" />
                </div>
              </>
            }
          />

          <Step
            n={2}
            title="Your ground-truth lines"
            body={
              <>
                <p className="text-xs text-label-secondary mb-2">
                  {breakdown.ground_truth_passed} passed · {breakdown.ground_truth_failed} failed
                  {breakdown.from_ground_truth > 0 &&
                    ` · ${breakdown.from_ground_truth} added as high-risk suggestion(s)`}
                </p>
                {breakdown.ground_truth_checks.length === 0 ? (
                  <p className="text-xs text-label-secondary">No ground-truth guidelines were provided.</p>
                ) : (
                  <ul className="space-y-1">
                    {breakdown.ground_truth_checks.map((g) => (
                      <GroundTruthRow
                        key={g.term}
                        check={g}
                        suggestions={suggestions}
                        onJump={onJumpToSuggestion}
                      />
                    ))}
                  </ul>
                )}
              </>
            }
          />

          <Step
            n={3}
            title="Formula"
            body={
              <div className="text-xs text-label-secondary space-y-1 font-mono bg-bg-secondary rounded-lg p-3">
                <div>high = {weights.high} · medium = {weights.medium} · low = {weights.low}</div>
                <div>overall = average(severity weights), capped at 100</div>
                <div className="text-label font-sans font-medium mt-2">
                  Headline score: {breakdown.overall.toFixed(1)} — includes ground-truth findings
                </div>
              </div>
            }
          />

          {gtFailed.length > 0 && onJumpToSuggestion && (
            <p className="text-xs text-label-secondary">
              Failed ground-truth items appear as suggestions in the AI panel — click a row above to jump.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Step({
  n,
  title,
  body,
}: {
  n: number;
  title: string;
  body: ReactNode;
}) {
  return (
    <div className="flex gap-3">
      <div className="w-6 h-6 rounded-full bg-accent/10 text-accent text-xs font-bold flex items-center justify-center shrink-0">
        {n}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-label">{title}</div>
        <div className="text-sm text-label-secondary mt-1">{body}</div>
      </div>
    </div>
  );
}

function SeverityChip({
  label,
  count,
  color,
}: {
  label: string;
  count: number;
  color: string;
}) {
  if (count === 0) return null;
  return (
    <span
      className={classNames(
        "inline-flex items-center gap-1 text-[10px] font-semibold text-white px-2 py-0.5 rounded",
        color,
      )}
    >
      {count} {label}
    </span>
  );
}

function GroundTruthRow({
  check,
  suggestions,
  onJump,
}: {
  check: GroundTruthCheck;
  suggestions: MSAAISuggestion[];
  onJump?: (orderIndex: number) => void;
}) {
  const linked = suggestions.find(
    (s) =>
      (s.order_index ?? 0) >= 9000 &&
      (s.proposed_text === check.term || s.heading?.includes(check.term.slice(0, 40))),
  );

  return (
    <li className="flex items-start gap-2 text-sm">
      <span className={check.passed ? "text-emerald-600" : "text-error"}>
        {check.passed ? "✓" : "✗"}
      </span>
      <span className="flex-1 text-label">{check.term}</span>
      {!check.passed && linked && onJump && (
        <button
          type="button"
          className="text-xs text-accent hover:underline shrink-0"
          onClick={() => onJump(linked.order_index)}
        >
          View suggestion
        </button>
      )}
    </li>
  );
}
