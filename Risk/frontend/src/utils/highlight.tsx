import { Fragment, type ReactNode } from "react";

export interface HighlightSpan {
  start: number;
  end: number;
  className: string;
}

/**
 * Render `text` with [start, end) ranges wrapped in <mark>. Ranges are
 * clipped against whichever earlier-starting span already claimed that
 * region — RBI and SEBI evidence can point at overlapping parts of the same
 * vendor clause, and a clean merge isn't worth the complexity for what's
 * just a visual aid (first span sorted by start wins the overlap).
 */
export function renderHighlighted(text: string, spans: HighlightSpan[]): ReactNode[] {
  const valid = spans
    .filter((s) => s.end > s.start && s.start >= 0 && s.start < text.length)
    .map((s) => ({ ...s, end: Math.min(s.end, text.length) }))
    .sort((a, b) => a.start - b.start);

  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const span of valid) {
    if (span.start < cursor) continue;
    if (span.start > cursor) {
      nodes.push(<Fragment key={`t${cursor}`}>{text.slice(cursor, span.start)}</Fragment>);
    }
    nodes.push(
      <mark key={`m${span.start}`} className={span.className}>
        {text.slice(span.start, span.end)}
      </mark>
    );
    cursor = span.end;
  }
  if (cursor < text.length) {
    nodes.push(<Fragment key={`t${cursor}`}>{text.slice(cursor)}</Fragment>);
  }
  return nodes;
}
