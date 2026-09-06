import { useEffect, useState } from "react";
import { api, ApiError, DDReport, Vendor } from "../../api/client";
import { openBlobInTab } from "../../api/download";
import { useAuth } from "../../app/AuthContext";
import { useToast } from "../../app/ToastContext";
import {
  PageHeader,
  Card,
  Button,
  FormField,
  Input,
  DataTable,
  StatusBadge,
  Badge,
  Tabs,
  EmptyState,
  Spinner,
  TableSkeleton,
} from "../../components/ui";
import { AuditReport } from "./AuditReport";

// Areas the screening agent works through. We can't get true per-step
// progress from the backend, so this panel shows an honest sense of *motion*
// and scope during the 20–60s run rather than claiming each step is finished.
const DD_STEPS = [
  "Scraping the vendor website",
  "Screening sanctions & watchlists",
  "Checking litigation records",
  "Scanning adverse media",
  "Assessing financial distress",
  "Reviewing ownership & security",
];

function DDProgress() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, []);
  // Advance roughly one step every 6s, then hold on the last while finishing.
  const active = Math.min(DD_STEPS.length - 1, Math.floor(elapsed / 6));
  return (
    <Card>
      <div className="dd-progress">
        <Spinner size="lg" />
        <h2 style={{ margin: "16px 0 4px" }}>Running due diligence…</h2>
        <p className="dd-progress__sub">
          Screening across public sources. This usually takes 20–60 seconds — you can leave this open.
        </p>
        <div className="dd-progress__steps">
          {DD_STEPS.map((step, i) => (
            <div
              key={i}
              className={`dd-step ${i < active ? "dd-step--done" : i === active ? "dd-step--active" : ""}`}
            >
              <span className="dd-step__marker">
                {i < active ? "✓" : i === active ? <Spinner size="sm" /> : "○"}
              </span>
              <span>{step}</span>
            </div>
          ))}
        </div>
        <div className="dd-progress__timer">{elapsed}s elapsed</div>
      </div>
    </Card>
  );
}

const CATEGORY_LABELS: Record<string, string> = {
  litigation: "Litigation",
  regulatory_action: "Regulatory action",
  adverse_media: "Adverse media",
  financial_distress: "Financial distress",
  sanctions: "Sanctions / watchlist",
  ownership: "Ownership concerns",
  security: "Security / threat-intel",
  web_presence: "Web presence / compliance",
};

export function M2Page() {
  const { user } = useAuth();
  const toast = useToast();
  const [tab, setTab] = useState("vendors");
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [loadingVendors, setLoadingVendors] = useState(true);
  const [report, setReport] = useState<DDReport | null>(null);
  // Track WHICH vendor's DD is running, so only that row shows "Running…"
  const [runningId, setRunningId] = useState<string | null>(null);
  const [signingOff, setSigningOff] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ legal_name: "", website: "", country: "IN" });
  const [formError, setFormError] = useState("");
  const canApprove = user?.roles.includes("admin");

  const loadVendors = () =>
    api
      .get<Vendor[]>("/vendors")
      .then(setVendors)
      .catch(() => toast.error("Couldn't load the vendor registry. Please refresh."))
      .finally(() => setLoadingVendors(false));

  useEffect(() => { loadVendors(); }, []);

  const createVendor = async () => {
    if (!form.legal_name.trim() || !form.website.trim()) {
      setFormError("Legal name and official website are both required to run due diligence.");
      return;
    }
    setFormError("");
    setCreating(true);
    try {
      const vendor = await api.post<Vendor>("/vendors", form);
      setForm({ legal_name: "", website: "", country: "IN" });
      loadVendors();
      toast.success("Vendor registered — starting due diligence.");
      // Registering a vendor is a request to screen it, so kick off the first
      // DD run right away and drop the user on the live progress panel.
      setRunningId(vendor.id);
      try {
        await startRun(vendor.id);
      } finally {
        setRunningId(null);
      }
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed to create vendor");
    } finally {
      setCreating(false);
    }
  };

  // Start a fresh screening (spends an API call). Used when no report
  // exists yet, or when the user explicitly asks to re-screen.
  const startRun = async (vendorId: string) => {
    const r = await api.post<DDReport>(`/vendors/${vendorId}/dd-runs`, {});
    setReport(r);          // show "processing" immediately
    setTab("report");
    await pollReport(r.id);
  };

  // Open a vendor's DD. A screening is expensive and non-deterministic, so this
  // only ever starts one when the vendor genuinely has no report yet — every
  // other case shows what is already there.
  const openDD = async (vendorId: string) => {
    setRunningId(vendorId);
    setReport(null);
    try {
      let latest: DDReport | null = null;
      try {
        latest = await api.get<DDReport>(`/vendors/${vendorId}/dd-reports/latest`);
      } catch (e) {
        // Only a 404 means "no report yet". Treating any failure as a missing
        // report — as `.catch(() => null)` did — turned a transient read error
        // into a fresh billable screening.
        if (!(e instanceof ApiError && e.status === 404)) {
          toast.error(
            e instanceof Error ? e.message : "Couldn't load the saved report. Please try again.",
          );
          return;
        }
      }

      if (!latest) {
        await startRun(vendorId);
        return;
      }

      setReport(latest);
      setTab("report");
      // Attach to a run that is still going rather than queueing another one.
      if (latest.status === "processing") {
        await pollReport(latest.id);
      }
    } finally {
      setRunningId(null);
    }
  };

  // Explicit re-screen — a new, dated snapshot.
  const rerun = async (vendorId: string) => {
    setRunningId(vendorId);
    setReport(null);
    try {
      await startRun(vendorId);
    } finally {
      setRunningId(null);
    }
  };

  const pollReport = async (id: string) => {
    // Real DD (scrape + grounded Gemini) runs in the background worker and
    // can take 20-60s, so poll patiently and stop on terminal states.
    for (let i = 0; i < 60; i++) {
      const r = await api.get<DDReport>(`/dd-reports/${id}`);
      setReport(r);
      if (r.status === "ready" || r.status === "signed_off") {
        toast.success("Due diligence complete.");
        return;
      }
      if (r.status === "failed") {
        toast.error("Screening failed. See the report for details.");
        return;
      }
      await new Promise((res) => setTimeout(res, 2000));
    }
    toast.info("Screening is taking longer than usual. Try re-opening the report shortly.");
  };

  const signOff = async () => {
    if (!report) return;
    setSigningOff(true);
    try {
      await api.post(`/dd-reports/${report.id}/sign-off`, {});
      const r = await api.get<DDReport>(`/dd-reports/${report.id}`);
      setReport(r);
      toast.success("Report signed off.");
    } catch {
      toast.error("Sign-off failed. Please try again.");
    } finally {
      setSigningOff(false);
    }
  };

  const exportPdf = async () => {
    if (!report) return;
    setExporting(true);
    try {
      await openBlobInTab(`/dd-reports/${report.id}/export.pdf`);
      toast.success("PDF exported.");
    } catch {
      toast.error("Couldn't export the PDF. Please try again.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      <PageHeader
        breadcrumb="M2 · Vendor DD"
        title="Vendor Due Diligence"
        subtitle="Evidence-led screening from public sources. Red-flag scoring with explainable category weights."
      />

      <Tabs
        tabs={[
          { id: "vendors", label: "Vendor registry" },
          { id: "register", label: "Register new" },
          { id: "report", label: "DD report" },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "register" && (
        <Card className="mb-24">
          <h2 className="card__title">Register vendor</h2>
          <p style={{ marginTop: -4, marginBottom: 12, fontSize: 13, color: "var(--slate-500)" }}>
            Only the legal name and official website are needed to run due diligence.
          </p>
          <div className="form-grid form-grid--2">
            <FormField label="Legal name" required>
              <Input value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} placeholder="Acme IT Services Pvt Ltd" />
            </FormField>
            <FormField label="Official website" required>
              <Input value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} placeholder="https://www.acme.com" />
            </FormField>
          </div>
          {formError && <p style={{ color: "#991b1b", fontSize: 13, marginTop: 10 }}>{formError}</p>}
          <Button variant="primary" className="mt-16" onClick={createVendor} loading={creating}>
            {creating ? "Creating…" : "Create vendor & run DD"}
          </Button>
        </Card>
      )}

      {tab === "vendors" && (
        <Card>
          {loadingVendors ? (
            <DataTable>
              <thead>
                <tr><th>Legal name</th><th>Website</th><th>CIN</th><th></th></tr>
              </thead>
              <TableSkeleton columns={4} />
            </DataTable>
          ) : vendors.length === 0 ? (
            <EmptyState title="No vendors registered" action={<Button onClick={() => setTab("register")}>Register vendor</Button>} />
          ) : (
            <DataTable>
              <thead>
                <tr><th>Legal name</th><th>Website</th><th>CIN</th><th></th></tr>
              </thead>
              <tbody>
                {vendors.map((v) => (
                  <tr key={v.id}>
                    <td><strong>{v.legal_name}</strong></td>
                    <td>{v.website ? <a href={v.website} target="_blank" rel="noreferrer">{v.website}</a> : "—"}</td>
                    <td className="mono">{v.cin ?? "—"}</td>
                    <td>
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => openDD(v.id)}
                        loading={runningId === v.id}
                        disabled={runningId !== null}
                      >
                        {runningId === v.id ? "Opening…" : "Open DD"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          )}
        </Card>
      )}

      {tab === "report" && (
        <>
          {!report ? (
            <Card>
              <EmptyState
                title="No report selected"
                description="Run due diligence on a vendor from the registry tab."
                action={<Button variant="secondary" onClick={() => setTab("vendors")}>Go to vendors</Button>}
              />
            </Card>
          ) : report.status === "processing" ? (
            <DDProgress />
          ) : report.status === "failed" ? (
            <Card>
              <EmptyState
                title="Screening failed"
                description={report.error || "The due-diligence run could not complete. Please retry."}
                action={
                  <div style={{ display: "flex", gap: 8 }}>
                    {/* Retrying is now an explicit choice — a failed report used
                        to re-screen itself the moment the vendor was opened. */}
                    <Button onClick={() => rerun(report.vendor_id)}>Retry screening</Button>
                    <Button variant="secondary" onClick={() => setTab("vendors")}>Back to vendors</Button>
                  </div>
                }
              />
            </Card>
          ) : (
            <div>
              {/* Sticky action bar — status on the left, actions on the right */}
              <div
                style={{
                  position: "sticky", top: 0, zIndex: 5,
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  gap: 12, flexWrap: "wrap", marginBottom: 20, padding: "10px 0",
                  background: "var(--bg, #f8fafc)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <h2 style={{ margin: 0, fontSize: 18 }}>DD report</h2>
                  <StatusBadge status={report.status} />
                  {report.created_at && (
                    <span style={{ fontSize: 12, color: "var(--slate-500)" }}>
                      snapshot as of {new Date(report.created_at).toLocaleString()}
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  {canApprove && report.status === "ready" && (
                    <Button variant="primary" onClick={signOff} loading={signingOff}>
                      {signingOff ? "Signing off…" : "Manager sign-off"}
                    </Button>
                  )}
                  <Button
                    variant="secondary"
                    onClick={() => rerun(report.vendor_id)}
                    loading={runningId === report.vendor_id}
                    disabled={runningId !== null}
                  >
                    {runningId === report.vendor_id ? "Re-screening…" : "Re-run screening"}
                  </Button>
                  <Button variant="secondary" onClick={exportPdf} loading={exporting}>
                    {exporting ? "Exporting…" : "Export PDF"}
                  </Button>
                </div>
              </div>

              {report.audit_data && <AuditReport audit={report.audit_data} />}

              {/* Screening findings — the evidence list, in a responsive grid */}
              {(report.findings?.length ?? 0) > 0 && (
                <Card className="mb-24">
                  <h2 className="card__title">Screening findings ({report.findings.length})</h2>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12 }}>
                    {report.findings.map((f) => (
                      <div
                        key={f.id}
                        className={`finding-card ${f.category === "sanctions" || f.category === "regulatory_action" ? "finding-card--high" : ""}`}
                        style={{ margin: 0 }}
                      >
                        <div className="finding-card__cat">
                          {CATEGORY_LABELS[f.category] ?? f.category}
                          <Badge variant={f.source_tier === "primary" ? "info" : "neutral"}>
                            {f.source_tier}
                          </Badge>
                        </div>
                        <h4>{f.title}</h4>
                        <p>{f.summary}</p>
                        {f.source_url && (
                          <a href={f.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
                            View source →
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {report.outsourcing_checklist && (
                <Card>
                  <h3 className="card__title">Outsourcing checklist (M1 linked)</h3>
                  <p style={{ margin: 0, fontSize: 14, color: "var(--slate-600)" }}>{report.outsourcing_checklist}</p>
                </Card>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
