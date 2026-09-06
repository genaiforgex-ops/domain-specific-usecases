import { Link } from "react-router-dom";
import { EvidenceItem } from "../api/client";
import { ClauseViewerTarget } from "./ClauseViewerPanel";
import { IconSparkle } from "./ui/Icons";
import { Button } from "./ui/index";
import { formatLabel, formatPercent } from "../utils/format";

interface AISuggestionPanelProps {
  regulator?: string;
  label: string | null;
  confidence: number | null;
  evidence?: EvidenceItem[];
  reasoning?: string;
  truncated?: boolean;
  aiEnabled: boolean;
  onAccept: () => void;
  onReject: () => void;
  onEdit: () => void;
  onEvidenceClick?: (target: ClauseViewerTarget) => void;
  loading?: boolean;
}

function confidenceLevel(c: number | null): { text: string; level: string } {
  if (c == null) return { text: "Unknown", level: "unknown" };
  if (c >= 0.85) return { text: "High confidence", level: "high" };
  if (c >= 0.7) return { text: "Medium confidence", level: "medium" };
  return { text: "Low confidence — secondary review", level: "low" };
}

// The model returns reasoning as one string of "Label: text" sections (see the
// REASONING FORMAT in the M1 prompt). Split it back into sections so each can
// render on its own line — a wall of prose is unreadable for a reviewer.
const REASONING_SECTIONS = [
  "Entity Context",
  "Service Category",
  "Activity",
  "Why this label",
  "Why not the alternatives",
  "Materiality",
  // SEBI-only: the model emits this after Materiality. RBI reasoning never
  // contains it, so it simply won't render there.
  "Outsourcing Principles",
];

function parseReasoningSections(text: string): { label: string; body: string }[] {
  const escaped = REASONING_SECTIONS.map((l) => l.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`(${escaped.join("|")})\\s*:\\s*`, "g");
  const hits: { label: string; contentStart: number; labelStart: number }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    hits.push({ label: m[1], contentStart: re.lastIndex, labelStart: m.index });
  }
  return hits.map((h, i) => ({
    label: h.label,
    body: text.slice(h.contentStart, i + 1 < hits.length ? hits[i + 1].labelStart : text.length).trim(),
  }));
}

export function AISuggestionPanel({
  regulator,
  label,
  confidence,
  evidence,
  reasoning,
  truncated,
  aiEnabled,
  onAccept,
  onReject,
  onEdit,
  onEvidenceClick,
  loading,
}: AISuggestionPanelProps) {
  const conf = confidenceLevel(confidence);

  // Defensive: the backend coerces reasoning to a string, but a job stored
  // before that fix (or an unexpected shape) could still be an object/array.
  // Flatten it so we never try to render a raw object as a React child.
  const r = reasoning as unknown;
  const reasoningText: string | undefined =
    r == null
      ? undefined
      : typeof r === "string"
        ? r
        : typeof r === "object"
          ? Object.entries(r as Record<string, unknown>).map(([k, v]) => `${k}: ${v}`).join("\n")
          : String(r);

  if (!aiEnabled) {
    return (
      <section className="ai-panel ai-panel--disabled" aria-label="AI assistance disabled">
        <p style={{ margin: 0, color: "var(--slate-600)" }}>
          AI assistance is turned off for this module. Complete the review manually; all decisions are still audited.
        </p>
      </section>
    );
  }

  return (
    <section className="ai-panel" aria-label="AI suggestion — advisory only">
      <header className="ai-panel__header">
        <span className="ai-panel__badge">
          <IconSparkle size={14} />
          {regulator ? `${regulator} · AI Advisory` : "AI Advisory"}
        </span>
        <h2 className="ai-panel__title">Suggested classification</h2>
        <span className={`ai-panel__confidence ai-panel__confidence--${conf.level}`}>
          {conf.text} · {formatPercent(confidence)}
        </span>
      </header>

      <p className="ai-panel__label">
        Proposed label: <strong>{formatLabel(label)}</strong>
      </p>

      {truncated && (
        <p style={{ fontSize: 12, color: "var(--amber-700, #b45309)", margin: "0 0 12px", fontWeight: 500 }}>
          ⚠ Input exceeded length limit — end of document may have been cut before classification.
        </p>
      )}

      {reasoningText && (
        <div className="ai-panel__reasoning" style={{ margin: "0 0 16px", fontSize: 13, color: "var(--slate-700)" }}>
          <h4 style={{ margin: "0 0 8px" }}>Why this label</h4>
          {(() => {
            const sections = parseReasoningSections(reasoningText);
            if (sections.length === 0) {
              return <p style={{ margin: 0 }}>{reasoningText}</p>;
            }
            return (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {sections.map((s, i) => (
                  <div key={i} style={{ lineHeight: 1.5 }}>
                    <span style={{ fontWeight: 600, color: "var(--slate-900, #0f172a)" }}>{s.label}: </span>
                    <span>{s.body}</span>
                  </div>
                ))}
              </div>
            );
          })()}
        </div>
      )}

      {evidence && evidence.length > 0 ? (
        <div className="ai-panel__evidence">
          <h4>Evidence — click to open source regulation</h4>
          <ul>
            {evidence.slice(0, 4).map((e, i) => {
              const citation = [
                e.source_doc ?? (`${regulator ?? ""}${e.instrument ? ` ${e.instrument}` : ""}`.trim() || "Regulation"),
                e.page_no ? `p.${e.page_no}` : null,
                e.para_no ? `Para ${e.para_no}` : null,
              ].filter(Boolean).join(" · ");

              const canOpen = !!(e.instrument && e.clause_id && (e.page_no || e.para_no));

              return (
                <li key={i}>
                  {canOpen ? (
                    <button
                      className="ai-panel__evidence-link"
                      onClick={() => onEvidenceClick?.({
                        regulator: regulator ?? "",
                        instrument: e.instrument,
                        source_doc: e.source_doc,
                        page_no: e.page_no,
                        para_no: e.para_no,
                        clause_id: e.clause_id,
                        clause_ref: e.clause_ref,
                        clause_text: e.clause_text,
                      })}
                    >
                      <span className="ai-panel__evidence-icon">📄</span>
                      {citation}
                    </button>
                  ) : (
                    <span className="ai-panel__evidence-citation">{citation || e.clause_ref}</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ) : (
        <div className="ai-panel__evidence ai-panel__evidence--empty">
          <p style={{ margin: 0, fontSize: 13, color: "var(--slate-600)" }}>
            No matching {regulator ? `${regulator} ` : ""}clause found to cite as evidence.{" "}
            <Link to="/admin/library">Add official regulator documents</Link> to the Library so future
            classifications can be grounded in a citation.
          </p>
        </div>
      )}

      <p style={{ fontSize: 12, color: "var(--slate-500)", margin: "0 0 16px" }}>
        Human reviewer must accept, edit, or reject. This suggestion is not a final decision.
      </p>

      <div className="ai-panel__actions" role="group" aria-label="Review actions">
        <Button variant="primary" onClick={onAccept} loading={loading} disabled={!label}>
          Accept suggestion
        </Button>
        <Button variant="secondary" onClick={onEdit} disabled={loading}>
          Override
        </Button>
        <Button variant="ghost" onClick={onReject} disabled={loading}>
          Dismiss
        </Button>
      </div>
    </section>
  );
}
