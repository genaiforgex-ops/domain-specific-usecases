import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import { classNames, riskColor } from "@/lib/utils";
import type { NegotiationChangeItem, NegotiationChanges } from "@/types";

type Severity = "high" | "medium" | "low" | "none";
type ChangeKind = "insert" | "delete" | "modify";

/** Per-hunk decision: keep vendor, revert to legal, or use reviewer-edited text. */
export type VendorHunkDecision =
  | { action: "accept" }
  | { action: "reject" }
  | { action: "edit"; text: string };

function sevRank(s: string): number {
  const m: Record<string, number> = { high: 0, medium: 1, low: 2, none: 3 };
  return m[s.toLowerCase()] ?? 3;
}

function sevDot(s: string): string {
  const k = s.toLowerCase();
  if (k === "high") return "bg-red-500";
  if (k === "medium") return "bg-amber-500";
  if (k === "low") return "bg-blue-500";
  return "bg-label-tertiary";
}

function changeKind(item: NegotiationChangeItem): ChangeKind {
  const hasOld = Boolean((item.old_text || "").trim());
  const hasNew = Boolean((item.new_text || "").trim());
  if (!hasOld && hasNew) return "insert";
  if (hasOld && !hasNew) return "delete";
  return "modify";
}

function kindLabel(kind: ChangeKind): string {
  if (kind === "insert") return "Vendor insert";
  if (kind === "delete") return "Vendor deletion";
  return "Modification";
}

function kindClass(kind: ChangeKind): string {
  if (kind === "insert") return "bg-emerald-50 text-emerald-800 border-emerald-200";
  if (kind === "delete") return "bg-red-50 text-error border-error/20";
  return "bg-amber-50 text-amber-900 border-amber-200";
}

function decisionLabel(d: VendorHunkDecision | undefined): string | null {
  if (!d) return null;
  if (d.action === "accept") return "Accepted vendor";
  if (d.action === "reject") return "Held legal position";
  return "Alternate proposed";
}

function inferRecommendation(item: NegotiationChangeItem): "accept" | "reject" | "edit" | null {
  const raw = (item.suggested_action || "").toLowerCase();
  if (!raw) return null;
  if (/\b(accept|keep|agree|ok to|fine to)\b/.test(raw) && !/\b(reject|counter|push back|do not)\b/.test(raw)) {
    return "accept";
  }
  if (/\b(reject|counter|push back|revert|restore|hold|do not accept)\b/.test(raw)) {
    return "reject";
  }
  if (/\b(edit|revise|propose|negotiate|amend|modify|clarify)\b/.test(raw)) {
    return "edit";
  }
  return null;
}

export function VendorChangesPanel({
  changes,
  onJumpToDiff,
  onSaveVersion,
  busy,
  canAct,
  changePages,
}: {
  changes: NegotiationChanges | null;
  onJumpToDiff: (diffIndex: number) => void;
  /**
   * Persist the reviewer's per-change decisions as a new redline version.
   * Every reconcilable change should have an accept / reject / edit decision.
   */
  onSaveVersion?: (decisions: Record<number, VendorHunkDecision>) => Promise<void> | void;
  busy?: boolean;
  canAct: boolean;
  /** diff_index → { page, line, severity } in the right (vendor) document */
  changePages?: Map<number, { page: number; line: number; severity: string }>;
}) {
  const [filter, setFilter] = useState<Severity | "all">("all");
  const [decisions, setDecisions] = useState<Record<number, VendorHunkDecision>>({});
  const [editDrafts, setEditDrafts] = useState<Record<number, string>>({});
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [focusIdx, setFocusIdx] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [briefOpen, setBriefOpen] = useState(true);
  const [pendingFocusDiff, setPendingFocusDiff] = useState<number | null>(null);

  const comparisonId = changes?.comparison_id ?? null;
  useEffect(() => {
    setDecisions({});
    setEditDrafts({});
    setEditingIndex(null);
    setFocusIdx(0);
    setSaveError(null);
    setBriefOpen(true);
  }, [comparisonId]);

  const items = useMemo<NegotiationChangeItem[]>(() => {
    if (!changes) return [];
    const arr = [...(changes.llm_narrative || [])];
    arr.sort((a, b) => sevRank(a.severity) - sevRank(b.severity));
    return arr;
  }, [changes]);

  const counts = useMemo(() => {
    const c = { high: 0, medium: 0, low: 0, none: 0, total: items.length };
    for (const i of items) {
      const k = i.severity.toLowerCase() as Severity;
      if (k in c) (c as Record<Severity, number>)[k]++;
    }
    return c;
  }, [items]);

  const filtered = filter === "all" ? items : items.filter((i) => i.severity.toLowerCase() === filter);

  const reviewQueue = useMemo(() => {
    const reconcilable = filtered.filter((i) => i.diff_index >= 0);
    return reconcilable.length > 0 ? reconcilable : filtered;
  }, [filtered]);

  useEffect(() => {
    setFocusIdx(0);
    setPendingFocusDiff(null);
  }, [comparisonId]);

  useEffect(() => {
    if (pendingFocusDiff != null) {
      const qi = reviewQueue.findIndex((r) => r.diff_index === pendingFocusDiff);
      if (qi >= 0) {
        setFocusIdx(qi);
        setPendingFocusDiff(null);
      }
      return;
    }
    setFocusIdx(0);
  }, [filter, reviewQueue, pendingFocusDiff]);

  useEffect(() => {
    if (focusIdx >= reviewQueue.length) setFocusIdx(Math.max(0, reviewQueue.length - 1));
  }, [reviewQueue.length, focusIdx]);

  const focused = reviewQueue[focusIdx] ?? null;

  useEffect(() => {
    if (focused && focused.diff_index >= 0) onJumpToDiff(focused.diff_index);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focused?.diff_index]);

  const reconcilable = useMemo(() => items.filter((i) => i.diff_index >= 0), [items]);

  const decisionCounts = useMemo(() => {
    let accepted = 0;
    let rejected = 0;
    let edited = 0;
    for (const it of reconcilable) {
      const d = decisions[it.diff_index];
      if (d?.action === "accept") accepted++;
      else if (d?.action === "reject") rejected++;
      else if (d?.action === "edit") edited++;
    }
    return {
      accepted,
      rejected,
      edited,
      decided: accepted + rejected + edited,
      undecided: reconcilable.length - accepted - rejected - edited,
    };
  }, [reconcilable, decisions]);

  const allDecided = reconcilable.length === 0 || decisionCounts.undecided === 0;
  const progressPct =
    reconcilable.length === 0
      ? 100
      : Math.round((decisionCounts.decided / reconcilable.length) * 100);

  const highRiskTitles = useMemo(
    () => items.filter((i) => i.severity.toLowerCase() === "high").slice(0, 3),
    [items],
  );

  const clauseGroups = useMemo(() => {
    const map = new Map<string, number>();
    for (const it of items) {
      const key = (it.clause_ref || "Unclassified").trim() || "Unclassified";
      map.set(key, (map.get(key) || 0) + 1);
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
  }, [items]);

  const decideAndAdvance = (diffIndex: number, d: VendorHunkDecision) => {
    setEditingIndex(null);
    const nextDecisions = { ...decisions, [diffIndex]: d };
    setDecisions(nextDecisions);
    let nextIdx = focusIdx;
    for (let offset = 1; offset <= reviewQueue.length; offset++) {
      const i = (focusIdx + offset) % reviewQueue.length;
      const it = reviewQueue[i];
      if (!it || it.diff_index < 0) continue;
      if (!nextDecisions[it.diff_index]) {
        nextIdx = i;
        break;
      }
      if (offset === reviewQueue.length) {
        nextIdx = Math.min(focusIdx + 1, Math.max(0, reviewQueue.length - 1));
      }
    }
    setFocusIdx(nextIdx);
  };

  const setAll = (action: "accept" | "reject") =>
    setDecisions(
      Object.fromEntries(reconcilable.map((it) => [it.diff_index, { action } as VendorHunkDecision])),
    );

  const clearDecisions = () => {
    setDecisions({});
    setEditDrafts({});
    setEditingIndex(null);
  };

  const startEdit = (item: NegotiationChangeItem) => {
    const idx = item.diff_index;
    setEditingIndex(idx);
    setEditDrafts((prev) => ({
      ...prev,
      [idx]:
        prev[idx] ??
        (decisions[idx]?.action === "edit" ? decisions[idx].text : item.new_text || item.old_text || ""),
    }));
  };

  const saveEdit = (diffIndex: number) => {
    const text = (editDrafts[diffIndex] ?? "").trim();
    if (!text) {
      setSaveError("Edited text cannot be empty.");
      return;
    }
    decideAndAdvance(diffIndex, { action: "edit", text });
  };

  const handleSave = async () => {
    if (!onSaveVersion) return;
    if (!allDecided) {
      setSaveError(
        `Review all ${reconcilable.length} changes before saving (${decisionCounts.undecided} still open).`,
      );
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await onSaveVersion(decisions);
      setDecisions({});
      setEditDrafts({});
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Failed to save version");
    } finally {
      setSaving(false);
    }
  };

  const stepFocus = (delta: number) => {
    if (reviewQueue.length === 0) return;
    setFocusIdx((cur) => (cur + delta + reviewQueue.length) % reviewQueue.length);
    setEditingIndex(null);
  };

  if (!changes || !changes.comparison_id) {
    return (
      <div className="border border-separator/40 rounded-lg bg-bg p-6 text-center">
        <div className="text-sm font-medium text-label">No analysis yet</div>
        <div className="text-xs text-label-secondary mt-1.5 leading-relaxed max-w-xs mx-auto">
          Upload the vendor return and LegalOS will build a counsel issues list — severity,
          rationale, and recommended position for each change.
        </div>
      </div>
    );
  }

  return (
    <div className="border border-separator/40 rounded-lg bg-bg flex flex-col overflow-hidden h-full min-h-0">
      {/* Header + triage */}
      <div className="px-4 py-3 border-b border-separator/30 bg-bg-secondary shrink-0">
        <div className="flex items-start justify-between gap-2 flex-wrap mb-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-semibold text-label tracking-tight">Counsel issues list</h3>
              <Badge className="bg-accent/10 text-accent border-accent/20 text-[10px]">
                AI analysis
              </Badge>
            </div>
            <p className="text-xs text-label-secondary mt-0.5">
              v{changes.from_version_number} → v{changes.to_version_number}
              {" · "}
              {counts.total} material change{counts.total === 1 ? "" : "s"}
            </p>
          </div>
          {reviewQueue.length > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-label-secondary tabular-nums">
                {Math.min(focusIdx + 1, reviewQueue.length)} / {reviewQueue.length}
              </span>
              <Button size="sm" variant="secondary" onClick={() => stepFocus(-1)} title="Previous">
                ↑
              </Button>
              <Button size="sm" variant="secondary" onClick={() => stepFocus(1)} title="Next">
                ↓
              </Button>
            </div>
          )}
        </div>

        {/* Risk heat strip */}
        <div className="flex h-1.5 rounded-full overflow-hidden bg-separator/30 mb-2.5" aria-hidden>
          {counts.high > 0 && (
            <div className="bg-red-500" style={{ width: `${(counts.high / Math.max(counts.total, 1)) * 100}%` }} />
          )}
          {counts.medium > 0 && (
            <div
              className="bg-amber-500"
              style={{ width: `${(counts.medium / Math.max(counts.total, 1)) * 100}%` }}
            />
          )}
          {counts.low > 0 && (
            <div
              className="bg-blue-500"
              style={{ width: `${(counts.low / Math.max(counts.total, 1)) * 100}%` }}
            />
          )}
        </div>

        {/* Review progress */}
        {canAct && onSaveVersion && reconcilable.length > 0 && (
          <div className="mb-2.5">
            <div className="flex items-center justify-between text-[11px] text-label-secondary mb-1">
              <span>Review progress</span>
              <span className="tabular-nums font-medium text-label">
                {decisionCounts.decided}/{reconcilable.length} · {progressPct}%
              </span>
            </div>
            <div className="h-1 rounded-full bg-separator/30 overflow-hidden">
              <div
                className="h-full bg-accent transition-[width] duration-300 ease-out"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
        )}

        {/* Collapsible counsel brief */}
        <button
          type="button"
          onClick={() => setBriefOpen((v) => !v)}
          className="w-full flex items-center justify-between text-left text-[11px] font-semibold uppercase tracking-wide text-label-secondary mb-1.5"
        >
          <span>Negotiation brief</span>
          <span className="text-label-tertiary font-normal normal-case tracking-normal">
            {briefOpen ? "Hide" : "Show"}
          </span>
        </button>
        {briefOpen && (
          <div className="rounded-md border border-separator/40 bg-bg px-3 py-2.5 mb-2.5 space-y-2 animate-fade-in">
            <p className="text-xs text-label leading-relaxed">
              {changes.executive_summary ||
                changes.summary_report ||
                "Compare each vendor delta against your legal position, then accept, hold, or propose alternate wording."}
            </p>
            {highRiskTitles.length > 0 && (
              <div>
                <div className="text-[10px] font-semibold text-error uppercase tracking-wide mb-1">
                  Escalate first
                </div>
                <ul className="space-y-1">
                  {highRiskTitles.map((it) => (
                    <li key={it.diff_index} className="flex items-start gap-1.5 text-xs text-label">
                      <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                      <button
                        type="button"
                        className="text-left hover:text-accent transition-colors"
                        onClick={() => {
                          setFilter("high");
                          setPendingFocusDiff(it.diff_index);
                          if (it.diff_index >= 0) onJumpToDiff(it.diff_index);
                        }}
                      >
                        {it.clause_ref ? `§ ${it.clause_ref} — ` : ""}
                        {it.title}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {clauseGroups.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-0.5">
                {clauseGroups.map(([name, n]) => (
                  <span
                    key={name}
                    className="text-[10px] px-1.5 py-0.5 rounded border border-separator/40 bg-bg-secondary text-label-secondary"
                    title={`${n} change(s) near this clause`}
                  >
                    {name.length > 28 ? `${name.slice(0, 26)}…` : name}
                    <span className="text-label-tertiary ml-1">{n}</span>
                  </span>
                ))}
              </div>
            )}
            {(changes.risk_commentary?.length ?? 0) > 0 && (
              <div className="pt-1 border-t border-separator/30">
                <div className="text-[10px] font-semibold text-label-secondary uppercase tracking-wide mb-1">
                  Cross-cutting risks
                </div>
                <ul className="space-y-1.5">
                  {changes.risk_commentary!.slice(0, 3).map((flag, i) => (
                    <li key={i} className="text-[11px] text-label-secondary leading-snug">
                      <Badge className={classNames(riskColor(flag.severity), "mr-1.5 align-middle")}>
                        {flag.severity}
                      </Badge>
                      {flag.rationale || flag.excerpt}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <div className="flex gap-1 flex-wrap">
          <FilterChip active={filter === "all"} onClick={() => setFilter("all")}>
            All <span className="opacity-70 ml-1">{counts.total}</span>
          </FilterChip>
          <FilterChip active={filter === "high"} onClick={() => setFilter("high")} dotClass="bg-red-500">
            High <span className="opacity-70 ml-1">{counts.high}</span>
          </FilterChip>
          <FilterChip
            active={filter === "medium"}
            onClick={() => setFilter("medium")}
            dotClass="bg-amber-500"
          >
            Medium <span className="opacity-70 ml-1">{counts.medium}</span>
          </FilterChip>
          <FilterChip active={filter === "low"} onClick={() => setFilter("low")} dotClass="bg-blue-500">
            Low <span className="opacity-70 ml-1">{counts.low}</span>
          </FilterChip>
        </div>

        {canAct && onSaveVersion && reconcilable.length > 0 && (
          <div className="flex items-center gap-2 mt-2 pt-2 border-t border-separator/40 flex-wrap">
            <span className="text-[11px] font-medium text-label-secondary">Bulk:</span>
            <button
              type="button"
              onClick={() => setAll("accept")}
              className="text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-2 py-0.5 hover:bg-emerald-100"
            >
              Accept all vendor
            </button>
            <button
              type="button"
              onClick={() => setAll("reject")}
              className="text-[11px] font-medium text-error bg-red-50 border border-error/20 rounded px-2 py-0.5 hover:bg-red-100"
            >
              Hold all legal
            </button>
            {decisionCounts.decided > 0 && (
              <button
                type="button"
                onClick={clearDecisions}
                className="text-[11px] text-label-secondary hover:underline ml-auto"
              >
                Clear
              </button>
            )}
          </div>
        )}
      </div>

      {focused && (
        <FocusedChangeCard
          item={focused}
          pageMeta={changePages?.get(focused.diff_index)}
          decision={decisions[focused.diff_index]}
          canAct={canAct && !!onSaveVersion && focused.diff_index >= 0}
          editing={editingIndex === focused.diff_index}
          editDraft={editDrafts[focused.diff_index] ?? ""}
          onEditDraft={(v) => setEditDrafts((prev) => ({ ...prev, [focused.diff_index]: v }))}
          onAccept={() => decideAndAdvance(focused.diff_index, { action: "accept" })}
          onReject={() => decideAndAdvance(focused.diff_index, { action: "reject" })}
          onStartEdit={() => startEdit(focused)}
          onCancelEdit={() => setEditingIndex(null)}
          onSaveEdit={() => saveEdit(focused.diff_index)}
          onJump={() => onJumpToDiff(focused.diff_index)}
        />
      )}

      {/* Compact issues navigator */}
      <div className="flex-1 overflow-auto divide-y divide-separator/30 min-h-0">
        {filtered.length === 0 ? (
          <div className="p-6 text-center text-sm text-label-secondary">
            No changes at this severity.
          </div>
        ) : (
          filtered.map((item, idx) => {
            const isFocused =
              focused != null &&
              reviewQueue[focusIdx]?.diff_index === item.diff_index &&
              reviewQueue[focusIdx] === item;
            const sev = item.severity.toLowerCase();
            const label = decisionLabel(decisions[item.diff_index]);
            const kind = changeKind(item);
            return (
              <button
                key={`${item.diff_index}-${idx}`}
                type="button"
                onClick={() => {
                  const qi = reviewQueue.findIndex((r) => r.diff_index === item.diff_index);
                  if (qi >= 0) setFocusIdx(qi);
                  else onJumpToDiff(item.diff_index);
                }}
                className={classNames(
                  "w-full text-left px-4 py-2.5 flex items-start gap-3 hover:bg-bg-secondary transition",
                  isFocused && "bg-accent/5 border-l-2 border-accent",
                )}
              >
                <span
                  className={classNames("mt-1.5 w-2 h-2 rounded-full flex-shrink-0", sevDot(sev))}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <Badge className={riskColor(sev)}>{sev.toUpperCase()}</Badge>
                    <span
                      className={classNames(
                        "text-[10px] font-medium rounded px-1.5 py-0.5 border",
                        kindClass(kind),
                      )}
                    >
                      {kindLabel(kind)}
                    </span>
                    {item.clause_ref && (
                      <span className="text-[10px] font-medium text-accent truncate max-w-[120px]">
                        § {item.clause_ref}
                      </span>
                    )}
                    {label ? (
                      <span
                        className={classNames(
                          "text-[10px] font-semibold rounded px-1.5 py-0.5",
                          decisions[item.diff_index]?.action === "accept" &&
                            "text-emerald-700 bg-emerald-100",
                          decisions[item.diff_index]?.action === "reject" &&
                            "text-error bg-red-100",
                          decisions[item.diff_index]?.action === "edit" &&
                            "text-amber-800 bg-amber-100",
                        )}
                      >
                        {label}
                      </span>
                    ) : item.diff_index >= 0 ? (
                      <span className="text-[10px] font-medium text-label-tertiary bg-bg-secondary rounded px-1.5 py-0.5">
                        Needs decision
                      </span>
                    ) : null}
                  </div>
                  <div className="text-sm font-medium text-label truncate mt-0.5">{item.title}</div>
                  <p className="text-xs text-label-secondary mt-0.5 line-clamp-1">
                    {item.change_summary || item.impact || item.rationale}
                  </p>
                </div>
              </button>
            );
          })
        )}
      </div>

      {canAct && onSaveVersion && reconcilable.length > 0 && (
        <div className="border-t border-separator/40 bg-bg px-4 py-3 sticky bottom-0 shrink-0">
          {saveError && <p className="text-xs text-error mb-2">{saveError}</p>}
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] text-label-secondary leading-tight">
              <span className="text-emerald-700 font-medium">{decisionCounts.accepted} accepted</span>
              {" · "}
              <span className="text-error font-medium">{decisionCounts.rejected} held</span>
              {" · "}
              <span className="text-amber-800 font-medium">{decisionCounts.edited} alternate</span>
              {decisionCounts.undecided > 0 && (
                <>
                  {" · "}
                  <span className="text-label-tertiary">{decisionCounts.undecided} open</span>
                </>
              )}
              <div className="text-label-tertiary mt-0.5">
                {allDecided
                  ? "All issues decided — save a new legal redline."
                  : `Decide every change (${decisionCounts.undecided} left) before saving.`}
              </div>
            </div>
            <Button size="sm" disabled={busy || saving || !allDecided} onClick={handleSave}>
              {saving ? "Saving…" : "Save redline version"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function FocusedChangeCard({
  item,
  pageMeta,
  decision,
  canAct,
  editing,
  editDraft,
  onEditDraft,
  onAccept,
  onReject,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onJump,
}: {
  item: NegotiationChangeItem;
  pageMeta?: { page: number; line: number; severity: string };
  decision?: VendorHunkDecision;
  canAct: boolean;
  editing: boolean;
  editDraft: string;
  onEditDraft: (v: string) => void;
  onAccept: () => void;
  onReject: () => void;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onSaveEdit: () => void;
  onJump: () => void;
}) {
  const sev = item.severity.toLowerCase();
  const kind = changeKind(item);
  const rec = inferRecommendation(item);

  return (
    <div className="px-4 py-3 border-b border-separator/40 bg-bg space-y-3 shrink-0">
      <div className="flex items-start gap-2 flex-wrap">
        <Badge className={riskColor(sev)}>{sev.toUpperCase()}</Badge>
        <span className={classNames("text-[10px] font-medium rounded px-1.5 py-0.5 border", kindClass(kind))}>
          {kindLabel(kind)}
        </span>
        {item.clause_ref && (
          <span className="text-[10px] font-medium text-accent bg-accent/10 border border-accent/20 rounded px-1.5 py-0.5">
            § {item.clause_ref}
          </span>
        )}
        {pageMeta && (
          <span className="text-[10px] font-medium text-label-secondary bg-bg-secondary border border-separator/40 rounded px-1.5 py-0.5">
            p.{pageMeta.page} · L{pageMeta.line}
          </span>
        )}
        <span className="text-sm font-semibold text-label flex-1 min-w-0">{item.title}</span>
        {decisionLabel(decision) && (
          <span
            className={classNames(
              "text-[10px] font-semibold rounded px-1.5 py-0.5",
              decision?.action === "accept" && "text-emerald-700 bg-emerald-100",
              decision?.action === "reject" && "text-error bg-red-100",
              decision?.action === "edit" && "text-amber-800 bg-amber-100",
            )}
          >
            {decisionLabel(decision)}
          </span>
        )}
      </div>

      {item.change_summary && (
        <p className="text-xs font-medium text-label leading-relaxed">{item.change_summary}</p>
      )}

      {(item.rationale || item.impact) && (
        <div className="rounded-md border border-separator/40 bg-bg-secondary/80 px-2.5 py-2">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-label-secondary mb-1">
            Why this matters
          </div>
          <p className="text-xs text-label-secondary leading-relaxed">
            {item.rationale || item.impact}
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
        <div>
          <div className="text-[11px] font-semibold text-error mb-1">Legal position</div>
          <pre className="whitespace-pre-wrap bg-red-50/80 border-l-2 border-red-300 px-2 py-1.5 rounded font-mono text-label-secondary max-h-36 overflow-auto">
            {item.old_text || "— Not in legal version (vendor insert)"}
          </pre>
        </div>
        <div>
          <div className="text-[11px] font-semibold text-emerald-700 mb-1">Vendor mark-up</div>
          <pre className="whitespace-pre-wrap bg-emerald-50/80 border-l-2 border-emerald-300 px-2 py-1.5 rounded font-mono text-label-secondary max-h-36 overflow-auto">
            {item.new_text || "— Removed by vendor"}
          </pre>
        </div>
      </div>

      {item.suggested_action && (
        <div className="text-xs bg-accent/10 border border-accent/20 rounded-md px-2.5 py-2">
          <div className="flex items-center gap-2 flex-wrap mb-0.5">
            <span className="font-semibold text-accent">Recommended position</span>
            {rec && (
              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-bg border border-accent/20 text-accent">
                {rec === "accept" ? "Lean accept" : rec === "reject" ? "Lean hold" : "Lean revise"}
              </span>
            )}
          </div>
          <span className="text-label-secondary leading-relaxed">{item.suggested_action}</span>
        </div>
      )}

      {editing && (
        <div className="space-y-2">
          <Textarea
            label="Propose alternate wording"
            value={editDraft}
            onChange={(e) => onEditDraft(e.target.value)}
            rows={4}
            className="text-xs font-mono"
          />
          <div className="flex gap-2">
            <Button size="sm" onClick={onSaveEdit}>
              Save alternate & next
            </Button>
            <Button size="sm" variant="secondary" onClick={onCancelEdit}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {!editing && (
        <div className="flex items-center gap-2 flex-wrap">
          <Button size="sm" variant="secondary" onClick={onJump}>
            Jump to document →
          </Button>
          {canAct && (
            <>
              <button
                type="button"
                onClick={onAccept}
                className={classNames(
                  "text-xs px-2.5 py-1.5 font-medium rounded-md border transition",
                  decision?.action === "accept"
                    ? "bg-emerald-600 text-white border-emerald-600"
                    : "bg-bg text-emerald-700 border-emerald-200 hover:bg-emerald-50",
                  rec === "accept" && decision?.action !== "accept" && "ring-1 ring-emerald-400/50",
                )}
                title="Accept vendor language in the next redline"
              >
                Accept vendor
              </button>
              <button
                type="button"
                onClick={onReject}
                className={classNames(
                  "text-xs px-2.5 py-1.5 font-medium rounded-md border transition",
                  decision?.action === "reject"
                    ? "bg-red-600 text-white border-red-600"
                    : "bg-bg text-error border-error/20 hover:bg-red-50",
                  rec === "reject" && decision?.action !== "reject" && "ring-1 ring-red-400/50",
                )}
                title="Keep legal version wording"
              >
                Hold legal
              </button>
              <button
                type="button"
                onClick={onStartEdit}
                className={classNames(
                  "text-xs px-2.5 py-1.5 font-medium rounded-md border transition",
                  decision?.action === "edit"
                    ? "bg-amber-600 text-white border-amber-600"
                    : "bg-bg text-amber-800 border-amber-200 hover:bg-amber-50",
                  rec === "edit" && decision?.action !== "edit" && "ring-1 ring-amber-400/50",
                )}
              >
                Propose alternate…
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function FilterChip({
  active,
  children,
  onClick,
  dotClass,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
  dotClass?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={classNames(
        "inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition",
        active
          ? "bg-accent text-white border-accent"
          : "bg-bg text-label-secondary border-separator/40 hover:border-separator/60",
      )}
    >
      {dotClass && <span className={classNames("w-1.5 h-1.5 rounded-full", dotClass)} />}
      {children}
    </button>
  );
}
