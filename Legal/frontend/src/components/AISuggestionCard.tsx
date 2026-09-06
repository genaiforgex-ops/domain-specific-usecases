import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import { classNames, riskColor } from "@/lib/utils";
import type { MSAAISuggestion } from "@/types";

export function AISuggestionCard({
  suggestion,
  canAct,
  disabled,
  onDecide,
  onHighlight,
  clauseBankOptions,
  onInsertFromBank,
}: {
  suggestion: MSAAISuggestion;
  canAct: boolean;
  disabled?: boolean;
  onDecide: (decision: "accept" | "modify" | "reject", reviewerEdit?: string) => Promise<void> | void;
  onHighlight?: (text: string) => void;
  clauseBankOptions?: Array<{ id: number; title: string; body_text: string; tier: string }>;
  onInsertFromBank?: (bodyText: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const proposed = suggestion.proposed_text || suggestion.ai_suggestion || "";
  const original = suggestion.original_text || suggestion.clause_text;
  const [edit, setEdit] = useState(suggestion.reviewer_edit || proposed);
  const [busy, setBusy] = useState(false);

  const hasActionableRedline = !!(proposed && proposed.trim());
  const flag = (suggestion.risk_flag || "none").toLowerCase();
  const decided = suggestion.decision !== "pending";
  const category = (suggestion.category || "legal_risk").replace(/_/g, " ");

  async function run(decision: "accept" | "modify" | "reject", reviewerEdit?: string) {
    setBusy(true);
    try {
      await onDecide(decision, reviewerEdit);
    } finally {
      setBusy(false);
      setEditing(false);
    }
  }

  return (
    <div
      data-suggestion-id={suggestion.order_index}
      className={classNames(
        "border rounded-lg overflow-hidden bg-bg transition",
        decided && "opacity-75",
        flag === "high" && "border-error/20",
        flag === "medium" && "border-warning/20",
        flag === "low" && "border-accent/20",
        flag === "none" && "border-separator/40",
      )}
    >
      <button
        type="button"
        className="w-full text-left px-4 py-3 min-h-tap flex items-start gap-3 hover:bg-bg-secondary"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={`${open ? "Collapse" : "Expand"} finding: ${suggestion.heading || `Finding #${suggestion.order_index + 1}`}`}
      >
        <span
          className={classNames(
            "mt-1.5 w-2 h-2 rounded-full flex-shrink-0",
            flag === "high" ? "bg-error" :
            flag === "medium" ? "bg-warning" :
            flag === "low" ? "bg-accent" : "bg-label-tertiary",
          )}
          aria-hidden
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge className={riskColor(flag)}>{flag.toUpperCase()}</Badge>
            <Badge className="bg-bg-secondary text-label-secondary border-separator/40 capitalize">{category}</Badge>
            <Badge className={decisionColor(suggestion.decision)}>
              {labelDecision(suggestion.decision)}
            </Badge>
            {suggestion.playbook_clause_type && (
              <Badge className="bg-accent/10 text-accent border-accent/20 text-[10px]">
                {suggestion.playbook_clause_type}
              </Badge>
            )}
            <span className="text-sm font-medium text-label truncate">
              {suggestion.heading || `Finding #${suggestion.order_index + 1}`}
            </span>
          </div>
          {suggestion.rationale && (
            <p className="text-xs text-label-secondary mt-1 line-clamp-2">{suggestion.rationale}</p>
          )}
        </div>
        <svg
          className={classNames(
            "w-4 h-4 mt-1 text-label-tertiary flex-shrink-0 transition-transform",
            open && "rotate-90",
          )}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          {suggestion.rationale && (
            <div className="text-xs text-label-secondary bg-bg-secondary border border-separator/30 rounded px-3 py-2">
              <span className="font-semibold text-label-secondary">AI rationale:</span>{" "}
              {suggestion.rationale}
            </div>
          )}

          {suggestion.standard_position_excerpt && (
            <div className="text-xs bg-accent/5 border border-accent/20 rounded px-3 py-2">
              <span className="font-semibold text-label">Standard position:</span>{" "}
              {suggestion.standard_position_excerpt}
            </div>
          )}

          {hasActionableRedline ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <div className="text-[11px] font-semibold text-label-secondary mb-1">Original excerpt</div>
                <pre className="text-xs font-mono whitespace-pre-wrap bg-red-50 border-l-2 border-red-300 rounded px-2 py-2 max-h-64 overflow-auto text-label-secondary">
                  {original}
                </pre>
              </div>
              <div>
                <div className="text-[11px] font-semibold text-label-secondary mb-1 flex items-center justify-between">
                  <span>Proposed change</span>
                  {canAct && !decided && !editing && (
                    <button
                      type="button"
                      className="text-[11px] text-accent hover:underline"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditing(true);
                      }}
                    >
                      Edit
                    </button>
                  )}
                </div>
                {editing ? (
                  <Textarea
                    rows={Math.min(12, Math.max(4, edit.split("\n").length + 1))}
                    value={edit}
                    onChange={(e) => setEdit(e.target.value)}
                  />
                ) : (
                  <pre className="text-xs font-mono whitespace-pre-wrap bg-emerald-50 border-l-2 border-emerald-300 rounded px-2 py-2 max-h-64 overflow-auto text-label-secondary">
                    {suggestion.reviewer_edit || proposed}
                  </pre>
                )}
              </div>
            </div>
          ) : (
            <div>
              <div className="text-[11px] font-semibold text-label-secondary mb-1">Context</div>
              <pre className="text-xs font-mono whitespace-pre-wrap bg-bg-secondary border border-separator/40 rounded px-3 py-2 max-h-64 overflow-auto text-label-secondary">
                {suggestion.clause_text}
              </pre>
            </div>
          )}

          {suggestion.apply_error && (
            <p className="text-xs text-error bg-red-50 border border-red-100 rounded px-2 py-1">
              Apply blocked: {suggestion.apply_error}
            </p>
          )}

          {suggestion.regulatory_ref && (
            <p className="text-xs text-label-secondary">Regulatory: {suggestion.regulatory_ref}</p>
          )}

          {onHighlight && original && (
            <button
              type="button"
              className="text-xs text-accent hover:underline"
              onClick={() => onHighlight(original)}
            >
              Locate in document
            </button>
          )}

          {clauseBankOptions && clauseBankOptions.length > 0 && onInsertFromBank && canAct && (
            <select
              className="text-xs border border-separator/40 rounded px-2 py-1 bg-bg"
              defaultValue=""
              onChange={(e) => {
                const opt = clauseBankOptions.find((c) => String(c.id) === e.target.value);
                if (opt) onInsertFromBank(opt.body_text);
                e.target.value = "";
              }}
            >
              <option value="">Insert from clause bank…</option>
              {clauseBankOptions.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.tier}: {c.title}
                </option>
              ))}
            </select>
          )}

          {canAct && (
            <div className="flex items-center gap-2 pt-1 flex-wrap">
              {editing ? (
                <>
                  <Button size="sm" disabled={busy || disabled} onClick={() => run("modify", edit)}>
                    Save decision
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={busy}
                    onClick={() => {
                      setEditing(false);
                      setEdit(suggestion.reviewer_edit || proposed);
                    }}
                  >
                    Cancel
                  </Button>
                </>
              ) : (
                <>
                  {hasActionableRedline && (
                    <>
                      <Button size="sm" disabled={busy || disabled} onClick={() => run("accept")}>
                        Accept
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={busy || disabled}
                        onClick={() => setEditing(true)}
                      >
                        Modify
                      </Button>
                    </>
                  )}
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={busy || disabled}
                    onClick={() => run("reject")}
                  >
                    Reject
                  </Button>
                </>
              )}
              {suggestion.confidence > 0 && (
                <span className="text-[11px] text-label-tertiary ml-auto">
                  AI confidence: {Math.round(suggestion.confidence * 100)}%
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function labelDecision(d: string): string {
  return d.charAt(0).toUpperCase() + d.slice(1);
}

function decisionColor(d: string): string {
  if (d === "accept") return "bg-emerald-100 text-emerald-800";
  if (d === "modify") return "bg-blue-100 text-blue-800";
  if (d === "reject") return "bg-red-100 text-red-800";
  return "bg-bg-secondary text-label-secondary";
}
