export type TextBlock =
  | { type: "heading"; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[]; ordered?: boolean };

const LIST_PREFIX = /^(\d+\.|\([a-z]\)|\([ivx]+\)|[•●▪–-])\s+/i;
const HEADING_LINE =
  /^(chapter|section|part|schedule|annex|appendix|article|regulation|circular|notification)\b/i;

function isHeadingLine(line: string): boolean {
  const t = line.trim();
  if (t.length < 4 || t.length > 120) return false;
  if (HEADING_LINE.test(t)) return true;
  if (/^#{1,4}\s/.test(t)) return true;
  if (/:$/.test(t) && t.length < 90 && !LIST_PREFIX.test(t)) return true;
  if (/^[A-Z][A-Z0-9\s,&.\-–—/()]{6,}$/.test(t) && t.split(/\s+/).length <= 12) return true;
  return false;
}

function stripListPrefix(line: string): string {
  return line.replace(LIST_PREFIX, "").trim();
}

function parseMultiline(text: string): TextBlock[] {
  const lines = text.split(/\n+/).map((l) => l.trim()).filter(Boolean);
  const blocks: TextBlock[] = [];
  let listItems: string[] = [];
  let listOrdered = false;

  const flushList = () => {
    if (!listItems.length) return;
    blocks.push({ type: "list", items: [...listItems], ordered: listOrdered });
    listItems = [];
    listOrdered = false;
  };

  for (const line of lines) {
    const cleaned = line.replace(/^#+\s*/, "");

    if (isHeadingLine(cleaned)) {
      flushList();
      blocks.push({ type: "heading", text: cleaned.replace(/:$/, "") });
      continue;
    }

    if (LIST_PREFIX.test(cleaned)) {
      const ordered = /^\d+\./.test(cleaned);
      if (listItems.length && listOrdered !== ordered) flushList();
      listOrdered = ordered;
      listItems.push(stripListPrefix(cleaned));
      continue;
    }

    if (listItems.length && cleaned.length < 220 && !/[.!?]$/.test(cleaned)) {
      listItems[listItems.length - 1] += ` ${cleaned}`;
      continue;
    }

    flushList();
    blocks.push({ type: "paragraph", text: cleaned });
  }

  flushList();
  return blocks;
}

function splitNumberedBlob(text: string): TextBlock[] | null {
  const markers = [...text.matchAll(/\b(\d+)\.\s+/g)];
  if (markers.length < 2) return null;

  const blocks: TextBlock[] = [];
  const intro = text.slice(0, markers[0].index).trim();
  if (intro) blocks.push({ type: "paragraph", text: intro });

  const items: string[] = [];
  for (let i = 0; i < markers.length; i++) {
    const start = markers[i].index! + markers[i][0].length;
    const end = i + 1 < markers.length ? markers[i + 1].index! : text.length;
    const item = text.slice(start, end).trim();
    if (item) items.push(item);
  }

  if (items.length) blocks.push({ type: "list", items, ordered: true });
  return blocks.length ? blocks : null;
}

function splitRomanBlob(text: string): TextBlock[] | null {
  const markers = [...text.matchAll(/\(\s*([ivxlc]+)\s*\)\s+/gi)];
  if (markers.length < 2) return null;

  const blocks: TextBlock[] = [];
  const intro = text.slice(0, markers[0].index).trim();
  if (intro) blocks.push({ type: "paragraph", text: intro });

  const items: string[] = [];
  for (let i = 0; i < markers.length; i++) {
    const start = markers[i].index! + markers[i][0].length;
    const end = i + 1 < markers.length ? markers[i + 1].index! : text.length;
    const item = text.slice(start, end).trim();
    if (item) items.push(item);
  }

  if (items.length) blocks.push({ type: "list", items, ordered: true });
  return blocks.length ? blocks : null;
}

function splitSentencesIntoParagraphs(text: string): TextBlock[] {
  const sentences =
    text.match(/[^.!?]+[.!?]+(?:\s+|$)|[^.!?]+$/g)?.map((s) => s.trim()).filter(Boolean) ?? [text];

  const blocks: TextBlock[] = [];
  let chunk: string[] = [];

  for (const sentence of sentences) {
    chunk.push(sentence);
    if (chunk.length >= 3) {
      blocks.push({ type: "paragraph", text: chunk.join(" ") });
      chunk = [];
    }
  }

  if (chunk.length) blocks.push({ type: "paragraph", text: chunk.join(" ") });
  return blocks.length ? blocks : [{ type: "paragraph", text }];
}

/** Turn scraped regulatory plain text into structured blocks for display. */
export function parseRegulatoryText(raw: string): TextBlock[] {
  const text = raw.replace(/\r\n/g, "\n").trim();
  if (!text) return [];

  if (text.includes("\n")) {
    const multiline = parseMultiline(text);
    if (multiline.length) return multiline;
  }

  const numbered = splitNumberedBlob(text);
  if (numbered) return numbered;

  const roman = splitRomanBlob(text);
  if (roman) return roman;

  return splitSentencesIntoParagraphs(text);
}

export function regulatoryReadStats(text: string): { words: number; minutes: number } {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return { words, minutes: Math.max(1, Math.round(words / 200)) };
}
