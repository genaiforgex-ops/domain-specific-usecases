/**
 * Repair broken GitHub-flavored Markdown tables before react-markdown/remark-gfm.
 * Mirrors backend ``app.services.markdown_tables`` for streamed / legacy turns.
 */

const SEP_CELL = /^:?-{3,}:?$/;
const BARE_DASH = /^\s*[-—–−]{3,}\s*$/;
const HEADING = /^#{1,6}\s/;
const LIST = /^([-*+]|\d+\.)\s/;

function asciiDashes(s: string): string {
  return s.replace(/[—–−]/g, "-");
}

function looksLikeTableRow(line: string): boolean {
  const s = line.trim();
  if (!s || s.startsWith("```") || s.startsWith(">") || HEADING.test(s)) return false;
  if (s.startsWith("|")) return (s.match(/\|/g) || []).length >= 2;
  if ((s.match(/\|/g) || []).length < 2 || LIST.test(s)) return false;
  const first = s.split("|", 1)[0].trim();
  return first.length > 0 && first.length <= 80;
}

function looksLikeSeparatorRow(line: string): boolean {
  if (!looksLikeTableRow(line)) return false;
  const cells = splitRow(line);
  return cells.length > 0 && cells.every((c) => SEP_CELL.test(c.replace(/\s/g, "")));
}

function isSepCell(cell: string): boolean {
  return SEP_CELL.test(asciiDashes(cell || "").replace(/\s/g, ""));
}

function splitRow(line: string): string[] {
  let s = asciiDashes(line.trim());
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

function formatRow(cells: string[], widths: number[]): string {
  const padded = widths.map((w, i) => (cells[i] ?? "").padEnd(w, " "));
  return `| ${padded.join(" | ")} |`;
}

function formatSeparator(widths: number[]): string {
  return `| ${widths.map((w) => "-".repeat(Math.max(3, w))).join(" | ")} |`;
}

function isWrapContinuation(line: string): boolean {
  const s = (line || "").trim();
  if (!s || s.startsWith("|")) return false;
  if (BARE_DASH.test(s)) return false;
  if (s.startsWith("```") || s.startsWith(">") || HEADING.test(s) || LIST.test(s)) return false;
  return true;
}

function rowIncomplete(line: string): boolean {
  const s = (line || "").replace(/\s+$/, "");
  return Boolean(s) && looksLikeTableRow(s) && !s.endsWith("|");
}

function joinWrappedRows(lines: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim() && out.length && looksLikeTableRow(out[out.length - 1])) {
      const next = lines[i + 1] ?? "";
      if (looksLikeTableRow(next) || BARE_DASH.test(next)) continue;
      if (rowIncomplete(out[out.length - 1]) && isWrapContinuation(next)) continue;
    }
    if (out.length && rowIncomplete(out[out.length - 1]) && isWrapContinuation(line)) {
      out[out.length - 1] = `${out[out.length - 1].replace(/\s+$/, "")} ${line.trim()}`;
      continue;
    }
    out.push(line);
  }
  return out;
}

function expandCollapsed(line: string): string[] {
  const cells = splitRow(line);
  if (cells.length < 2) return [line];

  let sepStart: number | null = null;
  for (let i = 0; i < cells.length; i++) {
    if (cells[i] === "" && i + 1 < cells.length && isSepCell(cells[i + 1])) {
      sepStart = i + 1;
      break;
    }
    if (isSepCell(cells[i]) && i > 0 && !cells.slice(0, i).every(isSepCell)) {
      sepStart = i;
      break;
    }
  }
  if (sepStart == null) return [line];

  const headerCells = [...cells.slice(0, sepStart)];
  while (headerCells.length && headerCells[headerCells.length - 1] === "") {
    headerCells.pop();
  }
  let sepCells = cells.slice(sepStart).filter((c) => c !== "");
  if (!headerCells.length || !sepCells.length || !sepCells.every(isSepCell)) {
    return [line];
  }
  while (sepCells.length < headerCells.length) sepCells.push("---");
  sepCells = sepCells.slice(0, headerCells.length);
  const widths = headerCells.map((c) => Math.max(3, c.length));
  return [formatRow(headerCells, widths), formatSeparator(widths)];
}

function normalizeBlock(lines: string[]): string[] {
  const rows: string[][] = [];
  for (const line of lines) {
    if (looksLikeSeparatorRow(line) || BARE_DASH.test(line)) continue;
    const cells = splitRow(line);
    if (cells.length && cells.every(isSepCell)) continue;
    if (cells.length) rows.push(cells);
  }
  if (!rows.length) return lines;
  const colCount = Math.max(...rows.map((r) => r.length));
  const normalized = rows.map((r) => {
    const copy = [...r];
    while (copy.length < colCount) copy.push("");
    return copy;
  });
  const widths = Array(colCount).fill(3) as number[];
  for (const row of normalized) {
    row.forEach((cell, i) => {
      widths[i] = Math.max(widths[i], cell.length, 3);
    });
  }
  const [header, ...body] = normalized;
  return [formatRow(header, widths), formatSeparator(widths), ...body.map((r) => formatRow(r, widths))];
}

/** Fix collapsed header/separator rows and bare dash noise into valid GFM tables. */
export function normalizeMarkdownTables(text: string): string {
  if (!text || !text.includes("|")) return text;

  const raw = joinWrappedRows(text.split(/\r?\n/));
  const expanded: string[] = [];
  for (const line of raw) {
    if (
      looksLikeTableRow(line) &&
      splitRow(line).some(isSepCell) &&
      !looksLikeSeparatorRow(line)
    ) {
      expanded.push(...expandCollapsed(line));
    } else {
      expanded.push(line);
    }
  }

  const cleaned: string[] = [];
  for (let i = 0; i < expanded.length; i++) {
    const line = expanded[i];
    if (BARE_DASH.test(line)) {
      const prev = expanded[i - 1] ?? "";
      const next = expanded[i + 1] ?? "";
      if (
        looksLikeTableRow(prev) ||
        looksLikeTableRow(next) ||
        BARE_DASH.test(prev) ||
        BARE_DASH.test(next)
      ) {
        continue;
      }
    }
    cleaned.push(line);
  }

  const out: string[] = [];
  let i = 0;
  while (i < cleaned.length) {
    if (looksLikeTableRow(cleaned[i])) {
      const start = i;
      while (
        i < cleaned.length &&
        (looksLikeTableRow(cleaned[i]) || BARE_DASH.test(cleaned[i]))
      ) {
        i++;
      }
      const block = cleaned.slice(start, i).filter((ln) => !BARE_DASH.test(ln));
      out.push(...(block.length ? normalizeBlock(block) : cleaned.slice(start, i)));
      continue;
    }
    out.push(cleaned[i]);
    i++;
  }

  let result = out.join("\n");
  if (text.endsWith("\n") && !result.endsWith("\n")) result += "\n";
  return result;
}
