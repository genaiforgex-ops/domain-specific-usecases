import type { DiffBlock } from "@/types";

export function classNames(...classes: Array<string | false | undefined | null>): string {
  return classes.filter(Boolean).join(" ");
}

/** Reject punctuation-only / empty Ask-AI-to-edit prompts (e.g. "."). */
export function isActionableEditInstruction(instruction: string | null | undefined): boolean {
  const text = (instruction ?? "").trim();
  if (!text) return false;
  const alnum = text.replace(/[^0-9A-Za-z]+/g, "");
  if (alnum.length < 3) return false;
  if (![...alnum].some((ch) => /[A-Za-z]/.test(ch))) return false;
  return /[A-Za-z0-9]{2,}/.test(text);
}

const UNSAFE_EDIT_RE =
  /\b(pretend|role[\s-]?play|roleplay|jailbreak|do\s+anything\s+now|ignore\s+(all\s+)?(previous|prior|above|system)\s+instructions?|act\s+as\s+(if|though|a|an)|you\s+are\s+now|fanfic|fanfiction|fictional\s+scenario|rewrite\s+(this|it|the\s+(document|msa|nda|contract))\s+(into|as)\s+a?\s*(poem|song|joke|story|rap|meme))\b/i;

export function isSafeEditInstruction(instruction: string | null | undefined): boolean {
  const text = (instruction ?? "").trim();
  if (!isActionableEditInstruction(text)) return false;
  return !UNSAFE_EDIT_RE.test(text);
}

export const ACTIONABLE_EDIT_INSTRUCTION_MESSAGE =
  "Enter a clear edit instruction (e.g. change X to Y, add a DPDP clause). Punctuation-only or empty prompts are not allowed.";

export const EDIT_REFUSAL_MESSAGE =
  "I can only apply legitimate legal-document edits for JFPSL counsel (clause changes, redlines, standard positions). I can't follow jailbreak, role-play, or fictional rewrite requests. Please describe a concrete legal edit.";


type Opcode = { tag: DiffBlock["kind"]; i1: number; i2: number; j1: number; j2: number };

/** Split into lines the way Python's str.splitlines() does (drops one trailing newline). */
function splitLines(s: string): string[] {
  const lines = s.split(/\r\n|\r|\n/);
  if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

/** LCS-based opcodes for a changed region (no common prefix/suffix inside). */
function lcsOpcodes(a: string[], b: string[]): Opcode[] {
  const n = a.length;
  const m = b.length;
  if (n === 0 && m === 0) return [];
  if (n === 0) return [{ tag: "insert", i1: 0, i2: 0, j1: 0, j2: m }];
  if (m === 0) return [{ tag: "delete", i1: 0, i2: n, j1: 0, j2: 0 }];
  // Guard against pathological sizes: fall back to a single replace block.
  if (n * m > 4_000_000) return [{ tag: "replace", i1: 0, i2: n, j1: 0, j2: m }];

  const dp: Int32Array[] = new Array(n + 1);
  for (let i = 0; i <= n; i++) dp[i] = new Int32Array(m + 1);
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const raw: Array<{ tag: "equal" | "delete" | "insert"; i: number; j: number }> = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      raw.push({ tag: "equal", i, j });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      raw.push({ tag: "delete", i, j });
      i++;
    } else {
      raw.push({ tag: "insert", i, j });
      j++;
    }
  }
  while (i < n) raw.push({ tag: "delete", i: i++, j });
  while (j < m) raw.push({ tag: "insert", i, j: j++ });

  const ops: Opcode[] = [];
  let k = 0;
  while (k < raw.length) {
    if (raw[k].tag === "equal") {
      const i1 = raw[k].i;
      const j1 = raw[k].j;
      let curI = i1;
      let curJ = j1;
      while (k < raw.length && raw[k].tag === "equal") {
        curI = raw[k].i + 1;
        curJ = raw[k].j + 1;
        k++;
      }
      ops.push({ tag: "equal", i1, i2: curI, j1, j2: curJ });
    } else {
      const i1 = raw[k].i;
      const j1 = raw[k].j;
      let curI = i1;
      let curJ = j1;
      while (k < raw.length && raw[k].tag !== "equal") {
        if (raw[k].tag === "delete") curI = raw[k].i + 1;
        else curJ = raw[k].j + 1;
        k++;
      }
      const tag: DiffBlock["kind"] =
        curI > i1 && curJ > j1 ? "replace" : curI > i1 ? "delete" : "insert";
      ops.push({ tag, i1, i2: curI, j1, j2: curJ });
    }
  }
  return ops;
}

/**
 * Line-level diff between two texts, producing DiffView-compatible blocks.
 * Uses common prefix/suffix trimming + LCS on the changed region so results are
 * accurate (no phantom trailing insert/delete) and cheap for typical edits.
 */
export function lineDiffBlocks(before: string, after: string): DiffBlock[] {
  const a = splitLines(before);
  const b = splitLines(after);

  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA--;
    endB--;
  }

  const ops: Opcode[] = [];
  if (start > 0) ops.push({ tag: "equal", i1: 0, i2: start, j1: 0, j2: start });
  for (const op of lcsOpcodes(a.slice(start, endA), b.slice(start, endB))) {
    ops.push({
      tag: op.tag,
      i1: op.i1 + start,
      i2: op.i2 + start,
      j1: op.j1 + start,
      j2: op.j2 + start,
    });
  }
  if (endA < a.length) ops.push({ tag: "equal", i1: endA, i2: a.length, j1: endB, j2: b.length });

  return ops.map((op) => ({
    kind: op.tag,
    v1: a.slice(op.i1, op.i2).join("\n"),
    v2: b.slice(op.j1, op.j2).join("\n"),
  }));
}

export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

/** Apple semantic status colors — always pair with a text label in UI. */
export function riskColor(flag: string): string {
  switch (flag) {
    case "high":
      return "bg-red-500/10 text-error border-red-500/20";
    case "medium":
      return "bg-warning/10 text-warning border-warning/20";
    case "low":
      return "bg-accent/10 text-accent border-accent/20";
    default:
      return "bg-bg-secondary text-label-secondary border-separator";
  }
}

export function statusColor(status: string): string {
  switch (status) {
    case "action_required":
    case "escalated":
    case "under_review":
      return "bg-warning/10 text-warning";
    case "finalized":
    case "answered":
    case "resolved":
    case "executed":
      return "bg-success/10 text-success";
    case "for_information":
    case "draft":
    case "pending_review":
      return "bg-bg-secondary text-label-secondary";
    case "not_relevant":
      return "bg-bg-secondary text-label-tertiary";
    default:
      return "bg-bg-secondary text-label-secondary";
  }
}
