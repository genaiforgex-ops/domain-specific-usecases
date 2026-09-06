import { forwardRef, useImperativeHandle, useMemo, useRef } from "react";

import type { DiffViewHandle } from "@/components/DiffView";
import type { DiffBlock, DiffToken } from "@/types";

const LINES_PER_PAGE = 38;

interface Props {
  blocks: DiffBlock[];
  height?: number;
  /** Optional document name shown in the page header. */
  title?: string;
  /**
   * When provided, each individual change (insert/delete/replace) shows a small
   * "Revert" control that drops just that change, reverting it to the original
   * text. Only wire this up for editable text sources.
   */
  onDeleteChange?: (index: number) => void;
}

/**
 * A document-styled inline redline: renders the proposed document as paginated
 * pages (serif, page shadows) with additions highlighted green and deletions
 * shown as red strike-through — closer to a real Word/PDF redline than the
 * side-by-side column diff. Exposes `scrollToIndex` so callers can jump between
 * changes using the shared DiffViewHandle contract.
 */
export const RedlinePreview = forwardRef<DiffViewHandle, Props>(function RedlinePreview(
  { blocks, height = 420, title, onDeleteChange },
  ref,
) {
  const scrollerRef = useRef<HTMLDivElement>(null);

  useImperativeHandle(
    ref,
    () => ({
      scrollToIndex: (index: number) => {
        const el = scrollerRef.current?.querySelector<HTMLElement>(
          `[data-diff-index="${index}"]`,
        );
        if (!el) return;
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("ring-2", "ring-accent", "rounded-sm");
        setTimeout(() => el.classList.remove("ring-2", "ring-accent", "rounded-sm"), 1800);
      },
    }),
    [],
  );

  // Paginate while preserving each block's global index (used as data-diff-index).
  const pages = useMemo(() => {
    const withIndex = blocks.map((block, index) => ({ block, index }));
    const out: Array<Array<{ block: DiffBlock; index: number }>> = [];
    for (let i = 0; i < withIndex.length; i += LINES_PER_PAGE) {
      out.push(withIndex.slice(i, i + LINES_PER_PAGE));
    }
    return out.length > 0 ? out : [[]];
  }, [blocks]);

  return (
    <div
      ref={scrollerRef}
      className="overflow-auto bg-bg-secondary/80 rounded-lg border border-separator/40 scroll-smooth"
      style={{ height }}
    >
      <div className="flex flex-col items-center gap-5 py-6 px-4">
        {pages.map((page, p) => (
          <div
            key={p}
            className="relative bg-bg shadow-md w-full max-w-4xl px-12 py-10 rounded-sm border border-separator/30 overflow-x-auto"
          >
            {title && p === 0 && (
              <div className="text-[11px] uppercase tracking-wide text-label-tertiary mb-4">
                {title}
              </div>
            )}
            <div className="text-[13px] font-serif leading-relaxed text-label space-y-0.5">
              {page.map(({ block, index }) => (
                <BlockLine
                  key={index}
                  block={block}
                  index={index}
                  onDeleteChange={onDeleteChange}
                />
              ))}
            </div>
            <div className="text-[10px] text-label-tertiary text-center mt-8 pt-4 border-t border-separator/30">
              — {p + 1} of {pages.length} —
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});

function looksLikeMarkdownTableRow(line: string): boolean {
  const s = line.trim();
  if (!s.startsWith("|")) return false;
  return (s.match(/\|/g)?.length ?? 0) >= 2;
}

function BlockLine({
  block,
  index,
  onDeleteChange,
}: {
  block: DiffBlock;
  index: number;
  onDeleteChange?: (index: number) => void;
}) {
  const mono =
    looksLikeMarkdownTableRow(block.v1 || "") || looksLikeMarkdownTableRow(block.v2 || "");
  const textClass = mono
    ? "whitespace-pre font-mono text-[11px] leading-5 tracking-tight"
    : "whitespace-pre-wrap";

  if (block.kind === "equal") {
    return (
      <div data-diff-index={index} className={`${textClass} px-1`}>
        {block.v2 || "\u00a0"}
      </div>
    );
  }

  const revertButton = onDeleteChange ? (
    <button
      type="button"
      onClick={() => onDeleteChange(index)}
      title="Revert this change to the original"
      className="absolute -right-1 top-0 opacity-0 group-hover:opacity-100 focus:opacity-100 transition text-[10px] font-sans px-1.5 py-0.5 rounded bg-bg border border-separator/50 text-label-secondary hover:text-error hover:border-error/40 shadow-sm"
    >
      Revert
    </button>
  ) : null;

  if (block.kind === "insert") {
    return (
      <div
        data-diff-index={index}
        className={`group relative ${textClass} px-1 rounded-sm bg-emerald-100/70 border-l-2 border-emerald-400 pl-2 pr-14`}
      >
        {block.v2 || "\u00a0"}
        {revertButton}
      </div>
    );
  }

  if (block.kind === "delete") {
    return (
      <div
        data-diff-index={index}
        className={`group relative ${textClass} px-1 rounded-sm bg-red-100/60 border-l-2 border-red-400 pl-2 pr-14 text-red-800/80 line-through`}
      >
        {block.v1 || "\u00a0"}
        {revertButton}
      </div>
    );
  }

  // replace — show removed line struck through above the new line, with
  // word-level highlighting when tokens are available.
  return (
    <div
      data-diff-index={index}
      className="group relative rounded-sm border-l-2 border-amber-400 pl-2 pr-14 bg-amber-50/50"
    >
      <div className={`${textClass} px-1 text-red-800/70 line-through`}>
        {block.v1_tokens && block.v1_tokens.length > 0
          ? renderTokens(block.v1_tokens)
          : block.v1 || "\u00a0"}
      </div>
      <div className={`${textClass} px-1 text-emerald-900`}>
        {block.v2_tokens && block.v2_tokens.length > 0
          ? renderTokens(block.v2_tokens)
          : block.v2 || "\u00a0"}
      </div>
      {revertButton}
    </div>
  );
}

function renderTokens(tokens: DiffToken[]) {
  return tokens.map((t, i) => {
    if (t.op === "equal") return <span key={i}>{t.text}</span>;
    if (t.op === "delete")
      return (
        <span key={i} className="bg-red-200/70 text-red-800 line-through rounded-sm">
          {t.text}
        </span>
      );
    return (
      <span key={i} className="bg-emerald-200/70 text-emerald-900 rounded-sm">
        {t.text}
      </span>
    );
  });
}

/** Count additions/deletions across diff blocks for a summary badge. */
export function redlineStats(blocks: DiffBlock[]): { additions: number; deletions: number } {
  let additions = 0;
  let deletions = 0;
  for (const b of blocks) {
    if (b.kind === "insert") additions++;
    else if (b.kind === "delete") deletions++;
    else if (b.kind === "replace") {
      additions++;
      deletions++;
    }
  }
  return { additions, deletions };
}
