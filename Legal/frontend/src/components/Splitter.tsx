import { useCallback, useEffect, useRef, useState } from "react";

import { classNames } from "@/lib/utils";

interface Props {
  /** Children must be exactly two elements. */
  children: [React.ReactNode, React.ReactNode];
  /** Initial split, 0–100 (percent of first pane). */
  initial?: number;
  /** Minimum percent for either pane. */
  min?: number;
  /** Orientation; default horizontal (left + right). */
  orientation?: "horizontal" | "vertical";
  className?: string;
  storageKey?: string;
}

export function Splitter({
  children,
  initial = 50,
  min = 15,
  orientation = "horizontal",
  className,
  storageKey,
}: Props) {
  const [first, second] = children;
  const containerRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const [pct, setPct] = useState<number>(() => {
    if (storageKey) {
      const saved = Number(localStorage.getItem(`splitter:${storageKey}`));
      if (Number.isFinite(saved) && saved >= min && saved <= 100 - min) return saved;
    }
    return initial;
  });

  useEffect(() => {
    if (storageKey) localStorage.setItem(`splitter:${storageKey}`, String(pct));
  }, [pct, storageKey]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    document.body.style.cursor = orientation === "horizontal" ? "col-resize" : "row-resize";
    document.body.style.userSelect = "none";
  }, [orientation]);

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!draggingRef.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const ratio =
        orientation === "horizontal"
          ? (e.clientX - rect.left) / rect.width
          : (e.clientY - rect.top) / rect.height;
      const next = Math.max(min, Math.min(100 - min, ratio * 100));
      setPct(next);
    },
    [min, orientation],
  );

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  const isHorizontal = orientation === "horizontal";

  return (
    <div
      ref={containerRef}
      className={classNames(
        "flex w-full h-full",
        isHorizontal ? "flex-row" : "flex-col",
        className,
      )}
    >
      <div
        style={{
          [isHorizontal ? "width" : "height"]: `${pct}%`,
        }}
        className="min-w-0 min-h-0 overflow-hidden"
      >
        {first}
      </div>
      <div
        role="separator"
        aria-orientation={orientation}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDoubleClick={() => setPct(initial)}
        className={classNames(
          "flex-shrink-0 bg-separator/40 hover:bg-accent/80 active:bg-accent transition-colors relative group",
          isHorizontal
            ? "w-1 cursor-col-resize mx-0.5"
            : "h-1 cursor-row-resize my-0.5",
        )}
      >
        <div
          className={classNames(
            "absolute opacity-0 group-hover:opacity-100 bg-accent transition-opacity",
            isHorizontal
              ? "left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-1 h-8 rounded"
              : "top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-1 w-8 rounded",
          )}
        />
      </div>
      <div
        style={{
          [isHorizontal ? "width" : "height"]: `${100 - pct}%`,
        }}
        className="min-w-0 min-h-0 overflow-hidden"
      >
        {second}
      </div>
    </div>
  );
}
