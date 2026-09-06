import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";

import { Icon } from "@/components/Icons";
import { classNames } from "@/lib/utils";

/** Three bouncing dots — universal "thinking" indicator. */
export function TypingDots() {
  return (
    <div className="flex gap-1 items-center py-2 px-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-2 h-2 rounded-full bg-label-tertiary animate-bounce"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </div>
  );
}

/** Incrementally reveal `text` to simulate streaming. Returns the visible slice. */
export function useTypewriter(text: string, speedMs = 14, enabled = true): string {
  const [displayed, setDisplayed] = useState(enabled ? "" : text);
  useEffect(() => {
    if (!enabled) {
      setDisplayed(text);
      return;
    }
    setDisplayed("");
    if (!text) return;
    let i = 0;
    const interval = setInterval(() => {
      i += 3; // 3 chars per tick for a snappy feel
      if (i >= text.length) {
        setDisplayed(text);
        clearInterval(interval);
      } else {
        setDisplayed(text.slice(0, i));
      }
    }, speedMs);
    return () => clearInterval(interval);
  }, [text, enabled, speedMs]);
  return displayed;
}

/** Group dated items into Today / Yesterday / Last 7 days / Earlier. */
export function groupByDate<T extends { created_at: string }>(
  items: T[],
): { label: string; items: T[] }[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterday = today - 86400000;
  const lastWeek = today - 7 * 86400000;
  const buckets: Record<string, T[]> = {
    Today: [],
    Yesterday: [],
    "Last 7 days": [],
    Earlier: [],
  };
  for (const it of items) {
    const t = new Date(it.created_at).getTime();
    if (t >= today) buckets.Today.push(it);
    else if (t >= yesterday) buckets.Yesterday.push(it);
    else if (t >= lastWeek) buckets["Last 7 days"].push(it);
    else buckets.Earlier.push(it);
  }
  return Object.entries(buckets)
    .filter(([, v]) => v.length > 0)
    .map(([label, items]) => ({ label, items }));
}

/** User avatar — circle with initials, brand colour. */
export function UserAvatar({ name }: { name: string }) {
  const initials = name
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <div className="w-8 h-8 rounded-full bg-accent text-white text-xs font-semibold flex items-center justify-center shrink-0">
      {initials || "?"}
    </div>
  );
}

/** AI avatar — gradient circle with sparkle icon. */
export function AIAvatar() {
  return (
    <div className="w-8 h-8 rounded-full bg-accent/15 text-accent flex items-center justify-center shrink-0">
      <Icon.Sparkles className="w-4 h-4" aria-hidden />
    </div>
  );
}

/** Auto-growing textarea that submits on Enter (Shift+Enter for newline). */
export function ChatInput({
  value,
  onChange,
  onSubmit,
  placeholder,
  busy,
  disabled,
  hint,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  placeholder?: string;
  busy?: boolean;
  disabled?: boolean;
  hint?: ReactNode;
}) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [value]);

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !busy && !disabled) onSubmit();
    }
  }

  return (
    <div className="px-4 md:px-8 py-3 border-t border-separator/40 bg-bg/95 backdrop-blur">
      <div className="max-w-3xl mx-auto">
        <div
          className={classNames(
            "relative rounded-2xl border bg-bg shadow-sm transition-all",
            "focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20",
            "border-separator/40",
          )}
        >
          <textarea
            ref={taRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={placeholder || "Ask anything…"}
            rows={1}
            disabled={disabled}
            className="block w-full resize-none rounded-2xl px-4 py-3 pr-14 text-sm bg-transparent focus:outline-none disabled:opacity-50"
            style={{ minHeight: 48 }}
          />
          <button
            type="button"
            onClick={onSubmit}
            disabled={busy || disabled || !value.trim()}
            className={classNames(
              "absolute right-2 bottom-2 min-w-tap min-h-tap w-11 h-11 rounded-xl flex items-center justify-center transition-all",
              value.trim() && !busy && !disabled
                ? "bg-accent text-white hover:opacity-90 hover:scale-105 shadow-sm"
                : "bg-bg-secondary text-label-tertiary cursor-not-allowed",
            )}
            aria-label={busy ? "Sending" : "Send"}
            title={busy ? "Sending…" : "Send (Enter)"}
          >
            {busy ? <Icon.Stop className="w-4 h-4" /> : <Icon.Send className="w-4 h-4" />}
          </button>
        </div>
        {hint && <div className="text-[11px] text-label-tertiary mt-1.5 text-center">{hint}</div>}
      </div>
    </div>
  );
}

/** Reusable "starter prompt" chip row for empty chat states. */
export function SuggestionChips({
  suggestions,
  onPick,
}: {
  suggestions: string[];
  onPick: (s: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
      {suggestions.map((s, i) => (
        <button
          key={s}
          onClick={() => onPick(s)}
          className="group text-left rounded-xl border border-separator/40 bg-bg hover:border-accent/40 hover:bg-accent/10 hover:shadow-sm px-4 py-3 transition-all animate-slide-up"
          style={{ animationDelay: `${i * 60}ms` }}
        >
          <span className="text-sm text-label group-hover:text-accent">{s}</span>
        </button>
      ))}
    </div>
  );
}

/** Smooth-scroll a ref's parent to bottom whenever a dep changes. */
export function useAutoScrollToBottom(deps: unknown[]) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return ref;
}
