import { useEffect, useMemo, useRef, useState } from "react";

import { AISuggestionCard } from "@/components/AISuggestionCard";
import type { DiffViewHandle } from "@/components/DiffView";
import { RedlinePreview, redlineStats } from "@/components/RedlinePreview";
import { Icon } from "@/components/Icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Textarea } from "@/components/ui/Textarea";
import { lineDiffBlocks } from "@/lib/utils";
import type { MSASuggestionsPreview, MSATracker } from "@/types";

const CATEGORY_FILTERS = [
  { id: "all", label: "All" },
  { id: "legal_risk", label: "Legal risk" },
  { id: "policy", label: "Policy" },
  { id: "grammar", label: "Grammar" },
  { id: "spelling", label: "Spelling" },
  { id: "ambiguity", label: "Ambiguity" },
  { id: "missing_clause", label: "Missing clause" },
  { id: "definition", label: "Definitions" },
] as const;

export function suggestionCounts(suggestions: MSATracker["ai_suggestions"]) {
  const items = suggestions || [];
  return {
    total: items.length,
    pending: items.filter((s) => s.decision === "pending").length,
    accepted: items.filter((s) => s.decision === "accept").length,
    modified: items.filter((s) => s.decision === "modify").length,
    rejected: items.filter((s) => s.decision === "reject").length,
    actionable: items.filter((s) => s.decision === "accept" || s.decision === "modify").length,
  };
}

function filterSuggestionsByCategory(suggestions: MSATracker["ai_suggestions"], category: string) {
  const items = suggestions || [];
  if (category === "all") return items;
  return items.filter((s) => (s.category || "legal_risk") === category);
}

export function AISuggestionsPanel({
  tracker,
  canApprove,
  onDecide,
  onDecideAll,
  onPreview,
  onApply,
  preview,
  busy,
  error,
  onHighlight,
  clauseBankOptions,
  onInsertFromBank,
  allowTextEdit = false,
}: {
  tracker: MSATracker;
  canApprove: boolean;
  onDecide: (
    orderIndex: number,
    decision: "accept" | "modify" | "reject",
    reviewerEdit?: string,
  ) => Promise<void>;
  onDecideAll?: () => Promise<void>;
  onPreview: () => void;
  onApply: (force?: boolean, editedText?: string) => void;
  preview: MSASuggestionsPreview | null;
  busy: boolean;
  error: string | null;
  onHighlight?: (text: string) => void;
  clauseBankOptions?: Array<{ id: number; title: string; body_text: string; tier: string }>;
  onInsertFromBank?: (orderIndex: number, bodyText: string) => void;
  /** Allow curating the combined accepted text before applying (text/PDF sources only). */
  allowTextEdit?: boolean;
}) {
  const [category, setCategory] = useState<string>("all");
  const counts = useMemo(() => suggestionCounts(tracker.ai_suggestions), [tracker.ai_suggestions]);
  const filtered = useMemo(
    () => filterSuggestionsByCategory(tracker.ai_suggestions, category),
    [tracker.ai_suggestions, category],
  );
  const locked = ["sent_to_vendor", "executed"].includes(tracker.status);

  const [editing, setEditing] = useState(false);
  const [editedText, setEditedText] = useState("");
  const [jumpCursor, setJumpCursor] = useState(0);
  const diffRef = useRef<DiffViewHandle>(null);

  useEffect(() => {
    if (preview) {
      setEditedText(preview.edited_text);
      setEditing(false);
      setJumpCursor(0);
    }
  }, [preview]);

  const canEdit = allowTextEdit && !!preview;

  const displayBlocks = useMemo(() => {
    if (!preview) return [];
    if (editing && canEdit) return lineDiffBlocks(preview.base_text, editedText);
    return preview.diff_blocks;
  }, [preview, editing, canEdit, editedText]);

  const changeIndices = useMemo(
    () =>
      displayBlocks.reduce<number[]>((acc, b, i) => {
        if (b.kind !== "equal") acc.push(i);
        return acc;
      }, []),
    [displayBlocks],
  );

  const stats = useMemo(() => redlineStats(displayBlocks), [displayBlocks]);

  function jumpTo(step: number) {
    if (changeIndices.length === 0) return;
    const next = (jumpCursor + step + changeIndices.length) % changeIndices.length;
    setJumpCursor(next);
    diffRef.current?.scrollToIndex(changeIndices[next]);
  }

  const curatedText = () => (canEdit && editing ? editedText : undefined);

  return (
    <Card
      title="AI review findings"
      subtitle="Actionable issues from legal risk, policy, grammar, and drafting analysis. Accept or modify the findings you want (rejected ones are left unchanged), preview the combined redline, then save as a new document version."
      actions={
        <div className="flex items-center gap-2 flex-wrap">
          <Badge className="bg-bg-secondary text-label-secondary">{counts.actionable} ready to apply</Badge>
          <Badge className="bg-amber-100 text-amber-800">{counts.pending} pending</Badge>
        </div>
      }
    >
      <div className="flex flex-wrap gap-2 mb-4">
        {CATEGORY_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setCategory(f.id)}
            className={`text-xs px-2.5 py-1 rounded-full border transition ${
              category === f.id
                ? "bg-accent/10 border-accent/30 text-accent"
                : "bg-bg border-separator/40 text-label-secondary hover:border-separator/60"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-4 text-center">
        <CountPill label="Total" value={counts.total} />
        <CountPill label="Pending" value={counts.pending} />
        <CountPill label="Accepted" value={counts.accepted} accent="text-emerald-700" />
        <CountPill label="Modified" value={counts.modified} accent="text-blue-700" />
        <CountPill label="Rejected" value={counts.rejected} accent="text-error" />
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        {canApprove && onDecideAll && (
          <Button
            size="sm"
            variant="secondary"
            disabled={busy || locked || counts.pending === 0}
            onClick={() => onDecideAll()}
          >
            <Icon.Check className="w-3.5 h-3.5 mr-1" />
            Accept all pending
          </Button>
        )}
        <Button size="sm" variant="secondary" disabled={busy || counts.actionable === 0} onClick={onPreview}>
          <Icon.Documents className="w-3.5 h-3.5 mr-1" />
          Preview accepted changes
        </Button>
        {canApprove && (
          <Button
            size="sm"
            disabled={busy || locked || counts.actionable === 0}
            onClick={() => onApply(false, curatedText())}
          >
            <Icon.Check className="w-3.5 h-3.5 mr-1" />
            Save as new version
          </Button>
        )}
        {canApprove && counts.actionable === 0 && (
          <span className="text-[11px] text-label-tertiary self-center">
            Accept or modify at least one finding to enable saving.
          </span>
        )}
      </div>

      {error && <p className="text-sm text-error mb-3">{error}</p>}

      {preview && (
        <div className="rounded-xl border border-warning/20 bg-amber-50/40 p-4 space-y-3 mb-4">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="text-sm text-label-secondary">
              Preview{" "}
              {"base_version_number" in preview && preview.base_version_number != null
                ? `from v${preview.base_version_number}`
                : ""}
              : {preview.applied_count} change(s) will apply
              {preview.blocked_count > 0 && (
                <span className="text-amber-800"> · {preview.blocked_count} blocked</span>
              )}
            </div>
            {canApprove && preview.blocked_count > 0 && (
              <Button
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => onApply(true, curatedText())}
              >
                Save partial as new version
              </Button>
            )}
          </div>

          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-label-secondary">
                {changeIndices.length} change{changeIndices.length === 1 ? "" : "s"}
              </span>
              <span className="inline-flex items-center gap-1 text-[11px]">
                <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-medium">
                  +{stats.additions} added
                </span>
                <span className="px-1.5 py-0.5 rounded bg-red-100 text-red-800 font-medium">
                  −{stats.deletions} removed
                </span>
              </span>
              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={changeIndices.length === 0}
                  onClick={() => jumpTo(-1)}
                  title="Previous change"
                >
                  ↑ Prev
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={changeIndices.length === 0}
                  onClick={() => jumpTo(1)}
                  title="Next change"
                >
                  Next ↓
                </Button>
              </div>
            </div>
            {allowTextEdit && (
              <Button
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => setEditing((v) => !v)}
              >
                <Icon.Pencil className="w-3.5 h-3.5 mr-1" />
                {editing ? "Hide editor" : "Edit combined text"}
              </Button>
            )}
          </div>

          {!allowTextEdit && (
            <p className="text-xs text-label-secondary">
              This is a Word document. Applying preserves the original formatting, so accepted
              suggestions are applied structurally rather than as edited plain text.
            </p>
          )}

          {editing && canEdit && (
            <Textarea
              label="Combined accepted text — curate before applying"
              rows={14}
              value={editedText}
              onChange={(e) => setEditedText(e.target.value)}
            />
          )}

          <RedlinePreview
            ref={diffRef}
            title={
              "base_version_number" in preview && preview.base_version_number != null
                ? `After accepted suggestions · from v${preview.base_version_number}`
                : "After accepted suggestions"
            }
            blocks={displayBlocks}
            height={300}
          />
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="text-sm text-label-secondary text-center py-6">
          No actionable findings in this category.
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((s) => (
            <AISuggestionCard
              key={s.order_index}
              suggestion={s}
              canAct={canApprove && !locked}
              disabled={busy}
              onDecide={(decision, reviewerEdit) => onDecide(s.order_index, decision, reviewerEdit)}
              onHighlight={onHighlight}
              clauseBankOptions={clauseBankOptions}
              onInsertFromBank={
                onInsertFromBank ? (body) => onInsertFromBank(s.order_index, body) : undefined
              }
            />
          ))}
        </div>
      )}
    </Card>
  );
}

function CountPill({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div className="rounded-lg border border-separator/30 bg-bg-secondary px-2 py-2">
      <div className="text-[10px] uppercase tracking-wide text-label-secondary">{label}</div>
      <div className={`text-lg font-semibold tabular-nums ${accent || "text-label"}`}>{value}</div>
    </div>
  );
}
