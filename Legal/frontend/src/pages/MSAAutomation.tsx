import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ContractTypeSelect } from "@/components/ContractTypeSelect";
import { DiffView, type DiffViewHandle } from "@/components/DiffView";
import { Icon } from "@/components/Icons";
import { NegotiationMemoryPanel } from "@/components/NegotiationMemoryPanel";
import { ReReviewPromptModal } from "@/components/ReReviewPromptModal";
import { ReviewOnboardingTour } from "@/components/review/ReviewOnboardingTour";
import {
  DocumentViewer,
  type DocumentViewerHandle,
  computeChangePages,
} from "@/components/DocumentViewer";
import { Markdown } from "@/components/Markdown";
import { MSADocumentEditor } from "@/components/MSADocumentEditor";
import { RedlinePreview, redlineStats } from "@/components/RedlinePreview";
import { isOfficeDoc, MSAOnlyOfficePanel } from "@/components/MSAOnlyOfficePanel";
import { Splitter } from "@/components/Splitter";
import { UploadZone } from "@/components/UploadZone";
import { VendorChangesPanel } from "@/components/VendorChangesPanel";
import { WorkflowTimeline } from "@/components/WorkflowTimeline";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import {
  ACTIONABLE_EDIT_INSTRUCTION_MESSAGE,
  EDIT_REFUSAL_MESSAGE,
  classNames,
  formatDate,
  isActionableEditInstruction,
  isSafeEditInstruction,
  lineDiffBlocks,
  statusColor,
} from "@/lib/utils";
import type {
  ContractTemplateSummary,
  DiffBlock,
  DocumentVersion,
  GmailMessageSummary,
  GmailStatus,
  GmailThread,
  MSADocxOperation,
  MSAGmailWatch,
  MSAPromptEditPreview,
  MSAPromptRevision,
  MSAPromptRevisionSummary,
  MSATracker,
  MSASummary,
  NegotiationChanges,
  ShareableUser,
  MSAShare,
} from "@/types";

const BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const QUICK_EDIT_PROMPTS = [
  "Make the liability cap mutual and limited to 12 months of fees",
  "Add a standard DPDP data-protection clause",
  "Change sole discretion to mutual agreement",
  "Tighten the termination-for-convenience notice to 30 days",
];

/** Nearby equal/other-side text so viewers can jump when this side has no hunk text (insert/delete). */
function nearestDiffContext(
  blocks: DiffBlock[] | undefined,
  index: number,
  side: "v1" | "v2",
): string | null {
  if (!blocks?.length) return null;
  for (let d = 1; d < blocks.length; d++) {
    for (const i of [index - d, index + d]) {
      if (i < 0 || i >= blocks.length) continue;
      const text = side === "v1" ? blocks[i].v1 : blocks[i].v2;
      if (text?.trim()) return text;
    }
  }
  return null;
}

export function MSAAutomationPage() {
  return (
    <Routes>
      <Route index element={<List />} />
      <Route path="start" element={<Start />} />
      <Route path="ingest" element={<Ingest />} />
      <Route path=":id" element={<Detail />} />
    </Routes>
  );
}

function List() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [rows, setRows] = useState<MSASummary[]>([]);
  const [gmail, setGmail] = useState<GmailStatus | null>(null);
  const [watches, setWatches] = useState<MSAGmailWatch[]>([]);
  const [pollNotice, setPollNotice] = useState<string | null>(null);
  const [pollBusy, setPollBusy] = useState(false);
  const [watchOpen, setWatchOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadWatches = useCallback(() => {
    if (!gmail?.connected) return;
    api.listMSAGmailWatches().then(setWatches).catch(() => setWatches([]));
  }, [gmail?.connected]);

  useEffect(() => {
    api
      .listMSA()
      .then(setRows)
      .finally(() => setLoading(false));
    api.gmailStatus().then(setGmail).catch(() => null);
  }, []);

  useEffect(() => {
    loadWatches();
  }, [loadWatches]);

  async function pollGmailNow() {
    setPollBusy(true);
    setPollNotice(null);
    try {
      const result = await api.pollGmail(false, true);
      const ingested = result.msa_ingested?.length ?? 0;
      const created = result.msa_auto_created?.length ?? 0;
      setPollNotice(
        `MSA poll: ${ingested} vendor doc(s) ingested, ${created} new negotiation(s) created.`,
      );
      setRows(await api.listMSA());
      loadWatches();
      if (created === 1 && result.msa_auto_created?.[0]?.tracker_id) {
        navigate(`/msa/${result.msa_auto_created[0].tracker_id}`);
      }
    } catch (err) {
      setPollNotice((err as Error).message);
    } finally {
      setPollBusy(false);
    }
  }

  const active = rows.filter((r) => r.status !== "executed").length;
  const highRisk = rows.filter((r) => (r.risk_score ?? 0) >= 70).length;
  const canCreate = hasPermission(user, "msa_automation");

  return (
    <div className="w-full max-w-none space-y-6 px-4 sm:px-6 lg:px-8 py-6 pb-10">
      <PageHeader
        eyebrow={
          <span className="inline-flex items-center gap-2">
            <Icon.Workflow className="w-4 h-4" aria-hidden />
            UC-05 · Vendor contract automation
          </span>
        }
        title="MSA / NDA Automation"
        subtitle={
          <>
            Upload, edit with AI, redline, send, and track every vendor negotiation in one workspace.
            {gmail?.connected && (
              <span className="mt-2 inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-accent/10 text-accent text-caption">
                <Icon.Mail className="w-3.5 h-3.5" aria-hidden />
                Gmail connected · {gmail.email}
              </span>
            )}
          </>
        }
        actions={
          canCreate ? (
          <div className="flex gap-2 shrink-0 flex-wrap">
            {gmail?.connected && (
              <>
                <Button
                  variant="secondary"
                  disabled={pollBusy}
                  onClick={pollGmailNow}
                  title="Check your watched vendor threads now for new contract attachments and ingest them."
                >
                  <Icon.Mail className="w-4 h-4 mr-1.5" aria-hidden />
                  Poll Gmail
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setWatchOpen(true)}
                  title="Search your inbox and pick a vendor email thread to watch — no thread ID needed."
                >
                  Watch vendor thread
                </Button>
              </>
            )}
            <Link to="start">
              <Button>
                <Icon.Plus className="w-4 h-4 mr-1.5" aria-hidden />
                New negotiation
              </Button>
            </Link>
            <Link to="ingest">
              <Button variant="secondary">
                <Icon.Mail className="w-4 h-4 mr-1.5" aria-hidden />
                Simulate ingest
              </Button>
            </Link>
          </div>
          ) : undefined
        }
      />

      {gmail?.connected && <GmailFlowInfo />}

      {pollNotice && (
        <div className="rounded-lg border border-separator/30 bg-bg-secondary px-4 py-3 text-sm text-label-secondary">
          {pollNotice}
        </div>
      )}

      {gmail?.connected && watches.length > 0 && (
        <Card title="Watched vendor threads" className="shadow-card">
          <p className="text-sm text-label-secondary mb-3">
            New vendor docx attachments in these threads are auto-ingested and AI-reviewed on poll.
          </p>
          <ul className="space-y-2">
            {watches.map((w) => (
              <li
                key={w.thread_id}
                className="flex flex-wrap items-center justify-between gap-2 border border-separator/20 rounded-lg px-3 py-2"
              >
                <div>
                  <div className="text-sm font-medium text-label">{w.subject || "Gmail thread"}</div>
                  <div className="text-xs text-label-secondary">
                    {w.tracker_id ? `Linked to MSA #${w.tracker_id}` : "Waiting for first vendor docx"}
                  </div>
                </div>
                {w.tracker_id ? (
                  <Link to={`/msa/${w.tracker_id}`} className="text-xs text-accent hover:underline">
                    Open negotiation
                  </Link>
                ) : (
                  <Badge className="bg-amber-100 text-amber-800">Auto-create on ingest</Badge>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {watchOpen && (
        <MSAGmailWatchPicker
          onClose={() => setWatchOpen(false)}
          onWatch={async (threadId, subject) => {
            await api.watchMSAGmailThread({ thread_id: threadId, subject });
            loadWatches();
            setWatchOpen(false);
            setPollNotice("Thread watched — vendor docx will auto-ingest on next poll.");
          }}
        />
      )}

      {/* Stat strip */}
      {rows.length > 0 && (
        <section className="grid grid-cols-3 gap-3 md:gap-4">
          <StatPill label="Total negotiations" value={rows.length} accent="text-label-secondary bg-bg-secondary" />
          <StatPill label="Active" value={active} accent="text-blue-700 bg-blue-50" />
          <StatPill label="High risk" value={highRisk} accent="text-error bg-red-50" />
        </section>
      )}

      <Card className="shadow-card">
        {loading ? (
          <div className="py-10 text-center text-sm text-label-secondary">Loading negotiations…</div>
        ) : rows.length === 0 ? (
          <div className="py-14 text-center">
            <Icon.Workflow className="w-12 h-12 mx-auto text-label-tertiary mb-3" />
            <p className="text-label-secondary font-medium">No MSA / NDA threads yet</p>
            <p className="text-sm text-label-secondary mt-1 max-w-md mx-auto">
              Start a negotiation to upload your first contract, run AI review, and edit it in
              plain language.
            </p>
            <Link to="start" className="inline-block mt-4">
              <Button>Start your first negotiation</Button>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto -mx-5">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-label-secondary border-b border-separator/30">
                <tr>
                  <th className="py-3 px-5 font-medium">Vendor</th>
                  <th className="py-3 font-medium">Type</th>
                  <th className="py-3 font-medium">Status</th>
                  <th className="py-3 font-medium">Risk</th>
                  <th className="py-3 font-medium">Updated</th>
                  <th className="py-3 px-5" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-separator/20 hover:bg-bg-secondary/80 transition-colors">
                    <td className="py-3.5 px-5 font-medium text-label">
                      {r.vendor_name}
                      {r.my_access_level && r.my_access_level !== "owner" && (
                        <Badge className="ml-2 bg-violet-100 text-violet-800 border-violet-200">
                          Shared with you
                        </Badge>
                      )}
                    </td>
                    <td className="py-3.5">
                      <Badge className="bg-bg-secondary text-label-secondary border-separator/40">
                        {r.contract_type}
                      </Badge>
                    </td>
                    <td className="py-3.5">
                      <Badge className={statusColor(r.status)}>{r.status.replace(/_/g, " ")}</Badge>
                    </td>
                    <td className="py-3.5">
                      {r.risk_score != null ? (
                        <span
                          className={classNames(
                            "font-semibold tabular-nums",
                            r.risk_score >= 70
                              ? "text-error"
                              : r.risk_score >= 40
                                ? "text-amber-700"
                                : "text-emerald-700",
                          )}
                        >
                          {r.risk_score}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-3.5 text-label-secondary tabular-nums">{formatDate(r.updated_at)}</td>
                    <td className="py-3.5 px-5 text-right">
                      <Link
                        to={`${r.id}`}
                        className="inline-flex items-center gap-1 text-accent hover:text-accent font-medium"
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

function StatPill({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="rounded-xl bg-bg border border-separator/40 shadow-card p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-label-secondary">{label}</span>
        <span className={classNames("rounded-md px-2 py-0.5 text-xs font-semibold", accent)}>
          {value}
        </span>
      </div>
      <div className="mt-2 text-2xl font-semibold text-label tabular-nums">{value}</div>
    </div>
  );
}

function Start() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [templates, setTemplates] = useState<ContractTemplateSummary[]>([]);
  const [form, setForm] = useState({
    vendor_name: "",
    vendor_email: "",
    contract_type: "MSA",
    template_id: searchParams.get("template") || "",
    base_text: "",
    review_guidelines: "",
  });
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<"upload" | "template" | "paste">("upload");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listContractTemplates(form.contract_type).then(setTemplates);
  }, [form.contract_type]);

  async function startNegotiation(skipAiReview: boolean) {
    setBusy(true);
    setError(null);
    try {
      let tracker: MSATracker;
      if (source === "upload" && file) {
        const fd = new FormData();
        fd.append("vendor_name", form.vendor_name);
        fd.append("vendor_email", form.vendor_email);
        fd.append("contract_type", form.contract_type);
        fd.append("skip_ai_review", skipAiReview ? "true" : "false");
        if (form.template_id) fd.append("template_id", form.template_id);
        if (form.review_guidelines.trim()) {
          fd.append("review_guidelines", form.review_guidelines);
        }
        fd.append("file", file);
        tracker = await api.startMSAUpload(fd);
      } else {
        tracker = await api.startMSA({
          vendor_name: form.vendor_name,
          vendor_email: form.vendor_email,
          contract_type: form.contract_type,
          skip_ai_review: skipAiReview,
          template_id: source === "template" && form.template_id ? Number(form.template_id) : null,
          base_text: source === "paste" ? form.base_text : null,
          review_guidelines: form.review_guidelines.trim() || null,
        });
      }
      navigate(`../${tracker.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const canSubmit =
    !!form.vendor_name &&
    !!form.vendor_email &&
    !!form.contract_type.trim() &&
    ((source === "upload" && !!file) ||
      (source === "template" && !!form.template_id) ||
      (source === "paste" && !!form.base_text.trim()));

  return (
    <div className="w-full max-w-none space-y-5 px-4 sm:px-6 lg:px-8 py-6 pb-10">
      <Link to=".." className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
        ← Back to negotiations
      </Link>
      <div>
        <h1 className="text-2xl font-semibold text-label">Start a new negotiation</h1>
        <p className="text-sm text-label-secondary mt-1 max-w-3xl">
          Upload your MSA / NDA document to begin. AI reviews each clause and flags risks before
          you send it to the vendor. You can also start from a template or pasted text.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          startNegotiation(false);
        }}
        className="space-y-5 max-w-5xl"
      >
        <Card title="Vendor details">
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Vendor name"
              value={form.vendor_name}
              onChange={(e) => setForm((f) => ({ ...f, vendor_name: e.target.value }))}
              required
              placeholder="Acme Pvt Ltd"
            />
            <Input
              label="Vendor email"
              type="email"
              value={form.vendor_email}
              onChange={(e) => setForm((f) => ({ ...f, vendor_email: e.target.value }))}
              required
              placeholder="legal@acme.com"
            />
            <ContractTypeSelect
              className="col-span-2"
              value={form.contract_type}
              onChange={(contract_type) =>
                setForm((f) => ({ ...f, contract_type, template_id: "" }))
              }
            />
          </div>
        </Card>

        <Card
          title="Ground truth checks"
          subtitle="Add exact names, spellings, or non-negotiable facts the AI should verify."
        >
          <Textarea
            label="Required wording / guidelines"
            rows={4}
            value={form.review_guidelines}
            onChange={(e) => setForm((f) => ({ ...f, review_guidelines: e.target.value }))}
            placeholder={"Jio Finance Platform and Service Limited\nJFPSL\nRegistered office: Maker Maxity, Bandra Kurla Complex"}
          />
          <p className="mt-2 text-xs text-label-secondary">
            Put one required item per line. Missing exact terms appear as high-risk findings, useful
            for catching wrong entity names, JFPSL spelling, addresses, and dates.
          </p>
        </Card>

        <Card
          title="Base document"
          subtitle="Upload your contract to start — or use a template / pasted text."
        >
          <div className="grid grid-cols-3 gap-2 mb-4">
            <SourceTab
              active={source === "upload"}
              onClick={() => setSource("upload")}
              title="Upload file"
              desc="PDF, DOCX, or TXT — recommended"
              icon={<Icon.Documents className="w-5 h-5" />}
            />
            <SourceTab
              active={source === "template"}
              onClick={() => setSource("template")}
              title="From template"
              desc={`${templates.length} ${form.contract_type} template${templates.length === 1 ? "" : "s"}`}
              icon={<Icon.ContractReview className="w-5 h-5" />}
            />
            <SourceTab
              active={source === "paste"}
              onClick={() => setSource("paste")}
              title="Paste text"
              desc="For quick experiments"
              icon={<Icon.Pencil className="w-5 h-5" />}
            />
          </div>

          {source === "upload" && (
            <UploadZone
              file={file}
              onFile={setFile}
              label="Drop your MSA / NDA here, or click to browse"
              hint="PDF, DOCX, or TXT · up to 50 MB · large documents are fully supported"
            />
          )}

          {source === "template" && (
            <div className="space-y-3">
              <Select
                label="Template"
                value={form.template_id}
                onChange={(e) => setForm((f) => ({ ...f, template_id: e.target.value }))}
              >
                <option value="">— Select a template —</option>
                {templates.map((t) => (
                  <option key={t.id} value={String(t.id)}>
                    {t.name}
                  </option>
                ))}
              </Select>
              <p className="text-xs text-label-secondary">
                Don't see what you need?{" "}
                <Link to="/contract-templates" className="text-accent hover:underline">
                  Manage templates
                </Link>
              </p>
            </div>
          )}

          {source === "paste" && (
            <Textarea
              label="Base text"
              rows={12}
              value={form.base_text}
              onChange={(e) => setForm((f) => ({ ...f, base_text: e.target.value }))}
              placeholder="Paste the MSA / NDA text here…"
            />
          )}
        </Card>

        {error && (
          <div className="border border-error/20 bg-red-50 rounded-md px-3 py-2 text-sm text-error">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={() => navigate("..")}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={busy || !canSubmit}
            onClick={() => startNegotiation(true)}
          >
            {busy ? "Saving…" : "Save as draft"}
          </Button>
          <Button type="submit" disabled={busy || !canSubmit}>
            {busy ? "Uploading & running AI review…" : "Start with AI review"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function SourceTab({
  active,
  onClick,
  title,
  desc,
  icon,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  desc: string;
  icon: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={classNames(
        "text-left rounded-xl border-2 p-3.5 transition",
        active
          ? "border-accent bg-accent/10 shadow-sm"
          : "border-separator/40 bg-bg hover:border-separator/60 hover:bg-bg-secondary",
      )}
    >
      <div className="flex items-center gap-2.5 mb-1.5">
        <span
          className={classNames(
            "rounded-lg p-1.5 transition-colors",
            active ? "bg-accent text-white" : "bg-bg-secondary text-label-secondary",
          )}
        >
          {icon}
        </span>
        <span className="text-sm font-semibold text-label">{title}</span>
      </div>
      <p className="text-xs text-label-secondary">{desc}</p>
    </button>
  );
}

function Ingest() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    vendor_name: "",
    vendor_email: "",
    contract_type: "MSA",
    subject: "",
    body: "",
    attachment_name: "",
    attachment_text: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function up<K extends keyof typeof form>(k: K, v: string) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const tracker = await api.ingestMSA({ ...form });
      navigate(`../${tracker.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-none space-y-5 px-4 sm:px-6 lg:px-8 py-6">
      <h1 className="text-2xl font-semibold text-label">Simulate Gmail ingest</h1>
      <Card className="max-w-5xl">
        <form className="space-y-3" onSubmit={submit}>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Vendor name" value={form.vendor_name} onChange={(e) => up("vendor_name", e.target.value)} required />
            <Input label="Vendor email" type="email" value={form.vendor_email} onChange={(e) => up("vendor_email", e.target.value)} required />
          </div>
          <ContractTypeSelect
            value={form.contract_type}
            onChange={(contract_type) => up("contract_type", contract_type)}
          />
          <Input label="Subject" value={form.subject} onChange={(e) => up("subject", e.target.value)} required />
          <Textarea label="Body" rows={4} value={form.body} onChange={(e) => up("body", e.target.value)} required />
          <Input label="Attachment name" value={form.attachment_name} onChange={(e) => up("attachment_name", e.target.value)} required />
          <Textarea label="Attachment text" rows={12} value={form.attachment_text} onChange={(e) => up("attachment_text", e.target.value)} required />
          {error && <p className="text-sm text-error">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => navigate("..")}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Ingesting…" : "Ingest"}</Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

function sourceLabel(s: string): string {
  const map: Record<string, string> = {
    legal_base: "Legal base",
    legal_redline: "Legal redline",
    vendor_return: "Vendor return",
    executed_final: "Executed",
  };
  return map[s] || s;
}

function sourceBadgeClass(s: string): string {
  const map: Record<string, string> = {
    legal_base: "bg-bg-secondary text-label-secondary",
    legal_redline: "bg-blue-100 text-blue-800",
    vendor_return: "bg-amber-100 text-amber-800",
    executed_final: "bg-emerald-100 text-emerald-800",
  };
  return map[s] || "bg-bg-secondary text-label-secondary";
}

function Detail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [tracker, setTracker] = useState<MSATracker | null>(null);
  const [versions, setVersions] = useState<DocumentVersion[]>([]);
  const [changes, setChanges] = useState<NegotiationChanges | null>(null);
  const [gmail, setGmail] = useState<GmailStatus | null>(null);
  const [activeView, setActiveView] = useState<
    "workspace" | "edit" | "direct-edit" | "email"
  >("workspace");
  const [showAiAnalysis, setShowAiAnalysis] = useState(false);
  const [editorText, setEditorText] = useState("");
  const [uploadingVendor, setUploadingVendor] = useState(false);
  const [vendorReturnFile, setVendorReturnFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [reReviewVersion, setReReviewVersion] = useState<number | null>(null);
  const [pollNotice, setPollNotice] = useState<string | null>(null);
  const [pollBusy, setPollBusy] = useState(false);
  const [watchOpen, setWatchOpen] = useState(false);
  const diffRef = useRef<DiffViewHandle>(null);
  const leftViewerRef = useRef<DocumentViewerHandle>(null);
  const rightViewerRef = useRef<DocumentViewerHandle>(null);

  const load = useCallback(async () => {
    if (!id) return;
    const tid = Number(id);
    const [t, v, c] = await Promise.all([
      api.getMSA(tid),
      api.listMSAVersions(tid),
      api.getMSAChanges(tid),
    ]);
    setTracker(t);
    setVersions(v);
    setChanges(c);
  }, [id]);

  const promptReReview = useCallback((versionNumber: number) => {
    setReReviewVersion(versionNumber);
  }, []);

  async function runReReview() {
    if (!tracker || reReviewVersion == null) return;
    setReviewBusy(true);
    try {
      const version = versions.find((v) => v.version_number === reReviewVersion);
      const updated = await api.runMSAReview(tracker.id, {
        version_id: version?.id,
      });
      setTracker(updated);
      setReReviewVersion(null);
      await load();
    } finally {
      setReviewBusy(false);
    }
  }

  useEffect(() => {
    load();
    api.gmailStatus().then(setGmail).catch(() => null);
  }, [load]);

  // Resolve the two latest versions to display side-by-side, plus their text.
  const [leftText, setLeftText] = useState<string>("");
  const [rightText, setRightText] = useState<string>("");
  const { leftVersion, rightVersion } = useMemo(() => {
    if (versions.length === 0) return { leftVersion: null, rightVersion: null };
    const sorted = [...versions].sort((a, b) => a.version_number - b.version_number);
    const right = sorted[sorted.length - 1];
    // Prefer the most recent non-same-source version on the left; fall back to prior version.
    let left: DocumentVersion | null = null;
    for (let i = sorted.length - 2; i >= 0; i--) {
      if (sorted[i].source !== right.source) {
        left = sorted[i];
        break;
      }
    }
    if (!left && sorted.length >= 2) left = sorted[sorted.length - 2];
    return { leftVersion: left, rightVersion: right };
  }, [versions]);

  useEffect(() => {
    async function loadText(v: DocumentVersion | null): Promise<string> {
      if (!v) return "";
      try {
        return await fetchVersionText(v);
      } catch {
        return "";
      }
    }
    loadText(leftVersion).then(setLeftText);
    loadText(rightVersion).then(setRightText);
  }, [leftVersion, rightVersion]);

  const latestLegal = useMemo(() => {
    const legal = versions
      .filter((v) => v.source === "legal_redline" || v.source === "legal_base")
      .sort((a, b) => b.version_number - a.version_number);
    return legal[0] ?? null;
  }, [versions]);

  useEffect(() => {
    if (!latestLegal) {
      setEditorText("");
      return;
    }
    fetchVersionText(latestLegal).then(setEditorText).catch(() => setEditorText(""));
  }, [latestLegal?.id]);

  // Map diff_index → estimated page in left/right viewer.
  // IMPORTANT: keep all hooks above the early-return below — moving them after
  // `if (!tracker)` breaks the Rules of Hooks and blanks the screen.
  const leftChangePages = useMemo(
    () => computeChangePages(leftText, (changes?.llm_narrative || []).map((n) => ({ diff_index: n.diff_index, old_text: n.old_text, new_text: n.old_text, severity: n.severity }))),
    [leftText, changes],
  );
  const rightChangePages = useMemo(
    () => computeChangePages(rightText, (changes?.llm_narrative || []).map((n) => ({ diff_index: n.diff_index, old_text: n.new_text, new_text: n.new_text, severity: n.severity }))),
    [rightText, changes],
  );
  const leftMarkers = useMemo(
    () => Array.from(leftChangePages.values()).map((v) => ({ page: v.page, severity: v.severity })),
    [leftChangePages],
  );
  const rightMarkers = useMemo(
    () => Array.from(rightChangePages.values()).map((v) => ({ page: v.page, severity: v.severity })),
    [rightChangePages],
  );

  // Non-equal hunks in the inline DiffView — used for Prev/Next jump controls.
  const diffChangeIndices = useMemo(
    () =>
      (changes?.diff_blocks ?? []).reduce<number[]>((acc, b, i) => {
        if (b.kind !== "equal") acc.push(i);
        return acc;
      }, []),
    [changes],
  );
  const [diffJumpCursor, setDiffJumpCursor] = useState(0);

  useEffect(() => {
    setDiffJumpCursor(0);
  }, [changes?.comparison_id]);

  if (!tracker) return <div className="text-label-secondary text-sm">Loading…</div>;

  const accessLevel =
    tracker.my_access_level ?? (hasPermission(user, "msa_automation") ? "owner" : null);
  const isOwner = accessLevel === "owner";
  const isViewOnly = accessLevel === "view";
  const canApprove =
    !isViewOnly &&
    (accessLevel === "edit" || (isOwner && hasPermission(user, "approve_ai_output")));
  const canSend = isOwner && hasPermission(user, "send_email");
  const canUpload = isOwner && tracker.status !== "executed";
  const hasAiReview = (tracker.ai_suggestions?.length ?? 0) > 0;
  const canAskBot = hasPermission(user, "legal_bot_use");

  async function handleVendorUpload() {
    if (!vendorReturnFile || !tracker) return;
    setUploadingVendor(true);
    setUploadError(null);
    try {
      const fd = new FormData();
      fd.append("file", vendorReturnFile);
      fd.append("source", "vendor_return");
      await api.uploadMSAVersion(tracker.id, fd);
      setVendorReturnFile(null);
      await load();
    } catch (e) {
      setUploadError((e as Error).message);
    } finally {
      setUploadingVendor(false);
    }
  }

  function jumpToDiff(index: number) {
    // Keep the Prev/Next cursor in sync when jumping from the changes list.
    const cursorIdx = diffChangeIndices.indexOf(index);
    if (cursorIdx >= 0) setDiffJumpCursor(cursorIdx);

    // Scroll to the inline-diff card first so the hunk is on screen.
    document.getElementById("diff-anchor")?.scrollIntoView({ behavior: "smooth", block: "start" });

    // 1. Scroll both columns of the inline diff to this change
    window.setTimeout(() => diffRef.current?.scrollToIndex(index), 80);

    // 2. Scroll each document viewer to the page containing the change
    const leftMeta = leftChangePages.get(index);
    const rightMeta = rightChangePages.get(index);
    if (leftMeta) leftViewerRef.current?.scrollToPage(leftMeta.page);
    if (rightMeta) rightViewerRef.current?.scrollToPage(rightMeta.page);

    // 3. Text fallbacks — use narrative + raw diff-block text so both sides move
    const item = (changes?.llm_narrative || []).find((n) => n.diff_index === index);
    const block = changes?.diff_blocks?.[index];
    const leftNeedle =
      item?.old_text ||
      block?.v1 ||
      // Inserts have no v1 — jump to nearby context in the older version
      nearestDiffContext(changes?.diff_blocks, index, "v1");
    const rightNeedle =
      item?.new_text ||
      block?.v2 ||
      nearestDiffContext(changes?.diff_blocks, index, "v2");

    window.setTimeout(() => {
      if (leftNeedle) leftViewerRef.current?.scrollToText(leftNeedle);
      if (rightNeedle) rightViewerRef.current?.scrollToText(rightNeedle);
    }, 120);
  }

  function jumpDiffStep(step: number) {
    if (diffChangeIndices.length === 0) return;
    const next =
      (diffJumpCursor + step + diffChangeIndices.length) % diffChangeIndices.length;
    setDiffJumpCursor(next);
    jumpToDiff(diffChangeIndices[next]);
  }

  const docsPane = (
    <div className="h-full p-2">
      {leftVersion ? (
        <Splitter initial={50} min={20} storageKey="msa-workspace-docs">
          <div className="h-full pr-1">
            <DocumentViewer
              ref={leftViewerRef}
              storageKey={leftVersion.storage_key}
              mimeType={leftVersion.mime_type}
              filename={leftVersion.filename}
              extractedText={leftText}
              title={`v${leftVersion.version_number} — ${sourceLabel(leftVersion.source)}`}
              badge={
                <Badge className={sourceBadgeClass(leftVersion.source)}>
                  v{leftVersion.version_number}
                </Badge>
              }
              changeMarkers={leftMarkers}
              onlyofficeTrackerId={tracker.id}
              onlyofficeVersionId={leftVersion.id}
            />
          </div>
          <div className="h-full pl-1">
            <DocumentViewer
              ref={rightViewerRef}
              storageKey={rightVersion!.storage_key}
              mimeType={rightVersion!.mime_type}
              filename={rightVersion!.filename}
              extractedText={rightText}
              title={`v${rightVersion!.version_number} — ${sourceLabel(rightVersion!.source)}`}
              badge={
                <Badge className={sourceBadgeClass(rightVersion!.source)}>
                  v{rightVersion!.version_number}
                </Badge>
              }
              changeMarkers={rightMarkers}
              onlyofficeTrackerId={tracker.id}
              onlyofficeVersionId={rightVersion!.id}
            />
          </div>
        </Splitter>
      ) : rightVersion ? (
        <DocumentViewer
          ref={rightViewerRef}
          storageKey={rightVersion.storage_key}
          mimeType={rightVersion.mime_type}
          filename={rightVersion.filename}
          extractedText={rightText}
          title={`v${rightVersion.version_number} — ${sourceLabel(rightVersion.source)}`}
          badge={
            <Badge className={sourceBadgeClass(rightVersion.source)}>
              v{rightVersion.version_number}
            </Badge>
          }
          changeMarkers={rightMarkers}
          onlyofficeTrackerId={tracker.id}
          onlyofficeVersionId={rightVersion.id}
        />
      ) : null}
    </div>
  );

  const vendorAnalysisPane = (
    <div className="h-full p-2 overflow-auto">
      <VendorChangesPanel
        changes={changes}
        onJumpToDiff={jumpToDiff}
        changePages={rightChangePages}
        canAct={canApprove}
        onSaveVersion={async (decisions) => {
          if (!changes || !rightVersion) return;
          const toVersion =
            versions.find((v) => v.version_number === changes.to_version_number) ??
            rightVersion;
          if (!toVersion) return;
          const parts: string[] = [];
          changes.diff_blocks.forEach((b, i) => {
            if (b.kind === "equal") {
              if (b.v2) parts.push(b.v2);
              return;
            }
            const d = decisions[i];
            if (d?.action === "edit" && d.text.trim()) {
              parts.push(d.text);
            } else if (d?.action === "reject") {
              if (b.v1) parts.push(b.v1);
            } else if (b.v2) {
              parts.push(b.v2);
            }
          });
          const updated = await api.applyMSAHumanEdit(tracker.id, {
            parent_version_id: toVersion.id,
            edited_text: parts.join("\n"),
          });
          await load();
          promptReReview(updated.current_version);
        }}
      />
    </div>
  );

  return (
    <div className="w-full max-w-none space-y-5 px-4 sm:px-6 lg:px-8 py-6 pb-10">
      <Link to=".." className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
        ← Back to negotiations
      </Link>

      {/* Header card */}
      <div className="rounded-2xl border border-separator/40 bg-bg shadow-card p-5 md:p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-start gap-4 min-w-0">
            <div className="w-12 h-12 rounded-xl bg-accent text-white flex items-center justify-center shrink-0">
              <Icon.Workflow className="w-6 h-6" />
            </div>
            <div className="min-w-0">
              <h1 className="text-xl font-semibold text-label truncate">{tracker.vendor_name}</h1>
              <p className="text-sm text-label-secondary truncate">{tracker.vendor_email}</p>
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                <Badge className={statusColor(tracker.status)}>
                  {tracker.status.replace(/_/g, " ")}
                </Badge>
                <span className="text-xs text-label-secondary px-2 py-0.5 rounded-full bg-bg-secondary">
                  v{tracker.current_version} · {tracker.contract_type}
                </span>
              </div>
            </div>
          </div>
          <div className="flex gap-2 flex-shrink-0 flex-wrap justify-end">
            {isOwner && (
              <Button variant="secondary" size="sm" onClick={() => setShareOpen(true)}>
                <Icon.Users className="w-4 h-4 mr-1" />
                Share
              </Button>
            )}
            {canAskBot && latestLegal && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  navigate(
                    `/jiolegal?msa=${tracker.id}&version=${latestLegal.id}&label=${encodeURIComponent(`${tracker.vendor_name} · v${latestLegal.version_number}`)}`,
                  )
                }
              >
                <Icon.Chat className="w-4 h-4 mr-1" />
                Ask about this document
              </Button>
            )}
            {isViewOnly && (
              <Badge className="bg-violet-100 text-violet-800">Read-only access</Badge>
            )}
            {accessLevel === "edit" && !isOwner && (
              <Badge className="bg-blue-100 text-blue-800">Shared edit access</Badge>
            )}
            {gmail?.configured && !gmail.connected && (
              <Button
                variant="secondary"
                size="sm"
                onClick={async () => {
                  const { authorization_url } = await api.gmailOAuthStart("settings");
                  window.location.href = authorization_url;
                }}
              >
                Connect Gmail
              </Button>
            )}
            {gmail?.connected && (
              <Button
                variant="secondary"
                size="sm"
                disabled={pollBusy}
                title="Check this negotiation's linked vendor thread now for a new contract attachment and ingest it."
                onClick={async () => {
                  setPollBusy(true);
                  setPollNotice(null);
                  try {
                    const result = await api.pollGmail(false, true);
                    const ingested = result.msa_ingested?.length ?? 0;
                    const created = result.msa_auto_created?.length ?? 0;
                    setPollNotice(
                      `MSA poll: ${ingested} vendor doc(s) ingested, ${created} new negotiation(s) created.`,
                    );
                    await load();
                  } catch (err) {
                    setPollNotice((err as Error).message);
                  } finally {
                    setPollBusy(false);
                  }
                }}
              >
                Poll Gmail
              </Button>
            )}
            {canApprove && tracker.status !== "executed" && (
              <Button
                size="sm"
                onClick={async () => {
                  await api.finalizeMSA(tracker.id);
                  load();
                }}
              >
                <Icon.Check className="w-4 h-4 mr-1" />
                Mark executed
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Workflow timeline */}
      <WorkflowTimeline status={tracker.status} />

      {tracker.status === "draft" && !hasAiReview && isOwner && (
        <div className="rounded-xl border border-accent/20 bg-accent/5 p-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-label">Saved as draft</p>
            <p className="text-xs text-label-secondary mt-0.5">
              Run AI review when you are ready to analyse clauses and generate suggestions.
            </p>
          </div>
          <Button
            size="sm"
            disabled={reviewBusy}
            onClick={async () => {
              setReviewBusy(true);
              try {
                const updated = await api.runMSAReview(tracker.id);
                setTracker(updated);
                await load();
              } finally {
                setReviewBusy(false);
              }
            }}
          >
            {reviewBusy ? "Running review…" : "Run AI review"}
          </Button>
        </div>
      )}

      {shareOpen && isOwner && (
        <MSASharePanel tracker={tracker} onClose={() => setShareOpen(false)} onUpdated={load} />
      )}

      {reReviewVersion != null && (
        <ReReviewPromptModal
          versionNumber={reReviewVersion}
          busy={reviewBusy}
          onRun={runReReview}
          onDismiss={() => setReReviewVersion(null)}
        />
      )}

      {/* Negotiation memory — keep; risk stats / AI suggestions chrome hidden for now */}
      <NegotiationMemoryPanel trackerId={tracker.id} />

      <ReviewOnboardingTour />

      {/* View tabs */}
      <div className="border-b border-separator/40 flex gap-1 overflow-x-auto scrollbar-thin">
        <ViewTab active={activeView === "workspace"} onClick={() => setActiveView("workspace")}>
          Document workspace
        </ViewTab>
        <ViewTab active={activeView === "edit"} onClick={() => setActiveView("edit")}>
          ✨ Ask AI to edit
        </ViewTab>
        <ViewTab active={activeView === "direct-edit"} onClick={() => setActiveView("direct-edit")}>
          Edit document
        </ViewTab>
        <ViewTab active={activeView === "email"} onClick={() => setActiveView("email")}>
          Email ({tracker.emails.length})
        </ViewTab>
      </div>

      {activeView === "workspace" && (
        <div className="space-y-5">
          {/* Vendor return upload — prominent CTA */}
          {canUpload && (
            <Card
              title="Vendor return"
              subtitle="Upload the vendor's edited document — AI will highlight every change and recommend actions."
              actions={
                <Badge className={statusColor(tracker.status)}>
                  Next: {nextAction(tracker.status)}
                </Badge>
              }
            >
              <UploadZone
                file={vendorReturnFile}
                onFile={setVendorReturnFile}
                disabled={uploadingVendor}
                label="Drop the vendor's signed/edited PDF or DOCX here"
                hint="AI will diff it against the last legal version and flag risky changes"
                compact={!!vendorReturnFile}
              />
              {uploadError && (
                <p className="text-xs text-error mt-2">{uploadError}</p>
              )}
              {vendorReturnFile && (
                <div className="mt-3 flex justify-end">
                  <Button onClick={handleVendorUpload} disabled={uploadingVendor}>
                    {uploadingVendor ? "Analyzing changes…" : "Upload & analyze changes"}
                  </Button>
                </div>
              )}
            </Card>
          )}

          {/* Document workspace — docs full width; AI analysis on demand */}
          {rightVersion && (
            <>
              <div className="flex items-center justify-end gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => setShowAiAnalysis((v) => !v)}
                >
                  {showAiAnalysis ? "Hide counsel analysis" : "Show counsel analysis"}
                </Button>
              </div>
              <div className="border border-separator/40 rounded-lg bg-bg" style={{ height: 720 }}>
                {showAiAnalysis ? (
                  <Splitter initial={60} min={25} storageKey="msa-workspace-main">
                    {docsPane}
                    {vendorAnalysisPane}
                  </Splitter>
                ) : (
                  docsPane
                )}
              </div>

              <div id="diff-anchor" />
              {changes && changes.comparison_id && (
                <Card
                  title={`Inline diff · v${changes.from_version_number} → v${changes.to_version_number}`}
                  subtitle={changes.summary_report || undefined}
                  actions={
                    <div className="flex items-center gap-2 flex-wrap justify-end">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs text-label-secondary whitespace-nowrap">
                          {diffChangeIndices.length === 0
                            ? "No changes"
                            : `Change ${Math.min(diffJumpCursor + 1, diffChangeIndices.length)} of ${diffChangeIndices.length}`}
                        </span>
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={diffChangeIndices.length === 0}
                          onClick={() => jumpDiffStep(-1)}
                          title="Previous change"
                        >
                          ↑ Prev
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={diffChangeIndices.length === 0}
                          onClick={() => jumpDiffStep(1)}
                          title="Next change"
                        >
                          Next ↓
                        </Button>
                      </div>
                      {versions.length >= 2 && (
                        <VersionPicker
                          versions={versions}
                          currentFrom={changes.from_version_number}
                          currentTo={changes.to_version_number}
                          onCompare={async (fromId, toId) => {
                            const next = await api.compareMSAVersions(tracker.id, fromId, toId);
                            setChanges(next);
                          }}
                        />
                      )}
                    </div>
                  }
                >
                  <p className="text-xs text-label-tertiary mb-2">
                    Use Prev / Next to jump straight to each change in the diff and document viewers —
                    no need to scroll looking for highlights.
                  </p>
                  <DiffView
                    ref={diffRef}
                    v1Label={`v${changes.from_version_number} (legal)`}
                    v2Label={`v${changes.to_version_number} (vendor)`}
                    blocks={changes.diff_blocks}
                    height={420}
                  />
                </Card>
              )}

              <Card title="Version timeline">
                <ul className="space-y-1.5">
                  {versions.map((v) => (
                    <li
                      key={v.id}
                      className="flex items-center justify-between border border-separator/30 rounded px-3 py-2 hover:bg-bg-secondary"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-mono text-sm font-semibold">v{v.version_number}</span>
                        <Badge className={sourceBadgeClass(v.source)}>{sourceLabel(v.source)}</Badge>
                        {v.filename && (
                          <span className="text-xs text-label-secondary truncate">{v.filename}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 flex-shrink-0">
                        <span className="text-xs text-label-secondary">{formatDate(v.created_at)}</span>
                        {v.storage_key && (
                          <button
                            type="button"
                            className="text-xs text-accent hover:underline"
                            onClick={() => downloadFile(v.storage_key!)}
                          >
                            Download
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </Card>

              {tracker.redlined_text && canSend && tracker.status === "redlined" && (
                <Card title={`Send redline v${tracker.current_version}`}>
                  <SendBox trackerId={tracker.id} vendorName={tracker.vendor_name} onSent={load} />
                </Card>
              )}
            </>
          )}

          {!rightVersion && (
            <Card>
              <div className="text-sm text-label-secondary py-4 text-center">
                Waiting for the first version. If you just started this negotiation, refresh in a
                moment.
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Kept mounted (hidden when inactive) so the instruction / scope / edited
          text typing boxes are preserved when the user switches tabs. */}
      <div className={activeView === "edit" ? "" : "hidden"}>
        <MSAEditPanel
          tracker={tracker}
          versions={versions}
          canApprove={canApprove}
          onApplied={async () => {
            const updated = await api.getMSA(tracker.id);
            await load();
            setActiveView("workspace");
            promptReReview(updated.current_version);
          }}
        />
      </div>

      {activeView === "direct-edit" && (
        latestLegal ? (
          isOfficeDoc(latestLegal) ? (
            <MSAOnlyOfficePanel
              trackerId={tracker.id}
              version={latestLegal}
              mode="edit"
              canEdit={canApprove && tracker.status !== "executed"}
              onSaved={async () => {
                const updated = await api.getMSA(tracker.id);
                await load();
                setActiveView("workspace");
                promptReReview(updated.current_version);
              }}
            />
          ) : (
            <MSADocumentEditor
              version={latestLegal}
              initialText={editorText}
              canSave={canApprove}
              disabled={tracker.status === "executed"}
              onSave={async (editedText, richHtml) => {
                const updated = await api.applyMSAHumanEdit(tracker.id, {
                  parent_version_id: latestLegal.id,
                  edited_text: editedText,
                  rich_html: richHtml,
                });
                await load();
                setActiveView("workspace");
                promptReReview(updated.current_version);
              }}
            />
          )
        ) : (
          <Card>
            <div className="text-sm text-label-secondary text-center py-6">No document version available to edit.</div>
          </Card>
        )
      )}

      {activeView === "email" && (
        <Card title="Email thread">
          {pollNotice && (
            <div className="mb-4 rounded-lg border border-separator/30 bg-bg-secondary px-3 py-2 text-sm text-label-secondary">
              {pollNotice}
            </div>
          )}
          {isOwner && gmail?.connected && (
            <div className="mb-4 flex flex-wrap items-center gap-2">
              {tracker.gmail_thread_id && tracker.gmail_auto_ingest !== false ? (
                <>
                  <Badge className="bg-emerald-100 text-emerald-800">Watching for vendor docx</Badge>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={async () => {
                      await api.unlinkMSAGmailThread(tracker.id);
                      await load();
                      setPollNotice("Gmail auto-ingest disabled for this negotiation.");
                    }}
                  >
                    Unwatch thread
                  </Button>
                </>
              ) : (
                <Button variant="secondary" size="sm" onClick={() => setWatchOpen(true)}>
                  Watch Gmail thread
                </Button>
              )}
            </div>
          )}
          {tracker.gmail_thread_id ? (
            <MSAGmailThreadPanel threadId={tracker.gmail_thread_id} />
          ) : (
            <p className="text-sm text-label-secondary mb-4">
              Link a Gmail thread to auto-ingest vendor docx attachments and run AI analysis.
            </p>
          )}
          {tracker.emails.length === 0 ? (
            <div className="text-sm text-label-secondary text-center py-4">No emails logged yet.</div>
          ) : (
            <ul className="space-y-3">
              {tracker.emails.map((m) => (
                <li
                  key={m.id}
                  className={classNames(
                    "border rounded-lg p-3",
                    m.direction === "in" ? "bg-bg-secondary" : "bg-blue-50",
                  )}
                >
                  <div className="text-xs text-label-secondary">
                    {m.direction === "in" ? "Inbound" : "Outbound"} · {formatDate(m.sent_at)}
                  </div>
                  <div className="text-sm font-semibold mt-0.5">{m.subject}</div>
                  <pre className="text-sm whitespace-pre-wrap font-sans mt-2 text-label-secondary">
                    {m.body}
                  </pre>
                  {m.attachment_name && (
                    <div className="text-xs text-label-secondary mt-1">📎 {m.attachment_name}</div>
                  )}
                </li>
              ))}
            </ul>
          )}
          {watchOpen && tracker && (
            <MSAGmailWatchPicker
              onClose={() => setWatchOpen(false)}
              onWatch={async (threadId, subject) => {
                await api.linkMSAGmailThread(tracker.id, {
                  thread_id: threadId,
                  subject,
                  vendor_email: tracker.vendor_email,
                });
                setWatchOpen(false);
                await load();
                setPollNotice("Thread linked — vendor docx will auto-ingest on poll.");
              }}
            />
          )}
        </Card>
      )}
    </div>
  );
}

function MSAEditPanel({
  tracker,
  versions,
  canApprove,
  onApplied,
}: {
  tracker: MSATracker;
  versions: DocumentVersion[];
  canApprove: boolean;
  onApplied: () => void;
}) {
  const { user } = useAuth();
  const [instruction, setInstruction] = useState("");
  const [selection, setSelection] = useState("");
  const [guidelines, setGuidelines] = useState(tracker.review_guidelines || "");
  const [preview, setPreview] = useState<MSAPromptEditPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editedText, setEditedText] = useState("");
  const [editableOps, setEditableOps] = useState<MSADocxOperation[]>([]);
  const [jumpCursor, setJumpCursor] = useState(0);
  const diffRef = useRef<DiffViewHandle>(null);
  const [revisions, setRevisions] = useState<MSAPromptRevisionSummary[]>([]);
  const [historyRevision, setHistoryRevision] = useState<MSAPromptRevision | null>(null);
  const [historyBusy, setHistoryBusy] = useState(false);
  const historyDiffRef = useRef<DiffViewHandle>(null);

  const disabled = tracker.status === "executed";

  const latestLegal = useMemo(() => {
    const legal = versions
      .filter((v) => v.source === "legal_redline" || v.source === "legal_base")
      .sort((a, b) => b.version_number - a.version_number);
    return legal[0] ?? null;
  }, [versions]);

  const docxSource = latestLegal ? isOfficeDoc(latestLegal) : false;

  const loadRevisions = useCallback(() => {
    api
      .listMSAPromptRevisions(tracker.id)
      .then(setRevisions)
      .catch(() => setRevisions([]));
  }, [tracker.id]);

  useEffect(() => {
    loadRevisions();
  }, [loadRevisions]);

  useEffect(() => {
    if (preview) {
      setEditedText(preview.edited_text);
      setEditableOps(preview.operations.map((op) => ({ ...op })));
      setEditing(false);
      setJumpCursor(0);
    } else {
      setEditableOps([]);
    }
  }, [preview]);

  const isDocxOps = preview?.edit_mode === "docx_operations";
  // Free-text curation is only safe for genuine text/PDF sources. Word documents
  // stay on structured ops — those ops are editable below without OnlyOffice.
  const canEditText = !!preview && !docxSource && !isDocxOps;
  const canCurateOps = !!preview && isDocxOps && editableOps.length > 0;

  const displayBlocks = useMemo(() => {
    if (!preview) return [];
    if (editing && canEditText) return lineDiffBlocks(preview.base_text, editedText);
    return preview.diff_blocks;
  }, [preview, editing, canEditText, editedText]);

  const changeIndices = useMemo(
    () =>
      displayBlocks.reduce<number[]>((acc, b, i) => {
        if (b.kind !== "equal") acc.push(i);
        return acc;
      }, []),
    [displayBlocks],
  );

  const stats = useMemo(() => redlineStats(displayBlocks), [displayBlocks]);

  function jumpTo(step: number) {
    if (changeIndices.length === 0) return;
    const next = (jumpCursor + step + changeIndices.length) % changeIndices.length;
    setJumpCursor(next);
    diffRef.current?.scrollToIndex(changeIndices[next]);
  }

  // Drop a single proposed change: rebuild the edited text keeping every block's
  // edited side, except the reverted block which falls back to the original
  // (base) text. Text sources only — DOCX stays on the formatting-safe path.
  function revertChange(index: number) {
    if (!canEditText) return;
    const lines: string[] = [];
    displayBlocks.forEach((b, i) => {
      const side = i === index ? b.v1 : b.v2;
      if (side.length > 0) lines.push(...side.split("\n"));
    });
    setEditedText(lines.join("\n"));
    setEditing(true);
  }

  // Wow moment: when the reviewer opens the inline editor, take them straight to
  // the first change in the document preview instead of making them hunt for it.
  useEffect(() => {
    if (!editing || changeIndices.length === 0) return;
    setJumpCursor(0);
    const t = setTimeout(() => diffRef.current?.scrollToIndex(changeIndices[0]), 80);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  const [historyJumpCursor, setHistoryJumpCursor] = useState(0);
  const historyChangeIndices = useMemo(
    () =>
      (historyRevision?.diff_blocks ?? []).reduce<number[]>((acc, b, i) => {
        if (b.kind !== "equal") acc.push(i);
        return acc;
      }, []),
    [historyRevision],
  );

  function historyJumpTo(step: number) {
    if (historyChangeIndices.length === 0) return;
    const next =
      (historyJumpCursor + step + historyChangeIndices.length) % historyChangeIndices.length;
    setHistoryJumpCursor(next);
    historyDiffRef.current?.scrollToIndex(historyChangeIndices[next]);
  }

  const versionNumberById = useMemo(() => {
    const map = new Map<number, number>();
    for (const v of versions) map.set(v.id, v.version_number);
    return map;
  }, [versions]);

  async function viewHistoryRevision(revisionId: number) {
    setHistoryBusy(true);
    setHistoryJumpCursor(0);
    try {
      setHistoryRevision(await api.getMSAPromptRevision(tracker.id, revisionId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load revision");
    } finally {
      setHistoryBusy(false);
    }
  }

  async function deleteHistoryRevision(revisionId: number, status: string) {
    if (status === "applied") return;
    const label = status === "proposed" ? "proposed edit" : "edit";
    if (!window.confirm(`Delete this ${label} from history? This cannot be undone.`)) return;
    setHistoryBusy(true);
    setError(null);
    try {
      await api.deleteMSAPromptRevision(tracker.id, revisionId);
      if (historyRevision?.id === revisionId) setHistoryRevision(null);
      if (preview?.revision_id === revisionId) setPreview(null);
      loadRevisions();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete edit");
    } finally {
      setHistoryBusy(false);
    }
  }

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
      const result = await api.promptEditMSA(tracker.id, {
        instruction,
        selection: selection.trim() || undefined,
        review_guidelines: guidelines.trim() || undefined,
      });
      setPreview(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Edit failed");
    } finally {
      setBusy(false);
    }
  }

  function updateOp(index: number, patch: Partial<MSADocxOperation>) {
    setEditableOps((prev) => prev.map((op, i) => (i === index ? { ...op, ...patch } : op)));
  }

  function removeOp(index: number) {
    setEditableOps((prev) => prev.filter((_, i) => i !== index));
  }

  async function apply() {
    if (!preview) return;
    if (canCurateOps && editableOps.length === 0) {
      setError("Keep at least one planned operation, or discard this proposal.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.applyMSAPromptEdit(tracker.id, {
        instruction,
        edited_text: canEditText ? editedText : preview.edited_text,
        parent_version_id: preview.base_version_id,
        revision_id: preview.revision_id ?? undefined,
        operations: canCurateOps ? editableOps : undefined,
      });
      setPreview(null);
      setInstruction("");
      setSelection("");
      setGuidelines("");
      onApplied();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Apply failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Ask AI to edit the document"
      subtitle="Describe a change in plain language. DOCX files use structured operations to preserve formatting."
    >
      {docxSource && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900 mb-4">
          Word document detected. AI plans <strong>structured operations</strong> that preserve
          formatting. After generation you can <strong>edit or remove</strong> any proposed change
          here before applying. Use <strong>Edit document</strong> (ONLYOFFICE) only for broader
          free-form formatting work.
        </div>
      )}
      {disabled ? (
        <div className="rounded-lg bg-bg-secondary border border-separator/40 p-4 text-sm text-label-secondary">
          This negotiation is executed and locked. No further edits can be made.
        </div>
      ) : !latestLegal ? (
        <div className="rounded-lg bg-amber-50 border border-warning/20 p-4 text-sm text-amber-800">
          No legal document version available to edit yet.
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-xs text-label-secondary">
            <Icon.Documents className="w-4 h-4" />
            Editing{" "}
            <span className="font-medium text-label-secondary">
              v{latestLegal.version_number} · {sourceLabel(latestLegal.source)}
            </span>
            {latestLegal.filename && <span className="text-label-tertiary">· {latestLegal.filename}</span>}
          </div>

          <div className="flex flex-wrap gap-2">
            {QUICK_EDIT_PROMPTS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setInstruction(p)}
                className="text-xs px-2.5 py-1 rounded-full border border-separator/40 bg-bg text-label-secondary hover:border-accent/30 hover:text-accent hover:bg-accent/10 transition"
              >
                {p.length > 46 ? p.slice(0, 46) + "…" : p}
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
            label="Scope (optional) — paste the clause this edit should apply to"
            rows={2}
            value={selection}
            onChange={(e) => setSelection(e.target.value)}
          />
          <Textarea
            label="Ground truth / guidelines (optional)"
            rows={3}
            value={guidelines}
            onChange={(e) => setGuidelines(e.target.value)}
            placeholder={"One required item per line, e.g.\nJio Finance Platform and Service Limited\nJFPSL"}
          />

          <div className="flex gap-2">
            <Button disabled={busy || !isSafeEditInstruction(instruction)} onClick={propose}>
              <Icon.Sparkles className="w-4 h-4 mr-1.5" />
              {busy && !preview
                ? `${user?.full_name ?? "You"} is drafting…`
                : "Generate proposed edit"}
            </Button>
          </div>
          {error && <p className="text-sm text-error">{error}</p>}

          {preview && (
            <div className="rounded-xl border border-warning/20 bg-amber-50/40 p-4 space-y-4 animate-fade-in">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <Badge className="bg-amber-100 text-amber-800 border-warning/20">Proposed edit</Badge>
                  <p className="text-xs text-label-secondary mt-1">
                    From v{preview.base_version_number} · model{" "}
                    <span className="font-mono">{preview.model_version}</span>
                    {preview.ai_fallback && (
                      <span className="text-amber-700 ml-2">
                        (ADK unavailable — rule-based fallback used)
                      </span>
                    )}
                  </p>
                </div>
                <div className="flex gap-2">
                  {canApprove ? (
                    <Button
                      size="sm"
                      disabled={busy || (canCurateOps && editableOps.length === 0)}
                      onClick={apply}
                    >
                      <Icon.Check className="w-3.5 h-3.5 mr-1" />
                      Apply as v{tracker.current_version + 1}
                    </Button>
                  ) : null}
                  <Button size="sm" variant="secondary" disabled={busy} onClick={() => setPreview(null)}>
                    Discard
                  </Button>
                </div>
              </div>

              {preview.change_summary && (
                <div className="text-sm text-label-secondary bg-bg border border-amber-100 rounded-lg p-3 leading-relaxed overflow-x-auto">
                  <Markdown text={preview.change_summary} />
                </div>
              )}

              {preview.edit_mode === "docx_operations" && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-medium text-label-secondary uppercase tracking-wide">
                      Planned operations
                      {canCurateOps ? " — edit if anything looks wrong" : ""}
                    </p>
                    {canCurateOps && (
                      <span className="text-[11px] text-label-tertiary">
                        {editableOps.length} op{editableOps.length === 1 ? "" : "s"}
                      </span>
                    )}
                  </div>
                  {editableOps.length === 0 ? (
                    <p className="text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-lg p-3">
                      All operations removed. Discard this proposal or regenerate.
                    </p>
                  ) : (
                    <ul className="space-y-3">
                      {editableOps.map((op, i) => (
                        <li
                          key={i}
                          className="text-sm bg-bg border border-separator/40 rounded-lg p-3 space-y-2"
                        >
                          <div className="flex items-center gap-2 flex-wrap">
                            <Badge className="bg-bg-secondary text-label-secondary border-separator/40 text-xs">
                              {op.op_type}
                            </Badge>
                            {op.anchor_id && (
                              <span className="text-xs font-mono text-label-tertiary">
                                {op.anchor_id}
                              </span>
                            )}
                            <span className="text-xs text-label-tertiary ml-auto">
                              {Math.round(op.confidence * 100)}% conf.
                            </span>
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled={busy}
                              onClick={() => removeOp(i)}
                              title="Remove this change"
                            >
                              Remove
                            </Button>
                          </div>
                          <Textarea
                            label="What this change does"
                            rows={2}
                            value={op.description}
                            onChange={(e) => updateOp(i, { description: e.target.value })}
                          />
                          {(op.target_text != null || op.op_type.includes("replace")) && (
                            <Textarea
                              label="Find / replace target (existing text)"
                              rows={2}
                              value={op.target_text ?? ""}
                              onChange={(e) =>
                                updateOp(i, { target_text: e.target.value || null })
                              }
                            />
                          )}
                          <Textarea
                            label="Replacement / new wording"
                            rows={3}
                            value={op.content ?? ""}
                            onChange={(e) => updateOp(i, { content: e.target.value || null })}
                          />
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {preview.operation_results.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-label-secondary uppercase tracking-wide">
                    Operation results
                  </p>
                  <ul className="space-y-1">
                    {preview.operation_results.map((r) => (
                      <li key={r.op_index} className="text-xs text-label-secondary">
                        <span
                          className={
                            r.status === "applied"
                              ? "text-emerald-700"
                              : r.status === "manual_required"
                                ? "text-amber-700"
                                : "text-error"
                          }
                        >
                          {r.status}
                        </span>
                        {" — "}
                        {r.description}
                        {r.message ? ` (${r.message})` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {!canApprove && (
                <p className="text-xs text-amber-800">
                  You can propose edits; applying a new version requires approval permission.
                </p>
              )}

              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-label-secondary">
                    {changeIndices.length} change{changeIndices.length === 1 ? "" : "s"}
                  </span>
                  <span className="inline-flex items-center gap-1 text-[11px]">
                    <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-medium">
                      +{stats.additions} added
                    </span>
                    <span className="px-1.5 py-0.5 rounded bg-red-100 text-red-800 font-medium">
                      −{stats.deletions} removed
                    </span>
                  </span>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={changeIndices.length === 0}
                      onClick={() => jumpTo(-1)}
                      title="Previous change"
                    >
                      ↑ Prev
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={changeIndices.length === 0}
                      onClick={() => jumpTo(1)}
                      title="Next change"
                    >
                      Next ↓
                    </Button>
                  </div>
                </div>
                {canEditText && (
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={busy}
                    onClick={() => setEditing((v) => !v)}
                  >
                    <Icon.Pencil className="w-3.5 h-3.5 mr-1" />
                    {editing ? "Hide editor" : "Edit proposed text"}
                  </Button>
                )}
              </div>

              {docxSource && (
                <p className="text-xs text-label-secondary">
                  Fix any incorrect AI wording in the planned operations above, then Apply.
                  OnlyOffice is optional — use it only when you need free-form document editing.
                </p>
              )}

              {editing && canEditText && (
                <Textarea
                  label="Proposed text — curate before applying"
                  rows={14}
                  value={editedText}
                  onChange={(e) => setEditedText(e.target.value)}
                />
              )}

              {canEditText && (
                <p className="text-[11px] text-label-tertiary">
                  Tip: hover any highlighted change and click <strong>Revert</strong> to drop just
                  that edit, or use <strong>Edit proposed text</strong> to curate the wording.
                </p>
              )}

              <RedlinePreview
                ref={diffRef}
                title={`Proposed v${tracker.current_version + 1} · redline from v${preview.base_version_number}`}
                blocks={displayBlocks}
                height={360}
                onDeleteChange={canEditText ? revertChange : undefined}
              />
            </div>
          )}

          <div className="rounded-lg border border-separator/30 bg-bg-secondary p-3 text-xs text-label-secondary leading-relaxed">
            <strong className="text-label-secondary">How it works:</strong> The original upload stays
            available and renders as-is. Applying creates a new legal redline version: DOCX remains
            editable DOCX, while PDF/text sources are rendered as a clean legal PDF. Every step is
            audit-logged.
          </div>
        </div>
      )}

      <div className="mt-5 border-t border-separator/30 pt-4">
        <div className="flex items-center justify-between gap-2 mb-2">
          <div>
            <p className="text-sm font-semibold text-label">Edit history</p>
            <p className="text-xs text-label-secondary">
              Every AI edit for this negotiation. Delete proposed or discarded edits anytime;
              applied edits stay for audit.
            </p>
          </div>
          <span className="text-xs text-label-tertiary">{revisions.length} edit(s)</span>
        </div>

        {revisions.length === 0 ? (
          <p className="text-xs text-label-secondary py-2">No AI edits yet.</p>
        ) : (
          <ul className="space-y-2">
            {[...revisions]
              .sort((a, b) => b.id - a.id)
              .map((r) => {
                const isActive = historyRevision?.id === r.id;
                const versionLabel =
                  isActive && historyRevision?.resulting_version_id != null
                    ? versionNumberById.get(historyRevision.resulting_version_id)
                    : undefined;
                return (
                  <li
                    key={r.id}
                    className="border border-separator/30 rounded-lg px-3 py-2"
                  >
                    <div className="flex items-start justify-between gap-2 flex-wrap">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge className={revisionStatusClass(r.status)}>{r.status}</Badge>
                          {versionLabel != null && (
                            <Badge className="bg-blue-100 text-blue-800">→ v{versionLabel}</Badge>
                          )}
                          <span className="text-xs text-label-tertiary">{formatDate(r.created_at)}</span>
                        </div>
                        <p className="text-sm text-label mt-1 line-clamp-2">{r.instruction}</p>
                        {r.change_summary && (
                          <p className="text-xs text-label-secondary mt-0.5 line-clamp-2">
                            {r.change_summary}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={historyBusy}
                          onClick={() => (isActive ? setHistoryRevision(null) : viewHistoryRevision(r.id))}
                        >
                          {isActive ? "Hide diff" : "View diff"}
                        </Button>
                        {r.status !== "applied" && canApprove && !disabled && (
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={historyBusy}
                            onClick={() => deleteHistoryRevision(r.id, r.status)}
                            title="Delete from edit history"
                            className="text-error hover:bg-red-50"
                          >
                            Delete
                          </Button>
                        )}
                      </div>
                    </div>

                    {isActive && historyRevision && (
                      <div className="mt-3 space-y-2">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-label-secondary">
                            {historyChangeIndices.length} change
                            {historyChangeIndices.length === 1 ? "" : "s"}
                          </span>
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={historyChangeIndices.length === 0}
                            onClick={() => historyJumpTo(-1)}
                          >
                            ↑ Prev
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={historyChangeIndices.length === 0}
                            onClick={() => historyJumpTo(1)}
                          >
                            Next ↓
                          </Button>
                        </div>
                        <RedlinePreview
                          ref={historyDiffRef}
                          title="After this edit"
                          blocks={historyRevision.diff_blocks}
                          height={300}
                        />
                      </div>
                    )}
                  </li>
                );
              })}
          </ul>
        )}
      </div>
    </Card>
  );
}

function revisionStatusClass(status: string): string {
  if (status === "applied") return "bg-emerald-100 text-emerald-800";
  if (status === "discarded") return "bg-red-100 text-red-800";
  return "bg-amber-100 text-amber-800";
}

function ViewTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={classNames(
        "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors duration-fast",
        active
          ? "border-accent text-accent"
          : "border-transparent text-label-secondary hover:text-label hover:border-separator/60",
      )}
    >
      {children}
    </button>
  );
}

function nextAction(status: string): string {
  const map: Record<string, string> = {
    under_review: "review clauses",
    redlined: "send to vendor",
    sent_to_vendor: "await vendor return",
    negotiation: "upload vendor return",
    executed: "done",
  };
  return map[status] || status.replace(/_/g, " ");
}

async function fetchVersionText(v: DocumentVersion): Promise<string> {
  try {
    const { extracted_text } = await api.getMSAVersionText(v.tracker_id, v.id);
    return extracted_text;
  } catch {
    return "";
  }
}

async function downloadFile(storageKey: string) {
  const resp = await fetch(`${BASE}/api/msa/files/${storageKey}`, { credentials: "include" });
  if (!resp.ok) return;
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = storageKey.split("/").pop() || "document";
  a.click();
  URL.revokeObjectURL(url);
}

function VersionPicker({
  versions,
  currentFrom,
  currentTo,
  onCompare,
}: {
  versions: DocumentVersion[];
  currentFrom: number | null;
  currentTo: number | null;
  onCompare: (fromId: number, toId: number) => Promise<void>;
}) {
  const sorted = [...versions].sort((a, b) => a.version_number - b.version_number);
  const fromInitial = sorted.find((v) => v.version_number === currentFrom) || sorted[0];
  const toInitial = sorted.find((v) => v.version_number === currentTo) || sorted[sorted.length - 1];
  const [fromId, setFromId] = useState<number>(fromInitial?.id ?? 0);
  const [toId, setToId] = useState<number>(toInitial?.id ?? 0);
  const [busy, setBusy] = useState(false);

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-label-secondary">Compare</span>
      <select
        value={fromId}
        onChange={(e) => setFromId(Number(e.target.value))}
        className="border border-separator/60 rounded px-2 py-1 text-xs bg-bg"
      >
        {sorted.map((v) => (
          <option key={v.id} value={v.id}>
            v{v.version_number} · {v.source.replace(/_/g, " ")}
          </option>
        ))}
      </select>
      <span className="text-label-tertiary">→</span>
      <select
        value={toId}
        onChange={(e) => setToId(Number(e.target.value))}
        className="border border-separator/60 rounded px-2 py-1 text-xs bg-bg"
      >
        {sorted.map((v) => (
          <option key={v.id} value={v.id}>
            v{v.version_number} · {v.source.replace(/_/g, " ")}
          </option>
        ))}
      </select>
      <Button
        size="sm"
        variant="secondary"
        disabled={busy || fromId === toId || !fromId || !toId}
        onClick={async () => {
          setBusy(true);
          try {
            await onCompare(fromId, toId);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Comparing…" : "Run"}
      </Button>
    </div>
  );
}

function SendBox({ trackerId, vendorName, onSent }: { trackerId: number; vendorName: string; onSent: () => void }) {
  const [subject, setSubject] = useState(`Redlined draft from JFPSL Legal — ${vendorName}`);
  const [body, setBody] = useState(`Dear ${vendorName} team,\n\nPlease find attached our redlined version.\n\nRegards,\nJFPSL Legal`);
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-2">
      <Input label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
      <Textarea label="Body" rows={5} value={body} onChange={(e) => setBody(e.target.value)} />
      <Button disabled={busy} onClick={async () => { setBusy(true); await api.sendMSA(trackerId, subject, body); onSent(); setBusy(false); }}>
        {busy ? "Sending…" : "Send to vendor"}
      </Button>
    </div>
  );
}

function MSASharePanel({
  tracker,
  onClose,
  onUpdated,
}: {
  tracker: MSATracker;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [users, setUsers] = useState<ShareableUser[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState("");
  const [accessLevel, setAccessLevel] = useState<"view" | "edit">("view");
  const [shares, setShares] = useState<MSAShare[]>(tracker.shares ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api.listMSAShares(tracker.id).then(setShares).catch(() => null);
    // Load available users once (chat-style dropdown / checklist).
    api
      .searchShareableUsers("")
      .then(setUsers)
      .catch(() => setUsers([]));
  }, [tracker.id]);

  const alreadyShared = useMemo(
    () => new Set(shares.map((s) => s.user_id)),
    [shares],
  );

  const filteredUsers = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return users.filter((u) => {
      if (alreadyShared.has(u.id)) return false;
      if (!q) return true;
      return (
        u.full_name.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q) ||
        (u.role || "").toLowerCase().includes(q)
      );
    });
  }, [users, filter, alreadyShared]);

  function toggleUser(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function addShare() {
    if (selected.size === 0) return;
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const created: MSAShare[] = [];
      for (const userId of selected) {
        const share = await api.createMSAShare(tracker.id, {
          user_id: userId,
          access_level: accessLevel,
        });
        created.push(share);
      }
      setShares((prev) => {
        const byUser = new Map(prev.map((s) => [s.user_id, s]));
        for (const s of created) byUser.set(s.user_id, s);
        return Array.from(byUser.values());
      });
      setSelected(new Set());
      setMsg(
        created.length === 1
          ? `Shared with ${created[0].user_full_name ?? "1 user"}.`
          : `Shared with ${created.length} users.`,
      );
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Share failed");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(userId: number) {
    setBusy(true);
    setError(null);
    try {
      await api.revokeMSAShare(tracker.id, userId);
      setShares((prev) => prev.filter((s) => s.user_id !== userId));
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Revoke failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Share negotiation"
      subtitle="Select users to grant read or edit access (same pattern as LawGenie chat share)."
      actions={
        <Button size="sm" variant="secondary" onClick={onClose}>
          Close
        </Button>
      }
    >
      <div className="space-y-4">
        <Input
          label="Find user"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search by name or email…"
        />
        <div className="max-h-56 overflow-y-auto scrollbar-thin rounded-lg border border-separator">
          {filteredUsers.length === 0 && (
            <div className="px-3 py-4 text-sm text-label-tertiary">
              {users.length === 0 ? "No users available." : "No matching users."}
            </div>
          )}
          {filteredUsers.map((u) => (
            <label
              key={u.id}
              className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-bg-accent/60 border-b border-separator/50 last:border-b-0"
            >
              <input
                type="checkbox"
                checked={selected.has(u.id)}
                onChange={() => toggleUser(u.id)}
                className="accent-accent h-4 w-4"
              />
              <span className="min-w-0">
                <span className="block text-sm text-label truncate">{u.full_name}</span>
                <span className="block text-xs text-label-tertiary truncate">
                  {u.email}
                  {u.role ? ` · ${u.role.replace(/_/g, " ")}` : ""}
                </span>
              </span>
            </label>
          ))}
        </div>
        <div className="flex gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="access"
              checked={accessLevel === "view"}
              onChange={() => setAccessLevel("view")}
            />
            Read only
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="access"
              checked={accessLevel === "edit"}
              onChange={() => setAccessLevel("edit")}
            />
            Edit
          </label>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-label-tertiary">{selected.size} selected</span>
          <Button size="sm" disabled={busy || selected.size === 0} onClick={() => void addShare()}>
            {busy ? "Sharing…" : "Share access"}
          </Button>
        </div>
        {msg && <p className="text-sm text-label-secondary">{msg}</p>}
        {error && <p className="text-sm text-error">{error}</p>}
        {shares.length > 0 && (
          <ul className="space-y-2 pt-2 border-t border-separator/30">
            {shares.map((s) => (
              <li
                key={s.id}
                className="flex items-center justify-between gap-2 text-sm border border-separator/30 rounded-lg px-3 py-2"
              >
                <div>
                  <span className="font-medium text-label">
                    {s.user_full_name ?? `User #${s.user_id}`}
                  </span>
                  {s.user_email && (
                    <span className="text-label-secondary ml-2">{s.user_email}</span>
                  )}
                  <Badge className="ml-2 capitalize">{s.access_level}</Badge>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={busy}
                  onClick={() => void revoke(s.user_id)}
                >
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function GmailFlowInfo() {
  const KEY = "legalos.msaGmailInfo.hidden";
  const [hidden, setHidden] = useState<boolean>(() => {
    try {
      return localStorage.getItem(KEY) === "1";
    } catch {
      return false;
    }
  });

  function toggle() {
    setHidden((h) => {
      const next = !h;
      try {
        localStorage.setItem(KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  const steps = [
    {
      icon: "👀",
      title: "Watch a thread",
      text: "Find the vendor's email (search — no thread IDs) and click Watch.",
    },
    {
      icon: "📥",
      title: "Vendor replies",
      text: "They send a revised contract as a .docx in that email thread.",
    },
    {
      icon: "🔄",
      title: "Poll Gmail",
      text: "Scans your watched threads for new vendor attachments. Also runs automatically in the background.",
    },
    {
      icon: "✅",
      title: "Auto-ingest & review",
      text: "The new .docx becomes a document version and is AI-reviewed; the MSA tracker is created or updated.",
    },
  ];

  if (hidden) {
    return (
      <div className="flex justify-end">
        <button
          onClick={toggle}
          className="text-xs text-label-tertiary hover:text-accent"
        >
          ⓘ What do “Poll Gmail” and “Watch vendor thread” do?
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-separator/40 bg-bg-secondary px-4 py-3">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-semibold text-label">
          How vendor email automation works
        </div>
        <button onClick={toggle} className="text-xs text-label-tertiary hover:text-label">
          Hide
        </button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {steps.map((s, i) => (
          <div key={i} className="relative flex gap-3 rounded-lg bg-bg px-3 py-2.5">
            <div className="text-xl leading-none shrink-0" aria-hidden>
              {s.icon}
            </div>
            <div className="min-w-0">
              <div className="text-xs font-semibold text-label">
                {i + 1}. {s.title}
              </div>
              <div className="text-xs text-label-secondary leading-snug mt-0.5">{s.text}</div>
            </div>
            {i < steps.length - 1 && (
              <div className="hidden lg:block absolute -right-2.5 top-1/2 -translate-y-1/2 text-label-tertiary">
                →
              </div>
            )}
          </div>
        ))}
      </div>
      <p className="mt-2.5 text-xs text-label-tertiary">
        Tip: “Poll Gmail” only checks the threads you’re watching — it never reads your whole
        inbox. Attachments are ingested only from watched or linked vendor threads.
      </p>
    </div>
  );
}

function MSAGmailWatchPicker({
  onClose,
  onWatch,
}: {
  onClose: () => void;
  onWatch: (threadId: string, subject?: string) => Promise<void>;
}) {
  const [messages, setMessages] = useState<GmailMessageSummary[]>([]);
  const [query, setQuery] = useState("");
  const [days, setDays] = useState(30);
  const [watchingId, setWatchingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Escape hatch for power users who already have a raw thread id.
  const [advanced, setAdvanced] = useState(false);
  const [threadId, setThreadId] = useState("");

  const runSearch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.gmailMessages({
        q: query.trim() || undefined,
        newer_than_days: days,
        max_results: 50,
      });
      setMessages(res.messages);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [query, days]);

  useEffect(() => {
    void runSearch();
    // Initial load only; subsequent searches are triggered explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // De-dupe messages down to one row per email thread.
  const threads = useMemo(() => {
    const byThread = new Map<string, GmailMessageSummary>();
    for (const m of messages) {
      if (!byThread.has(m.thread_id)) byThread.set(m.thread_id, m);
    }
    return Array.from(byThread.values());
  }, [messages]);

  async function watch(id: string, subject?: string) {
    const tid = id.trim();
    if (!tid) return;
    setWatchingId(tid);
    setError(null);
    try {
      await onWatch(tid, subject);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setWatchingId(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card title="Find & watch a vendor email thread" className="w-full max-w-xl shadow-xl">
        <p className="text-sm text-label-secondary mb-3">
          Search your inbox for the vendor's email and click <strong>Watch</strong>. New vendor{" "}
          <code>.docx</code> replies in that thread are then auto-ingested and AI-reviewed — no
          thread IDs needed.
        </p>
        {error && <p className="text-sm text-error mb-3">{error}</p>}

        <div className="flex gap-2">
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void runSearch();
            }}
            placeholder="Search by vendor name, subject, or sender email…"
            className="flex-1 rounded-lg border border-separator bg-bg px-3 py-2 text-sm text-label focus:outline-none"
          />
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-lg border border-separator bg-bg px-2 py-2 text-sm text-label"
          >
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={365}>1 year</option>
          </select>
          <Button size="sm" onClick={() => void runSearch()} disabled={loading}>
            Search
          </Button>
        </div>

        <div className="mt-3">
          {loading ? (
            <div className="text-sm text-label-secondary py-6 text-center">Searching inbox…</div>
          ) : threads.length === 0 ? (
            <div className="text-sm text-label-secondary py-6 text-center">
              No matching emails. Try a different search or widen the date range.
            </div>
          ) : (
            <ul className="max-h-72 overflow-y-auto space-y-1.5 border border-separator/30 rounded-lg p-2">
              {threads.map((m) => (
                <li
                  key={m.thread_id}
                  className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-bg-secondary"
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-sm truncate text-label">
                      {m.subject || "(no subject)"}
                    </div>
                    <div className="text-xs text-label-secondary truncate">
                      {m.from_addr}
                      {m.date ? ` · ${new Date(m.date).toLocaleDateString()}` : ""}
                    </div>
                    {m.snippet && (
                      <div className="text-xs text-label-tertiary truncate mt-0.5">{m.snippet}</div>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={watchingId !== null}
                    onClick={() => void watch(m.thread_id, m.subject)}
                  >
                    {watchingId === m.thread_id ? "Watching…" : "Watch"}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="mt-3">
          <button
            type="button"
            className="text-xs text-label-tertiary hover:text-label"
            onClick={() => setAdvanced((v) => !v)}
          >
            {advanced ? "▾" : "▸"} Advanced: paste a thread ID
          </button>
          {advanced && (
            <div className="flex gap-2 mt-2">
              <Input
                value={threadId}
                onChange={(e) => setThreadId(e.target.value)}
                placeholder="Gmail thread ID"
              />
              <Button
                size="sm"
                disabled={!threadId.trim() || watchingId !== null}
                onClick={() => void watch(threadId)}
              >
                Watch
              </Button>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <Button variant="secondary" onClick={onClose} disabled={watchingId !== null}>
            Close
          </Button>
        </div>
      </Card>
    </div>
  );
}

function MSAGmailThreadPanel({ threadId }: { threadId: string }) {
  const [thread, setThread] = useState<GmailThread | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .gmailThread(threadId)
      .then(setThread)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [threadId]);

  if (loading) {
    return <div className="text-sm text-label-secondary mb-4">Loading Gmail thread…</div>;
  }
  if (error) {
    return <div className="text-sm text-error mb-4">{error}</div>;
  }
  if (!thread) return null;

  return (
    <div className="mb-6 border border-separator/30 rounded-lg p-3 bg-bg-secondary">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="text-sm font-medium text-label">Live Gmail thread</div>
        <Link
          to={`/jiolegal?gmail_thread=${threadId}&gmail_label=MSA+vendor+thread`}
          className="text-xs text-accent hover:underline"
        >
          Ask LawGenie about this thread
        </Link>
      </div>
      <ul className="space-y-3 max-h-64 overflow-y-auto">
        {thread.messages.map((m) => (
          <li key={m.id} className="border border-separator/20 rounded p-2 bg-bg text-sm">
            <div className="text-xs text-label-secondary">{m.from_addr}</div>
            <div className="font-medium">{m.subject}</div>
            <pre className="text-xs whitespace-pre-wrap text-label-secondary mt-1 max-h-24 overflow-y-auto">
              {m.body}
            </pre>
          </li>
        ))}
      </ul>
    </div>
  );
}
