import { forwardRef, useImperativeHandle, useRef } from "react";

import type { DiffBlock, DiffToken } from "@/types";

export interface DiffViewHandle {
  scrollToIndex: (index: number) => void;
}

interface Props {
  v1Label: string;
  v2Label: string;
  blocks: DiffBlock[];
  height?: number;
}

/** Scroll a child into view inside its own overflow container (not the window). */
function scrollChildIntoContainer(container: HTMLElement, el: HTMLElement) {
  const cRect = container.getBoundingClientRect();
  const eRect = el.getBoundingClientRect();
  const target =
    eRect.top - cRect.top + container.scrollTop - container.clientHeight / 2 + el.clientHeight / 2;
  container.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
}

export const DiffView = forwardRef<DiffViewHandle, Props>(function DiffView(
  { v1Label, v2Label, blocks, height = 500 },
  ref,
) {
  const v1Ref = useRef<HTMLDivElement>(null);
  const v2Ref = useRef<HTMLDivElement>(null);

  useImperativeHandle(ref, () => ({
    scrollToIndex: (index: number) => {
      // Align both version panes to the same change so you can compare side-by-side.
      [v1Ref.current, v2Ref.current].forEach((container) => {
        if (!container) return;
        const el = container.querySelector<HTMLElement>(`[data-diff-index="${index}"]`);
        if (!el) return;
        scrollChildIntoContainer(container, el);
        el.classList.add("ring-2", "ring-accent");
        window.setTimeout(() => el.classList.remove("ring-2", "ring-accent"), 1800);
      });
    },
  }));

  return (
    <div>
      <Legend />
      <div className="grid grid-cols-2 gap-3 text-xs font-mono">
        <DiffColumn label={v1Label} blocks={blocks} side="v1" innerRef={v1Ref} height={height} />
        <DiffColumn label={v2Label} blocks={blocks} side="v2" innerRef={v2Ref} height={height} />
      </div>
    </div>
  );
});

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-3 mb-2 text-[11px] text-label-secondary">
      <span className="inline-flex items-center gap-1">
        <span className="inline-block w-3 h-3 rounded-sm bg-emerald-100 border border-emerald-400" />
        Added
      </span>
      <span className="inline-flex items-center gap-1">
        <span className="inline-block w-3 h-3 rounded-sm bg-red-100 border border-red-400" />
        Removed
      </span>
      <span className="inline-flex items-center gap-1">
        <span className="inline-block w-3 h-3 rounded-sm bg-amber-100 border border-amber-400" />
        Modified
      </span>
      <span className="text-label-tertiary">— modified lines highlight the exact words that changed</span>
    </div>
  );
}

// Block-level marker: a left border + tint identifying the kind of change for the whole region.
function blockClass(kind: string, side: "v1" | "v2"): string {
  if (kind === "equal") return "";
  if (kind === "insert") return side === "v2" ? "bg-emerald-50/60 border-l-2 border-emerald-400" : "";
  if (kind === "delete") return side === "v1" ? "bg-red-50/60 border-l-2 border-red-400" : "";
  if (kind === "replace") return "bg-amber-50/60 border-l-2 border-amber-400";
  return "";
}

// Word-level rendering for "replace" blocks: only the changed tokens are tinted.
function renderTokens(tokens: DiffToken[]) {
  return tokens.map((t, i) => {
    if (t.op === "equal") return <span key={i}>{t.text}</span>;
    if (t.op === "delete")
      return (
        <span key={i} className="bg-red-200/70 text-red-800 line-through rounded-sm">
          {t.text}
        </span>
      );
    // insert
    return (
      <span key={i} className="bg-emerald-200/70 text-emerald-800 rounded-sm">
        {t.text}
      </span>
    );
  });
}

function DiffColumn({
  label,
  blocks,
  side,
  innerRef,
  height,
}: {
  label: string;
  blocks: DiffBlock[];
  side: "v1" | "v2";
  innerRef: React.RefObject<HTMLDivElement>;
  height: number;
}) {
  return (
    <div className="flex flex-col">
      <div className="text-xs font-semibold text-label-secondary mb-1 px-1">{label}</div>
      <div
        ref={innerRef as React.RefObject<HTMLDivElement>}
        className="border border-separator/40 rounded bg-bg overflow-auto"
        style={{ height }}
      >
        {blocks.map((b, i) => {
          const text = side === "v1" ? b.v1 : b.v2;
          const tokens = side === "v1" ? b.v1_tokens : b.v2_tokens;
          const isReplaceWithTokens = b.kind === "replace" && tokens && tokens.length > 0;
          const lineThrough = b.kind === "delete" && side === "v1" ? "line-through" : "";

          // Always render a row for every block on both sides so Prev/Next can
          // scroll *both* panes to the same change (inserts/deletes used to
          // omit the empty side and leave that pane at the top).
          if (!text && b.kind !== "equal") {
            const placeholder =
              b.kind === "insert" && side === "v1"
                ? "(not in this version)"
                : b.kind === "delete" && side === "v2"
                  ? "(removed in other version)"
                  : "\u00a0";
            return (
              <div
                key={i}
                data-diff-index={i}
                className={`whitespace-pre-wrap px-2 py-1 min-h-[1.75em] text-label-tertiary italic ${blockClass(b.kind, side)}`}
              >
                {placeholder}
              </div>
            );
          }

          return (
            <div
              key={i}
              data-diff-index={i}
              className={`whitespace-pre-wrap px-2 py-1 transition ${lineThrough} ${blockClass(b.kind, side)}`}
            >
              {isReplaceWithTokens ? renderTokens(tokens!) : text || " "}
            </div>
          );
        })}
      </div>
    </div>
  );
}
