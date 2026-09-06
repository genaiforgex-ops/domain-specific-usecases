import { useCallback, useEffect, useState } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";

import { Markdown } from "@/components/Markdown";
import { ContractDocumentPanel } from "@/components/ContractDocumentPanel";
import { DiffView } from "@/components/DiffView";
import { Icon } from "@/components/Icons";
import { ReviewOnboardingTour } from "@/components/review/ReviewOnboardingTour";
import { ReviewGuidelinesInput } from "@/components/review/ReviewGuidelinesInput";
import { ReviewWorkspace, type ChangeMode } from "@/components/review/ReviewWorkspace";
import { Splitter } from "@/components/Splitter";
import { UploadZone } from "@/components/UploadZone";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import { classNames, formatDate, riskColor, statusColor, isActionableEditInstruction, isSafeEditInstruction, ACTIONABLE_EDIT_INSTRUCTION_MESSAGE, EDIT_REFUSAL_MESSAGE } from "@/lib/utils";
import type {
  Contract,
  ContractClause,
  ContractRevision,
  ContractSuggestionsPreview,
  ContractSummary,
  ReviewFinding,
} from "@/types";

const QUICK_PROMPTS = [
  "Make the liability cap mutual and limited to 12 months of fees",
  "Add a standard DPDP data-protection clause",
  "Replace unlimited liability with a mutual 12-month cap",
  "Change sole discretion to mutual agreement",
];

type DetailTab = "edit" | "review";

function clausesToFindings(clauses: ContractClause[]): ReviewFinding[] {
  return clauses.map((c) => ({
    order_index: c.order_index,
    heading: c.heading,
    clause_text: c.clause_text,
    risk_flag: c.risk_flag,
    confidence: c.confidence,
    rationale: c.ai_rationale || "",
    ai_suggestion: c.ai_suggestion,
    decision:
      c.decision === "accepted"
        ? "accept"
        : c.decision === "rejected"
          ? "reject"
          : c.decision === "edited"
            ? "modify"
            : "pending",
    reviewer_edit: c.reviewer_edit,
  }));
}

function contractFindings(contract: Contract): ReviewFinding[] {
  if (contract.ai_suggestions?.length) return contract.ai_suggestions;
  return clausesToFindings(contract.clauses);
}

export function ContractReviewPage() {
  return (
    <Routes>
      <Route index element={<List />} />
      <Route path="new" element={<NewContract />} />
      <Route path=":id" element={<Detail />} />
    </Routes>
  );
}

function List() {
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listContracts().then((rows) => {
      setContracts(rows);
      setLoading(false);
    });
  }, []);

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        eyebrow={
          <span className="inline-flex items-center gap-2">
            <Icon.ContractReview className="w-4 h-4" aria-hidden />
            UC-01 · AI-assisted review
          </span>
        }
        title="Contract Review"
        subtitle="Upload a contract, get clause-level risk analysis against the JFPSL playbook, then edit the document in plain language — every change is tracked for your approval."
        actions={
          <Link to="new">
            <Button>
              <Icon.Plus className="w-4 h-4 mr-1.5" aria-hidden />
              New review
            </Button>
          </Link>
        }
      />

      <Card className="shadow-card">
        {loading ? (
          <div className="py-8 text-center text-subheadline text-label-secondary">Loading contracts…</div>
        ) : contracts.length === 0 ? (
          <div className="py-14 text-center">
            <Icon.Documents className="w-12 h-12 mx-auto text-label-tertiary mb-3" aria-hidden />
            <p className="text-label font-medium">No contracts reviewed yet</p>
            <p className="text-subheadline text-label-secondary mt-1 max-w-md mx-auto">
              Upload an MSA, NDA, or vendor agreement to start AI review and prompt-based editing.
            </p>
            <Link to="new" className="inline-block mt-4">
              <Button>Upload your first contract</Button>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto -mx-5">
            <table className="w-full text-sm">
              <thead className="text-left text-caption uppercase tracking-wider text-label-tertiary border-b border-separator/40">
                <tr>
                  <th className="py-3 px-5 font-medium">Document</th>
                  <th className="py-3 font-medium">Type</th>
                  <th className="py-3 font-medium">Risk</th>
                  <th className="py-3 font-medium">Status</th>
                  <th className="py-3 font-medium">Uploaded</th>
                  <th className="py-3 px-5" />
                </tr>
              </thead>
              <tbody>
                {contracts.map((c) => (
                  <tr
                    key={c.id}
                    className="border-b border-separator/30 hover:bg-bg-secondary/80 transition-colors min-h-tap"
                  >
                    <td className="py-3.5 px-5">
                      <div className="font-medium text-label">{c.filename}</div>
                    </td>
                    <td className="py-3.5">
                      <Badge className="bg-bg-secondary text-label-secondary">
                        {c.contract_type}
                      </Badge>
                    </td>
                    <td className="py-3.5">
                      {c.risk_score != null ? (
                        <span
                          className={classNames(
                            "inline-flex items-center gap-1 font-semibold tabular-nums",
                            c.risk_score >= 70
                              ? "text-error"
                              : c.risk_score >= 40
                                ? "text-warning"
                                : "text-success",
                          )}
                        >
                          {c.risk_score}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-3.5">
                      <Badge className={statusColor(c.status)}>{c.status.replace(/_/g, " ")}</Badge>
                    </td>
                    <td className="py-3.5 text-label-secondary tabular-nums">{formatDate(c.created_at)}</td>
                    <td className="py-3.5 px-5 text-right">
                      <Link
                        to={`${c.id}`}
                        className="inline-flex items-center gap-1 min-h-tap text-accent hover:opacity-80 font-medium"
                      >
                        Open
                        <Icon.ArrowRight className="w-4 h-4" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function NewContract() {
  const navigate = useNavigate();
  const [filename, setFilename] = useState("");
  const [contractType, setContractType] = useState("MSA");
  const [guidelines, setGuidelines] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleFile(f: File | null) {
    setFile(f);
    if (!f) return;
    setFilename(f.name);
    const reader = new FileReader();
    reader.onload = () => setText(String(reader.result || ""));
    reader.readAsText(f);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const contract = await api.createContract({
        filename: filename || file?.name || "contract.txt",
        contract_type: contractType,
        raw_text: text,
        review_guidelines: guidelines.trim() || undefined,
      });
      navigate(`../${contract.id}`);
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-6 pb-10">
      <Link to=".." className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
        ← Back to reviews
      </Link>
      <div>
        <h1 className="text-2xl font-semibold text-label">New contract review</h1>
        <p className="text-sm text-label-secondary mt-1">
          Upload or paste your contract. AI will analyse each clause against the JFPSL playbook.
        </p>
      </div>
      <Card className="shadow-card">
        <form className="space-y-5" onSubmit={submit}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Filename"
              placeholder="vendor_msa_v1.txt"
              value={filename}
              onChange={(e) => setFilename(e.target.value)}
              required
            />
            <Select
              label="Contract type"
              value={contractType}
              onChange={(e) => setContractType(e.target.value)}
            >
              <option value="MSA">MSA</option>
              <option value="NDA">NDA</option>
              <option value="DPA">Data Processing Agreement</option>
              <option value="SOW">Statement of Work</option>
            </Select>
          </div>
          <ReviewGuidelinesInput value={guidelines} onChange={setGuidelines} />
          <UploadZone
            file={file}
            onFile={handleFile}
            label="Drop your contract here"
            hint="TXT or MD for now · PDF/DOCX in MSA module"
          />
          <Textarea
            label="Or paste contract text"
            rows={14}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"1. Scope of Services\n   The Vendor shall provide …\n\n2. Limitation of Liability\n   …"}
            required
          />
          {error && <p className="text-sm text-error">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={() => navigate("..")}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Analysing…" : "Run AI review"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

function Detail() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [contract, setContract] = useState<Contract | null>(null);
  const [tab, setTab] = useState<DetailTab>("review");
  const [selection, setSelection] = useState("");
  const [highlightQuery, setHighlightQuery] = useState<string | null>(null);
  const [changeMode, setChangeMode] = useState<ChangeMode>("track");
  const [suggestionsPreview, setSuggestionsPreview] = useState<ContractSuggestionsPreview | null>(null);
  const [suggestionsBusy, setSuggestionsBusy] = useState(false);
  const [suggestionsError, setSuggestionsError] = useState<string | null>(null);
  const [clauseBank, setClauseBank] = useState<
    Array<{ id: number; title: string; body_text: string; tier: string }>
  >([]);

  const load = useCallback(async () => {
    if (!id) return;
    const c = await api.getContract(Number(id));
    setContract(c);
    if (c.contract_type) {
      api.listClauseBankByType(c.contract_type).then((rows) => setClauseBank(rows)).catch(() => setClauseBank([]));
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (!contract) {
    return (
      <div className="flex items-center justify-center py-20 text-label-secondary text-sm">
        Loading contract…
      </div>
    );
  }

  const canApprove = hasPermission(user, "approve_ai_output");
  const findings = contractFindings(contract);
  const highRisk = findings.filter((c) => c.risk_flag === "high").length;
  const locked = contract.status === "finalized";

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)] -mx-8 -my-6">
      <div className="flex-shrink-0 px-6 py-4 bg-bg border-b border-separator/40 flex items-center gap-4 flex-wrap">
        <Link to=".." className="text-sm text-label-secondary hover:text-accent flex items-center gap-1">
          ← Reviews
        </Link>
        <div className="h-4 w-px bg-separator/40 hidden sm:block" />
        <div className="flex-1 min-w-0">
          <h1 className="text-lg font-semibold text-label truncate">{contract.filename}</h1>
          <p className="text-xs text-label-secondary mt-0.5">
            {contract.contract_type} · {findings.length} findings · risk{" "}
            <span className="font-semibold text-label-secondary">{contract.risk_score}</span>
            {highRisk > 0 && <span className="text-error ml-1">· {highRisk} high-risk</span>}
          </p>
        </div>
        <Badge className={statusColor(contract.status)}>{contract.status.replace(/_/g, " ")}</Badge>
        {canApprove && !locked && (
          <Button
            size="sm"
            onClick={async () => {
              await api.finalizeContract(contract.id);
              load();
            }}
          >
            <Icon.Check className="w-4 h-4 mr-1" />
            Finalize
          </Button>
        )}
      </div>

      <div className="flex-1 min-h-0 px-4 py-4 space-y-3 overflow-y-auto">
        <ReviewOnboardingTour />

        <Splitter initial={52} min={30} storageKey="contract-review" className="h-full min-h-[480px] rounded-xl">
          <ContractDocumentPanel
            text={contract.raw_text}
            filename={contract.filename}
            status={contract.status}
            onSelection={setSelection}
            highlightQuery={highlightQuery}
            previewText={suggestionsPreview?.edited_text}
          />
          <div className="h-full flex flex-col bg-bg border border-separator/40 rounded-xl shadow-card overflow-hidden">
            <div className="flex border-b border-separator/30 bg-bg-secondary/80 flex-shrink-0">
              <button
                type="button"
                onClick={() => setTab("review")}
                className={classNames(
                  "flex-1 px-4 py-3 text-sm font-medium transition flex items-center justify-center gap-2",
                  tab === "review"
                    ? "text-accent border-b-2 border-accent bg-bg"
                    : "text-label-secondary hover:text-label-secondary",
                )}
              >
                <Icon.Flag className="w-4 h-4" />
                Review workspace
              </button>
              <button
                type="button"
                onClick={() => setTab("edit")}
                className={classNames(
                  "flex-1 px-4 py-3 text-sm font-medium transition flex items-center justify-center gap-2",
                  tab === "edit"
                    ? "text-accent border-b-2 border-accent bg-bg"
                    : "text-label-secondary hover:text-label-secondary",
                )}
              >
                <Icon.Sparkles className="w-4 h-4" />
                AI Editor
              </button>
            </div>

            <div className="flex-1 overflow-y-auto scrollbar-thin p-4">
              {tab === "edit" ? (
                <PromptEditPanel
                  contract={contract}
                  canApprove={canApprove}
                  selection={selection}
                  onSelectionChange={setSelection}
                  onApplied={load}
                />
              ) : (
                <ReviewWorkspace
                  contractType={contract.contract_type}
                  suggestions={findings}
                  riskScore={contract.risk_score}
                  riskBreakdown={contract.risk_breakdown}
                  playbookSummary={contract.playbook_summary}
                  changeHistory={contract.change_history ?? undefined}
                  status={contract.status}
                  locked={locked}
                  canApprove={canApprove}
                  changeMode={changeMode}
                  onChangeMode={setChangeMode}
                  allowTextEdit
                  preview={suggestionsPreview}
                  busy={suggestionsBusy}
                  error={suggestionsError}
                  clauseBankOptions={clauseBank}
                  onHighlightExcerpt={(t) => setHighlightQuery(t)}
                  onJumpToSuggestion={(orderIndex) => {
                    document
                      .querySelector(`[data-suggestion-id="${orderIndex}"]`)
                      ?.scrollIntoView({ behavior: "smooth", block: "center" });
                  }}
                  onInsertFromBank={async (orderIndex, bodyText) => {
                    await api.decideContractSuggestion(contract.id, orderIndex, "modify", bodyText);
                    await load();
                  }}
                  onRunReview={async () => {
                    setSuggestionsBusy(true);
                    try {
                      await api.runContractReview(contract.id);
                      await load();
                    } finally {
                      setSuggestionsBusy(false);
                    }
                  }}
                  onDecide={async (orderIndex, decision, reviewerEdit) => {
                    await api.decideContractSuggestion(contract.id, orderIndex, decision, reviewerEdit);
                    await load();
                  }}
                  onPreview={async () => {
                    setSuggestionsBusy(true);
                    setSuggestionsError(null);
                    try {
                      setSuggestionsPreview(await api.previewContractSuggestions(contract.id));
                    } catch (e) {
                      setSuggestionsError(e instanceof Error ? e.message : "Preview failed");
                    } finally {
                      setSuggestionsBusy(false);
                    }
                  }}
                  onApply={async (force, editedText) => {
                    setSuggestionsBusy(true);
                    setSuggestionsError(null);
                    try {
                      await api.applyContractSuggestions(contract.id, {
                        edited_text: editedText ?? suggestionsPreview?.edited_text,
                        change_mode: changeMode,
                        force,
                      });
                      setSuggestionsPreview(null);
                      await load();
                    } catch (e) {
                      setSuggestionsError(e instanceof Error ? e.message : "Apply failed");
                    } finally {
                      setSuggestionsBusy(false);
                    }
                  }}
                />
              )}
            </div>
          </div>
        </Splitter>
      </div>
    </div>
  );
}

function PromptEditPanel({
  contract,
  canApprove,
  selection,
  onSelectionChange,
  onApplied,
}: {
  contract: Contract;
  canApprove: boolean;
  selection: string;
  onSelectionChange: (s: string) => void;
  onApplied: () => void;
}) {
  const [instruction, setInstruction] = useState("");
  const [revision, setRevision] = useState<ContractRevision | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const disabled = contract.status === "finalized";

  async function propose() {
    if (!isActionableEditInstruction(instruction)) {
      setError(ACTIONABLE_EDIT_INSTRUCTION_MESSAGE);
      return;
    }
    if (!isSafeEditInstruction(instruction)) {
      setError(EDIT_REFUSAL_MESSAGE);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const rev = await api.promptEditContract(contract.id, {
        instruction,
        selection: selection.trim() || undefined,
      });
      setRevision(rev);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Edit failed");
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!revision) return;
    setBusy(true);
    try {
      await api.applyContractRevision(contract.id, revision.id);
      setRevision(null);
      setInstruction("");
      onSelectionChange("");
      onApplied();
    } finally {
      setBusy(false);
    }
  }

  async function discard() {
    if (!revision) return;
    setBusy(true);
    try {
      await api.discardContractRevision(contract.id, revision.id);
      setRevision(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold text-label">Edit with a prompt</h2>
        <p className="text-sm text-label-secondary mt-1 leading-relaxed">
          Describe the change in plain language. Highlight text in the document to limit the edit
          to a specific clause, or leave scope open for document-wide changes.
        </p>
      </div>

      {disabled ? (
        <div className="rounded-lg bg-bg-secondary border border-separator/40 p-4 text-sm text-label-secondary">
          This contract is finalized. Reopen it to make further edits.
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {QUICK_PROMPTS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setInstruction(p)}
                className="text-xs px-2.5 py-1 rounded-full border border-separator/40 bg-bg text-label-secondary hover:border-accent/30 hover:text-accent hover:bg-accent/10 transition"
              >
                {p.length > 48 ? p.slice(0, 48) + "…" : p}
              </button>
            ))}
          </div>

          <Textarea
            label="Your instruction"
            rows={3}
            placeholder='e.g. "Make the liability cap mutual and limited to 12 months of fees"'
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
          />

          <Textarea
            label="Scope (optional)"
            rows={2}
            placeholder="Paste or highlight the clause this edit should apply to…"
            value={selection}
            onChange={(e) => onSelectionChange(e.target.value)}
          />
          {selection && (
            <button
              type="button"
              className="text-xs text-label-secondary hover:text-error underline"
              onClick={() => onSelectionChange("")}
            >
              Clear scope
            </button>
          )}

          <Button disabled={busy || !isSafeEditInstruction(instruction)} onClick={propose} className="w-full sm:w-auto">
            <Icon.Sparkles className="w-4 h-4 mr-1.5" />
            {busy && !revision ? "Drafting edit…" : "Generate proposed edit"}
          </Button>
          {error && <p className="text-sm text-error">{error}</p>}
        </>
      )}

      {revision && (
        <div className="rounded-xl border border-warning/20 bg-amber-50/40 p-4 space-y-4 animate-fade-in">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <Badge className="bg-amber-100 text-amber-800 border-warning/20">Proposed edit</Badge>
              <p className="text-xs text-label-secondary mt-1">
                Model <span className="font-mono">{revision.model_version}</span> · review before applying
              </p>
            </div>
            <div className="flex gap-2">
              {canApprove ? (
                <>
                  <Button size="sm" disabled={busy} onClick={apply}>
                    <Icon.Check className="w-3.5 h-3.5 mr-1" />
                    Apply
                  </Button>
                  <Button size="sm" variant="danger" disabled={busy} onClick={discard}>
                    Discard
                  </Button>
                </>
              ) : (
                <Button size="sm" variant="secondary" disabled={busy} onClick={discard}>
                  Discard
                </Button>
              )}
            </div>
          </div>

          {revision.change_summary && (
            <div className="text-sm text-label-secondary bg-bg border border-amber-100 rounded-lg p-3 leading-relaxed overflow-x-auto">
              <Markdown text={revision.change_summary} />
            </div>
          )}

          {!canApprove && (
            <p className="text-xs text-amber-800">
              You can propose edits; applying requires approval permission.
            </p>
          )}

          <DiffView
            v1Label="Current document"
            v2Label="Proposed (redline)"
            blocks={revision.diff_blocks ?? []}
            height={280}
          />
        </div>
      )}

      <div className="rounded-lg border border-separator/30 bg-bg-secondary p-3 text-xs text-label-secondary leading-relaxed">
        <strong className="text-label-secondary">How it works:</strong> AI drafts the edit as a track-mode
        redline. Nothing changes until you click Apply. Every step is audit-logged.
      </div>
    </div>
  );
}

function ClauseCard({
  contractId,
  clause,
  canApprove,
  onChanged,
  onUseAsSelection,
}: {
  contractId: number;
  clause: ContractClause;
  canApprove: boolean;
  onChanged: () => void;
  onUseAsSelection: (text: string) => void;
}) {
  const [expanded, setExpanded] = useState(clause.risk_flag === "high" || clause.risk_flag === "medium");
  const [comment, setComment] = useState(clause.reviewer_comment || "");
  const [edit, setEdit] = useState(clause.reviewer_edit || "");
  const [busy, setBusy] = useState(false);

  async function decide(decision: string) {
    setBusy(true);
    try {
      await api.decideClause(contractId, clause.id, {
        decision,
        reviewer_edit: decision === "edited" ? edit : undefined,
        reviewer_comment: comment || undefined,
      });
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={classNames(
        "rounded-xl border transition",
        clause.risk_flag === "high"
          ? "border-error/20 bg-red-50/30"
          : clause.risk_flag === "medium"
            ? "border-warning/20 bg-amber-50/20"
            : "border-separator/40 bg-bg",
      )}
    >
      <button
        type="button"
        className="w-full text-left px-4 py-3 flex items-start gap-3"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="text-xs font-mono text-label-tertiary mt-0.5">#{clause.order_index + 1}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge className={riskColor(clause.risk_flag)}>{clause.risk_flag}</Badge>
            <span className="text-xs text-label-secondary">
              {Math.round(clause.confidence * 100)}% confidence
            </span>
            <Badge
              className={classNames(
                "text-[10px]",
                clause.decision === "accepted"
                  ? "bg-emerald-100 text-emerald-800 border-emerald-200"
                  : clause.decision === "rejected"
                    ? "bg-red-100 text-red-800 border-error/20"
                    : clause.decision === "edited"
                      ? "bg-blue-100 text-blue-800 border-accent/20"
                      : "bg-bg-secondary text-label-secondary border-separator/40",
              )}
            >
              {clause.decision}
            </Badge>
          </div>
          {clause.heading && (
            <p className="text-sm font-medium text-label mt-1 truncate">{clause.heading}</p>
          )}
        </div>
        <Icon.ChevronDown
          className={classNames(
            "w-4 h-4 text-label-tertiary transition-transform shrink-0",
            expanded && "rotate-180",
          )}
        />
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-separator/30/80 pt-3 space-y-3">
          <pre className="text-sm text-label-secondary whitespace-pre-wrap font-sans bg-bg rounded-lg p-3 border border-separator/30 max-h-48 overflow-y-auto">
            {clause.clause_text}
          </pre>
          <button
            type="button"
            className="text-xs text-accent hover:underline"
            onClick={() => onUseAsSelection(clause.clause_text)}
          >
            Use in AI editor scope →
          </button>
          <p className="text-xs text-label-secondary italic">{clause.ai_rationale}</p>
          {clause.ai_suggestion && (
            <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-sm">
              <div className="text-xs font-semibold text-blue-700 mb-1">Playbook suggestion</div>
              <div className="text-label-secondary whitespace-pre-wrap">{clause.ai_suggestion}</div>
            </div>
          )}
          {canApprove && (
            <div className="space-y-2 pt-2 border-t border-separator/30">
              <Textarea
                label="Reviewer comment"
                rows={2}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
              <Textarea
                label="Edited clause text"
                rows={3}
                value={edit}
                onChange={(e) => setEdit(e.target.value)}
              />
              <div className="flex gap-2">
                <Button size="sm" disabled={busy} onClick={() => decide("accepted")}>
                  Accept
                </Button>
                <Button size="sm" variant="secondary" disabled={busy} onClick={() => decide("edited")}>
                  Save edit
                </Button>
                <Button size="sm" variant="danger" disabled={busy} onClick={() => decide("rejected")}>
                  Reject
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
