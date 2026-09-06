import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Tabs } from "@/components/ui/Tabs";
import { Textarea } from "@/components/ui/Textarea";
import { api } from "@/lib/api";
import { classNames, formatDate, statusColor } from "@/lib/utils";
import type { RegulatoryUpdate } from "@/types";

import { NewsFullText } from "./NewsFullText";

type DetailTabId = "summary" | "analysis" | "fulltext" | "actions";

const PANEL_WIDTH = 420;
const CLOSE_MS = 280;

function RelevanceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-label-secondary">Relevance</span>
        <span className="font-medium text-label tabular-nums">{pct}%</span>
      </div>
      <div className="h-2 rounded-full bg-bg-secondary overflow-hidden">
        <div
          className="h-full rounded-full bg-accent transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function TriageActions({
  update,
  onChanged,
}: {
  update: RegulatoryUpdate;
  onChanged: () => void;
}) {
  const [note, setNote] = useState(update.impact_note || "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setNote(update.impact_note || "");
  }, [update.id, update.impact_note]);

  async function setStatus(status: string) {
    setBusy(true);
    try {
      await api.triageNews(update.id, status, note || undefined);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <Textarea
        rows={4}
        label="Impact note"
        placeholder="Describe the business impact of this update (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <div className="flex gap-2 flex-wrap">
        <Button size="sm" disabled={busy} onClick={() => void setStatus("action_required")}>
          Action required
        </Button>
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => void setStatus("for_information")}>
          For information
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => void setStatus("not_relevant")}>
          Not relevant
        </Button>
      </div>
    </div>
  );
}

function MetadataRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 border-b border-separator/20 text-sm">
      <span className="text-label-secondary shrink-0">{label}</span>
      <span className="text-label text-right">{value}</span>
    </div>
  );
}

export function NewsDetailPanel({
  item,
  canFull,
  onClose,
  onChanged,
}: {
  item: RegulatoryUpdate;
  canFull: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [tab, setTab] = useState<DetailTabId>("summary");
  const [closing, setClosing] = useState(false);

  const handleClose = useCallback(() => {
    if (closing) return;
    setClosing(true);
    window.setTimeout(() => onClose(), CLOSE_MS);
  }, [closing, onClose]);

  useEffect(() => {
    setTab("summary");
    setClosing(false);
  }, [item.id]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") handleClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [handleClose]);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  const detailTabs = [
    { id: "summary", label: "Summary" },
    { id: "analysis", label: "AI Analysis" },
    { id: "fulltext", label: "Full Text" },
    ...(canFull ? [{ id: "actions", label: "Actions" }] : []),
  ];

  return (
    <>
      <div
        className={classNames(
          "fixed inset-0 z-40 bg-black/25 backdrop-blur-[1px]",
          closing ? "animate-fade-in opacity-0 transition-opacity duration-slow" : "animate-fade-in",
        )}
        onClick={handleClose}
        aria-hidden="true"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Regulatory update detail"
        style={{ width: `min(100vw, ${PANEL_WIDTH}px)` }}
        className={classNames(
          "fixed inset-y-0 right-0 z-50 flex flex-col bg-bg border-l border-separator/40 shadow-xl",
          closing ? "animate-slide-out-right" : "animate-slide-in-right",
        )}
      >
        <div className="shrink-0 px-4 py-3 border-b border-separator/40 flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <Badge className="bg-bg-secondary text-label-secondary border-separator/40 text-xs">
                {item.source}
              </Badge>
              {item.category && (
                <Badge className="bg-accent/10 text-accent border-accent/20 text-xs">{item.category}</Badge>
              )}
              <Badge className={classNames(statusColor(item.status), "text-xs")}>
                {item.status.replace(/_/g, " ")}
              </Badge>
            </div>
            <h2 className="text-base font-semibold text-label leading-snug">{item.title}</h2>
            <p className="text-xs text-label-tertiary mt-1">
              Published {formatDate(item.published_at)}
              {item.url && (
                <>
                  {" · "}
                  <a href={item.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                    View source
                  </a>
                </>
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            aria-label="Hide detail panel"
            title="Hide panel"
            className="shrink-0 w-8 h-8 flex items-center justify-center rounded-md text-label-secondary hover:bg-bg-secondary hover:text-label transition-colors"
          >
            ⟩
          </button>
        </div>

        <Tabs
          tabs={detailTabs}
          active={tab}
          onChange={(id) => setTab(id as DetailTabId)}
          className="shrink-0 px-4"
        />

        <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4">
          {tab === "summary" && (
            <div className="space-y-4 animate-fade-in">
              <p className="text-sm text-label leading-relaxed">{item.summary}</p>
              <RelevanceBar score={item.relevance_score} />
              <div className="rounded-lg border border-separator/30 bg-bg-secondary/50 p-3 space-y-0">
                <MetadataRow label="Status" value={item.status.replace(/_/g, " ")} />
                <MetadataRow label="Regulator" value={item.source} />
                <MetadataRow label="Category" value={item.category || "—"} />
                <MetadataRow label="Published" value={formatDate(item.published_at)} />
                <MetadataRow label="Ingested" value={formatDate(item.ingested_at)} />
              </div>
            </div>
          )}

          {tab === "analysis" && (
            <div className="space-y-4 animate-fade-in">
              <RelevanceBar score={item.relevance_score} />
              {item.impact_note ? (
                <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-100 dark:border-amber-900/40 rounded-lg p-3">
                  <div className="text-xs font-semibold text-amber-700 dark:text-amber-400 mb-1">
                    Impact note
                  </div>
                  <p className="text-sm text-amber-900 dark:text-amber-200 leading-relaxed">{item.impact_note}</p>
                </div>
              ) : (
                <p className="text-sm text-label-tertiary">No impact note recorded yet.</p>
              )}
              {item.tags.length > 0 && (
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-label-secondary mb-2">
                    Topical tags
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {item.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full px-2.5 py-0.5 text-xs bg-bg-secondary text-label-secondary border border-separator/40"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <div className="rounded-lg border border-separator/30 bg-bg-secondary/50 p-3 space-y-0">
                <MetadataRow label="Category" value={item.category || "—"} />
                <MetadataRow label="Relevance" value={`${Math.round(item.relevance_score * 100)}%`} />
                <MetadataRow label="Source" value={item.source} />
              </div>
            </div>
          )}

          {tab === "fulltext" && (
            <div className="animate-fade-in">
              {item.full_text ? (
                <NewsFullText text={item.full_text} url={item.url} />
              ) : (
                <p className="text-sm text-label-tertiary">
                  Full text not available for this update.{" "}
                  {item.url && (
                    <a href={item.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                      Read at source
                    </a>
                  )}
                </p>
              )}
            </div>
          )}

          {tab === "actions" && canFull && (
            <div className="animate-fade-in">
              <p className="text-sm text-label-secondary mb-4">
                Classify this update and add an impact note for your team.
              </p>
              <TriageActions update={item} onChanged={onChanged} />
            </div>
          )}

          {tab === "actions" && !canFull && (
            <div className="animate-fade-in">
              <p className="text-sm text-label-secondary">
                Current status:{" "}
                <span className="font-medium text-label">{item.status.replace(/_/g, " ")}</span>
              </p>
              {item.impact_note && (
                <div className="mt-3 bg-amber-50 border border-amber-100 rounded-lg p-3 text-sm">
                  {item.impact_note}
                </div>
              )}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
