import { useEffect, useState } from "react";

import { AISuggestionsPanel, suggestionCounts } from "@/components/AISuggestionsPanel";
import { RiskExplainer } from "@/components/RiskExplainer";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ChangeHistoryPanel } from "@/components/review/ChangeHistoryPanel";
import { PlaybookDeviationPanel } from "@/components/review/PlaybookDeviationPanel";
import { classNames } from "@/lib/utils";
import type {
  ContractSuggestionsPreview,
  MSAAISuggestion,
  MSARiskBreakdown,
  MSASuggestionsPreview,
  MSATracker,
  PlaybookSummary,
  ReviewChangeEntry,
  ReviewFinding,
} from "@/types";

export type ChangeMode = "track" | "suggest";

export function ReviewWorkspace({
  contractType,
  suggestions,
  riskScore,
  riskBreakdown,
  playbookSummary,
  changeHistory = [],
  status,
  locked = false,
  canApprove,
  changeMode,
  onChangeMode,
  onDecide,
  onDecideAll,
  onPreview,
  onApply,
  onRunReview,
  preview,
  busy,
  error,
  onJumpToSuggestion,
  onHighlightExcerpt,
  clauseBankOptions,
  onInsertFromBank,
  showRiskExplainer = true,
  allowTextEdit = false,
}: {
  contractType: string;
  suggestions: ReviewFinding[];
  riskScore: number | null;
  riskBreakdown?: MSARiskBreakdown | null;
  playbookSummary?: PlaybookSummary | null;
  changeHistory?: ReviewChangeEntry[];
  status: string;
  locked?: boolean;
  canApprove: boolean;
  changeMode: ChangeMode;
  onChangeMode: (m: ChangeMode) => void;
  onDecide: (
    orderIndex: number,
    decision: "accept" | "modify" | "reject",
    reviewerEdit?: string,
  ) => Promise<void>;
  onDecideAll?: () => Promise<void>;
  onPreview: () => void;
  onApply: (force?: boolean, editedText?: string) => void;
  onRunReview?: () => void;
  preview: MSASuggestionsPreview | ContractSuggestionsPreview | null;
  busy?: boolean;
  error?: string | null;
  onJumpToSuggestion?: (orderIndex: number) => void;
  onHighlightExcerpt?: (text: string) => void;
  clauseBankOptions?: Array<{ id: number; title: string; body_text: string; tier: string }>;
  onInsertFromBank?: (orderIndex: number, bodyText: string) => void;
  showRiskExplainer?: boolean;
  allowTextEdit?: boolean;
}) {
  const [applyConfirmOpen, setApplyConfirmOpen] = useState(false);
  const [pendingEdited, setPendingEdited] = useState<string | undefined>(undefined);
  const counts = suggestionCounts(suggestions as MSAAISuggestion[]);

  const trackerShim: MSATracker = {
    id: 0,
    vendor_name: "",
    vendor_email: "",
    contract_type: contractType,
    deal_reference: null,
    status,
    risk_score: riskScore,
    current_version: 0,
    redlined_text: null,
    ai_suggestions: suggestions as MSAAISuggestion[],
    template_id: null,
    canonical_version_id: null,
    executed_version_id: null,
    gmail_thread_id: null,
    assigned_to_id: null,
    created_at: "",
    updated_at: "",
    emails: [],
    risk_breakdown: riskBreakdown,
  };

  function requestApply(force?: boolean, editedText?: string) {
    if (!force && counts.actionable > 0) {
      setPendingEdited(editedText);
      setApplyConfirmOpen(true);
      return;
    }
    setApplyConfirmOpen(false);
    onApply(force, editedText ?? pendingEdited);
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-accent/20 bg-accent/5 px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-label">
            Reviewing against {contractType} playbook
            {playbookSummary
              ? ` (${playbookSummary.clause_count} clauses, ${playbookSummary.required_count} required)`
              : ""}
          </p>
          <p className="text-xs text-label-secondary mt-0.5">
            Risk score {riskScore?.toFixed(1) ?? "—"} · {counts.pending} pending · {counts.actionable}{" "}
            ready to apply
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <ModeToggle mode={changeMode} onChange={onChangeMode} disabled={locked} />
          {onRunReview && (
            <Button size="sm" variant="secondary" onClick={onRunReview} disabled={busy || locked}>
              Re-run review
            </Button>
          )}
        </div>
      </div>

      {showRiskExplainer && (
        <RiskExplainer
          breakdown={riskBreakdown}
          suggestions={suggestions as MSAAISuggestion[]}
          onJumpToSuggestion={onJumpToSuggestion}
        />
      )}

      <PlaybookDeviationPanel
        suggestions={suggestions}
        contractType={contractType}
        clauseCount={playbookSummary?.clause_count}
      />

      <ChangeHistoryPanel entries={changeHistory} />

      {suggestions.length === 0 ? (
        <Card>
          <div className="text-sm text-label-secondary text-center py-8">
            No AI findings yet. Run a review to analyse this draft against the playbook.
          </div>
        </Card>
      ) : (
        <AISuggestionsPanel
          tracker={trackerShim}
          canApprove={canApprove && !locked}
          busy={busy ?? false}
          error={error ?? null}
          preview={preview as MSASuggestionsPreview | null}
          onDecide={onDecide}
          onDecideAll={onDecideAll}
          onPreview={onPreview}
          onApply={requestApply}
          onHighlight={onHighlightExcerpt}
          clauseBankOptions={clauseBankOptions}
          onInsertFromBank={onInsertFromBank}
          allowTextEdit={allowTextEdit}
        />
      )}

      {applyConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-bg rounded-xl shadow-xl border border-separator/40 max-w-md w-full p-5 space-y-4">
            <h2 className="text-lg font-semibold text-label">Apply {counts.actionable} change(s)?</h2>
            <p className="text-sm text-label-secondary">
              Mode: <strong>{changeMode}</strong> — changes will be{" "}
              {changeMode === "track" ? "recorded as a visible redline" : "saved as a clean revision"}.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setApplyConfirmOpen(false)}>
                Cancel
              </Button>
              <Button onClick={() => requestApply(true)} disabled={busy}>
                Apply changes
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ModeToggle({
  mode,
  onChange,
  disabled,
}: {
  mode: ChangeMode;
  onChange: (m: ChangeMode) => void;
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex rounded-lg border border-separator/40 p-0.5 bg-bg-secondary text-xs">
      {(["track", "suggest"] as const).map((m) => (
        <button
          key={m}
          type="button"
          disabled={disabled}
          onClick={() => onChange(m)}
          className={classNames(
            "px-3 py-1.5 rounded-md font-medium capitalize transition",
            mode === m ? "bg-bg text-accent shadow-sm" : "text-label-secondary hover:text-label",
          )}
        >
          {m} mode
        </button>
      ))}
    </div>
  );
}
