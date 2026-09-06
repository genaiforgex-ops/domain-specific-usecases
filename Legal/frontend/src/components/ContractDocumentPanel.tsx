import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Icon } from "@/components/Icons";
import { Button } from "@/components/ui/Button";
import { classNames } from "@/lib/utils";

const LINES_PER_PAGE = 45;

function paginate(text: string): string[] {
  const lines = text.split("\n");
  const pages: string[] = [];
  for (let i = 0; i < lines.length; i += LINES_PER_PAGE) {
    pages.push(lines.slice(i, i + LINES_PER_PAGE).join("\n"));
  }
  return pages.length > 0 ? pages : [""];
}

export function ContractDocumentPanel({
  text,
  filename,
  status,
  onSelection,
  previewText,
  highlightQuery,
}: {
  text: string;
  filename: string;
  status?: string;
  onSelection?: (selected: string) => void;
  /** When set, show proposed document instead of current (for redline preview). */
  previewText?: string | null;
  /** Jump/highlight excerpt in document viewer. */
  highlightQuery?: string | null;
}) {
  const displayText = previewText ?? text;
  const pages = useMemo(() => paginate(displayText), [displayText]);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [visiblePage, setVisiblePage] = useState(1);
  const [query, setQuery] = useState("");
  const [selectionHint, setSelectionHint] = useState<string | null>(null);

  useEffect(() => {
    if (highlightQuery?.trim()) {
      const snippet = highlightQuery.trim().slice(0, 80);
      setQuery(snippet);
    }
  }, [highlightQuery]);

  const scrollToPage = useCallback((page: number) => {
    const el = pageRefs.current[Math.max(0, page - 1)];
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
    setVisiblePage(page);
  }, []);

  function handleMouseUp() {
    const sel = window.getSelection()?.toString().trim();
    if (sel && sel.length > 10) {
      setSelectionHint(sel.slice(0, 80) + (sel.length > 80 ? "…" : ""));
      onSelection?.(sel);
    }
  }

  function renderHighlights(s: string): React.ReactNode {
    const q = query.trim();
    if (!q) return s;
    try {
      const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
      return s.split(re).map((p, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="bg-amber-200 text-label rounded-sm px-0.5">
            {p}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      );
    } catch {
      return s;
    }
  }

  return (
    <div className="border border-separator/40 rounded-xl bg-bg flex flex-col overflow-hidden h-full shadow-card">
      <div className="px-4 py-3 border-b border-separator/30 flex items-center gap-3 bg-bg-secondary flex-shrink-0">
        <div className="rounded-lg bg-accent/10 text-accent p-2">
          <Icon.Documents className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-label truncate">{filename}</div>
          <div className="text-[11px] text-label-secondary flex items-center gap-1.5 mt-0.5">
            <span>
              Page {visiblePage} / {pages.length}
            </span>
            {status && (
              <>
                <span>·</span>
                <span className="capitalize">{status.replace(/_/g, " ")}</span>
              </>
            )}
            {previewText && (
              <>
                <span>·</span>
                <span className="text-amber-700 font-medium">Proposed preview</span>
              </>
            )}
          </div>
        </div>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search document…"
          className="w-36 text-xs px-2.5 py-1.5 border border-separator/40 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/60"
        />
        <Button size="sm" variant="secondary" onClick={() => scrollToPage(Math.max(1, visiblePage - 1))}>
          ↑
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => scrollToPage(Math.min(pages.length, visiblePage + 1))}
        >
          ↓
        </Button>
      </div>

      {selectionHint && !previewText && (
        <div className="px-4 py-2 bg-accent/10 border-b border-accent/20 text-xs text-accent flex items-center gap-2">
          <Icon.Sparkles className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">
            Selection captured — use it in the AI editor panel on the right.
          </span>
          <button
            type="button"
            className="ml-auto text-accent hover:text-accent underline shrink-0"
            onClick={() => setSelectionHint(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      <div
        ref={scrollerRef}
        className="flex-1 overflow-auto bg-bg-secondary/80 scroll-smooth min-h-0"
        onMouseUp={handleMouseUp}
      >
        <div className="flex flex-col items-center gap-5 py-6 px-4">
          {pages.map((page, i) => (
            <div
              key={i}
              ref={(el) => {
                pageRefs.current[i] = el;
              }}
              className={classNames(
                "relative bg-bg shadow-md w-full max-w-2xl px-12 py-10 rounded-sm border transition",
                previewText ? "border-warning/20 ring-1 ring-amber-100" : "border-separator/30",
              )}
            >
              <div className="absolute -left-10 top-3 text-[10px] font-mono text-label-tertiary select-none">
                {i + 1}
              </div>
              <pre className="text-[13px] font-serif leading-relaxed whitespace-pre-wrap text-label selection:bg-accent/20 selection:text-label">
                {renderHighlights(page)}
              </pre>
              <div className="text-[10px] text-label-tertiary text-center mt-8 pt-4 border-t border-separator/30">
                — {i + 1} of {pages.length} —
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="px-4 py-2 border-t border-separator/30 bg-bg-secondary text-[11px] text-label-secondary flex items-center justify-between flex-shrink-0">
        <span>Highlight text to scope an AI edit · Scroll to navigate</span>
        <div className="flex items-center gap-1.5">
          <span>Go to</span>
          <input
            type="number"
            min={1}
            max={pages.length}
            value={visiblePage}
            onChange={(e) => {
              const p = Number(e.target.value);
              if (p >= 1 && p <= pages.length) scrollToPage(p);
            }}
            className="w-11 text-center px-1 py-0.5 border border-separator/40 rounded text-label-secondary"
          />
        </div>
      </div>
    </div>
  );
}
