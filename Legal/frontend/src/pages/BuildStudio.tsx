import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";

import { GitHubLogo, Icon } from "@/components/Icons";
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
import { classNames, formatDate } from "@/lib/utils";
import type {
  AgentLogEntry,
  FeatureRequest,
  FeatureRequestStatus,
  FeatureRequestSummary,
} from "@/types";

const STATUS_LABEL: Record<FeatureRequestStatus, string> = {
  submitted: "Submitted",
  analysing: "Analysing",
  planning: "Planning",
  in_progress: "Implementing",
  pr_open: "PR open · awaiting review",
  in_review: "In review",
  merged: "Merged",
  deploying: "Deploying",
  deployed: "Deployed",
  failed: "Failed",
  rejected: "Rejected",
};

const STATUS_COLOR: Record<FeatureRequestStatus, string> = {
  submitted: "bg-bg-secondary text-label border-separator/40",
  analysing: "bg-blue-100 text-blue-800 border-accent/20",
  planning: "bg-blue-100 text-blue-800 border-accent/20",
  in_progress: "bg-indigo-100 text-indigo-800 border-indigo-200",
  pr_open: "bg-amber-100 text-amber-800 border-warning/20",
  in_review: "bg-amber-100 text-amber-800 border-warning/20",
  merged: "bg-violet-100 text-violet-800 border-violet-200",
  deploying: "bg-cyan-100 text-cyan-800 border-cyan-200",
  deployed: "bg-emerald-100 text-emerald-800 border-emerald-200",
  failed: "bg-red-100 text-red-800 border-error/20",
  rejected: "bg-red-100 text-red-800 border-error/20",
};

const TYPE_COLOR: Record<string, string> = {
  bug: "bg-red-50 text-error border-error/20",
  feature: "bg-emerald-50 text-emerald-700 border-emerald-200",
  enhancement: "bg-blue-50 text-blue-700 border-accent/20",
  refactor: "bg-violet-50 text-violet-700 border-violet-200",
};

const PRIORITY_COLOR: Record<string, string> = {
  P0: "bg-red-100 text-red-800 border-error/20",
  P1: "bg-amber-100 text-amber-800 border-warning/20",
  P2: "bg-blue-100 text-blue-800 border-accent/20",
  P3: "bg-bg-secondary text-label border-separator/40",
};

const TIMELINE_STEPS: { key: FeatureRequestStatus[]; label: string; icon: keyof typeof Icon }[] = [
  { key: ["submitted"], label: "Submitted", icon: "Inbox" },
  { key: ["analysing", "planning"], label: "Analysed", icon: "Sparkles" },
  { key: ["in_progress"], label: "Implementing", icon: "Code" },
  { key: ["pr_open", "in_review"], label: "PR opened", icon: "PullRequest" },
  { key: ["merged"], label: "Merged", icon: "Branch" },
  { key: ["deploying"], label: "Deploying", icon: "Rocket" },
  { key: ["deployed"], label: "Deployed", icon: "Check" },
];

const STATUS_ORDER: FeatureRequestStatus[] = [
  "submitted",
  "analysing",
  "planning",
  "in_progress",
  "pr_open",
  "in_review",
  "merged",
  "deploying",
  "deployed",
];

function stepIndex(status: FeatureRequestStatus): number {
  return TIMELINE_STEPS.findIndex((s) => s.key.includes(status));
}

function isInFlight(status: FeatureRequestStatus): boolean {
  return !["deployed", "failed", "rejected", "pr_open"].includes(status);
}

export function BuildStudioPage() {
  return (
    <Routes>
      <Route index element={<List />} />
      <Route path="new" element={<Submit />} />
      <Route path=":id" element={<Detail />} />
    </Routes>
  );
}

// ── List ──────────────────────────────────────────────────────────────────────

function List() {
  const [rows, setRows] = useState<FeatureRequestSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setRows(await api.listFeatureRequests());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        eyebrow={
          <span className="inline-flex items-center gap-2">
            <Icon.Sparkles className="w-4 h-4" aria-hidden />
            Autonomous build pipeline
          </span>
        }
        title="Build Studio"
        subtitle={
          <>
            Submit an issue or feature request. An agent analyses your repo, drafts a plan,
            implements it on a feature branch, runs tests, and opens a PR. You review and merge.
            Approved PRs auto-deploy.
            <span className="mt-2 inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-accent/10 text-accent text-caption">
              <GitHubLogo className="w-3.5 h-3.5" aria-hidden />
              Connected to GitHub · jfpsl/legalos · human gate at PR merge
            </span>
          </>
        }
        actions={
          <Link to="new">
            <Button>
              <Icon.Plus className="w-4 h-4 mr-1.5" aria-hidden />
              New request
            </Button>
          </Link>
        }
      />

      <Card>
        {loading ? (
          <div className="text-subheadline text-label-secondary">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="py-10 text-center">
            <Icon.Sparkles className="w-10 h-10 mx-auto text-accent/40 mb-3" />
            <p className="text-label font-medium">No requests yet</p>
            <p className="text-subheadline text-label-secondary mt-1">
              Submit your first issue or feature request and watch the agent work.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-separator/30">
            {rows.map((r, i) => (
              <li
                key={r.id}
                className="py-3 flex items-center gap-3 animate-slide-up"
                style={{ animationDelay: `${i * 40}ms` }}
              >
                <Badge className={TYPE_COLOR[r.request_type] || ""}>{r.request_type}</Badge>
                <Badge className={PRIORITY_COLOR[r.priority]}>{r.priority}</Badge>
                <Link
                  to={`${r.id}`}
                  className="flex-1 min-w-0 text-subheadline font-medium text-label hover:text-accent truncate"
                >
                  {r.title}
                </Link>
                <StatusPill status={r.status} />
                <span className="text-caption text-label-tertiary hidden md:inline tabular-nums">
                  {formatDate(r.updated_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function StatusPill({ status }: { status: FeatureRequestStatus }) {
  const inFlight = isInFlight(status);
  return (
    <span
      className={classNames(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium border",
        STATUS_COLOR[status],
      )}
    >
      {inFlight && (
        <span className="relative inline-flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full rounded-full bg-current opacity-60 animate-ping" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
        </span>
      )}
      {STATUS_LABEL[status]}
    </span>
  );
}

// ── Submit ────────────────────────────────────────────────────────────────────

function Submit() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    title: "",
    description: "",
    request_type: "feature",
    priority: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const req = await api.submitFeatureRequest({
        title: form.title,
        description: form.description,
        request_type: form.request_type,
        priority: form.priority || undefined,
      });
      navigate(`../${req.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-5 pb-10">
      <Link to=".." className="text-subheadline text-accent hover:underline">
        ← Back
      </Link>
      <div>
        <h1 className="text-title-2 text-label">Submit a request</h1>
        <p className="text-subheadline text-label-secondary mt-1">
          Describe what you want changed. The agent will turn it into a PR.
        </p>
      </div>
      <Card>
        <form onSubmit={submit} className="space-y-4">
          <Select
            label="Type"
            value={form.request_type}
            onChange={(e) => setForm({ ...form, request_type: e.target.value })}
          >
            <option value="feature">Feature</option>
            <option value="bug">Bug</option>
            <option value="enhancement">Enhancement</option>
            <option value="refactor">Refactor</option>
          </Select>
          <Input
            label="Title"
            placeholder="e.g. Add CSV export to the audit log page"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            required
            minLength={4}
            autoFocus
          />
          <Textarea
            label="Describe the problem or feature in detail"
            rows={8}
            placeholder={
              "Paste a bug repro, or describe the new feature with acceptance criteria.\n\nExample:\nThe audit log page lets us filter by module but there's no way to export to CSV for compliance.\n\nAdd a 'Download CSV' button next to the filter row. CSV should include all columns currently shown in the table."
            }
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            required
            minLength={10}
          />
          <Select
            label="Priority (optional — auto-scored if omitted)"
            value={form.priority}
            onChange={(e) => setForm({ ...form, priority: e.target.value })}
          >
            <option value="">Auto</option>
            <option value="P0">P0 — Critical</option>
            <option value="P1">P1 — High</option>
            <option value="P2">P2 — Normal</option>
            <option value="P3">P3 — Low</option>
          </Select>
          <div className="rounded-lg bg-indigo-50/60 border border-indigo-100 px-4 py-3 text-xs text-indigo-900 flex items-start gap-2">
            <GitHubLogo className="w-4 h-4 mt-0.5 shrink-0" />
            <div>
              On submit, the agent opens a tracking issue + a feature branch, drafts the
              implementation, opens a PR, and pings you for review. <strong>No PR auto-merges</strong> —
              a Legal Admin / Super Admin must approve it.
            </div>
          </div>
          {error && <p className="text-sm text-error">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => navigate("..")}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Submitting…" : "Submit to agent"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

// ── Detail ────────────────────────────────────────────────────────────────────

function Detail() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [req, setReq] = useState<FeatureRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    if (!id) return;
    const r = await api.getFeatureRequest(Number(id));
    setReq(r);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while in flight
  useEffect(() => {
    if (!req) return;
    if (!isInFlight(req.status)) return;
    const i = setInterval(load, 1800);
    return () => clearInterval(i);
  }, [req, load]);

  // Auto-scroll log to bottom on new entries
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [req?.agent_log?.length]);

  if (!req) return <div className="text-label-secondary text-subheadline">Loading…</div>;

  const canApprove = hasPermission(user, "build_pr_approve");
  const currentStep = stepIndex(req.status);

  async function approve() {
    setBusy(true);
    try {
      await api.approvePR(req!.id);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function reject() {
    const reason = window.prompt("Reason for rejection:");
    if (!reason) return;
    setBusy(true);
    try {
      await api.rejectFeatureRequest(req!.id, reason);
      await load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6 pb-10">
      <Link to=".." className="text-subheadline text-accent hover:underline">
        ← Back
      </Link>

      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <Badge className={TYPE_COLOR[req.request_type] || ""}>{req.request_type}</Badge>
          <Badge className={PRIORITY_COLOR[req.priority]}>{req.priority}</Badge>
          <StatusPill status={req.status} />
          {req.github_issue_url && (
            <a
              href={req.github_issue_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-caption text-label-secondary hover:text-label bg-bg border border-separator/40 rounded-full px-2 py-0.5"
            >
              <GitHubLogo className="w-3 h-3" />
              <span>#{req.github_issue_number}</span>
            </a>
          )}
          {req.pr_url && (
            <a
              href={req.pr_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-caption text-label-secondary hover:text-label bg-bg border border-separator/40 rounded-full px-2 py-0.5"
            >
              <Icon.PullRequest className="w-3 h-3" />
              <span>PR #{req.pr_number}</span>
            </a>
          )}
        </div>
        <h1 className="text-title-2 text-label">{req.title}</h1>
        <p className="text-subheadline text-label-secondary mt-1">
          {req.repository ? `${req.repository} · ` : ""}
          model <span className="font-mono">{req.model_version}</span>
        </p>
      </div>

      {/* Timeline */}
      <Card>
        <div className="flex items-center gap-2 overflow-x-auto scrollbar-thin pb-2">
          {TIMELINE_STEPS.map((s, i) => {
            const reached = currentStep >= i || req.status === "deployed";
            const active = currentStep === i && isInFlight(req.status);
            const I = Icon[s.icon];
            return (
              <div key={s.label} className="flex items-center gap-2 shrink-0">
                <div className="flex flex-col items-center min-w-[80px]">
                  <div
                    className={classNames(
                      "w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all",
                      reached
                        ? "bg-success border-success text-white"
                        : active
                        ? "bg-indigo-500 border-indigo-500 text-white animate-pulse-soft"
                        : "bg-bg border-separator/40 text-label-tertiary",
                    )}
                  >
                    <I className="w-5 h-5" />
                  </div>
                  <div
                    className={classNames(
                      "text-[10px] mt-1.5 font-medium uppercase tracking-wider text-center",
                      reached
                        ? "text-emerald-700"
                        : active
                        ? "text-indigo-700"
                        : "text-label-tertiary",
                    )}
                  >
                    {s.label}
                  </div>
                </div>
                {i < TIMELINE_STEPS.length - 1 && (
                  <div
                    className={classNames(
                      "h-0.5 w-8 md:w-12 transition-colors",
                      currentStep > i ? "bg-emerald-400" : "bg-separator/40",
                    )}
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* Action bar — human gate */}
        {req.status === "pr_open" && (
          <div className="mt-4 rounded-lg border border-warning/20 bg-amber-50 p-4 animate-fade-in">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="flex items-start gap-3">
                <div className="rounded-md bg-bg p-2 text-amber-700 shrink-0">
                  <Icon.PullRequest className="w-5 h-5" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-amber-900">
                    Pull request awaiting human review
                  </p>
                  <p className="text-xs text-amber-800 mt-0.5">
                    {canApprove
                      ? "Review the changes on GitHub and approve to trigger merge + deploy."
                      : "A Legal Admin / Super Admin must approve to proceed."}
                  </p>
                </div>
              </div>
              {canApprove && (
                <div className="flex gap-2 shrink-0">
                  <Button variant="secondary" disabled={busy} onClick={reject}>
                    Reject
                  </Button>
                  <Button disabled={busy} onClick={approve}>
                    <Icon.Check className="w-4 h-4 mr-1" />
                    Approve & merge
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}

        {req.status === "deployed" && req.deployment_url && (
          <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-4 animate-fade-in flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-3 min-w-0">
              <div className="rounded-md bg-bg p-2 text-emerald-700 shrink-0">
                <Icon.Rocket className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-emerald-900">Deployed</p>
                <p className="text-xs text-emerald-800 truncate">{req.deployment_url}</p>
              </div>
            </div>
            <a
              href={req.deployment_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-md bg-emerald-600 text-white hover:bg-emerald-700"
            >
              Open
              <Icon.ArrowRight className="w-3.5 h-3.5" />
            </a>
          </div>
        )}

        {(req.status === "failed" || req.status === "rejected") && (
          <div className="mt-4 rounded-lg border border-error/20 bg-red-50 p-4 animate-fade-in">
            <p className="text-sm font-semibold text-red-900">
              {req.status === "failed" ? "Build failed" : "Request rejected"}
            </p>
            <p className="text-xs text-red-800 mt-1">
              See the agent log below for details. You can submit a revised request.
            </p>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left: details */}
        <div className="lg:col-span-2 space-y-5">
          <Card title="Description">
            <p className="text-subheadline text-label whitespace-pre-wrap leading-relaxed">
              {req.description}
            </p>
          </Card>

          {req.plan && req.plan.length > 0 && (
            <Card title="Implementation plan" subtitle={`${req.loc_estimate ?? "—"} LOC estimate`}>
              <ol className="space-y-2">
                {req.plan.map((step, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="shrink-0 w-6 h-6 rounded-full bg-bg-secondary text-label-secondary text-caption font-medium flex items-center justify-center">
                      {i + 1}
                    </span>
                    <div className="min-w-0">
                      <div className="text-subheadline text-label">{step.step}</div>
                      {step.files && step.files.length > 0 && (
                        <div className="text-caption text-label-tertiary font-mono mt-0.5 truncate">
                          {step.files.slice(0, 3).join("  ·  ")}
                          {step.files.length > 3 ? ` · +${step.files.length - 3}` : ""}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          )}

          {req.diff_summary && (
            <Card title="Diff summary" subtitle={req.branch_name || ""}>
              <p className="text-subheadline text-label">{req.diff_summary}</p>
              {req.files_touched && req.files_touched.length > 0 && (
                <div className="mt-3 space-y-1">
                  <p className="text-caption font-medium text-label-secondary uppercase tracking-wider">
                    Files touched
                  </p>
                  <ul className="text-caption font-mono text-label space-y-0.5">
                    {req.files_touched.map((f) => (
                      <li key={f} className="flex items-center gap-2">
                        <Icon.Code className="w-3 h-3 text-label-tertiary" />
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          )}
        </div>

        {/* Right: live agent log */}
        <div>
          <Card
            title={
              <div className="flex items-center gap-2">
                <Icon.Activity className="w-4 h-4 text-indigo-600" />
                <span>Agent log</span>
                {isInFlight(req.status) && (
                  <span className="text-[10px] uppercase tracking-wider text-indigo-600 animate-pulse-soft">
                    Live
                  </span>
                )}
              </div>
            }
          >
            <div className="max-h-[520px] overflow-y-auto scrollbar-thin pr-2">
              <ul className="space-y-3">
                {req.agent_log.map((entry, i) => (
                  <LogLine key={i} entry={entry} />
                ))}
                <div ref={logEndRef} />
              </ul>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function LogLine({ entry }: { entry: AgentLogEntry }) {
  const dot =
    entry.level === "success"
      ? "bg-success"
      : entry.level === "warn"
      ? "bg-amber-500"
      : entry.level === "error"
      ? "bg-red-500"
      : "bg-indigo-400";
  return (
    <li className="flex gap-3 animate-fade-in">
      <div className="flex flex-col items-center shrink-0">
        <div className={classNames("w-2 h-2 rounded-full mt-1.5", dot)} />
        <div className="w-px flex-1 bg-separator/40 mt-1" />
      </div>
      <div className="min-w-0 flex-1 pb-1">
        <div className="text-caption text-label-tertiary tabular-nums">{formatDate(entry.at)}</div>
        <div className="text-subheadline text-label leading-snug">{entry.message}</div>
        <div className="text-[10px] uppercase tracking-wider text-label-tertiary mt-0.5">
          {entry.stage}
        </div>
      </div>
    </li>
  );
}
