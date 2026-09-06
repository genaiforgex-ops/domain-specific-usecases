import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ClassificationAgent, ClassificationJob, EvidenceItem, Vendor } from "../../api/client";
import { openBlobInTab } from "../../api/download";
import { AISuggestionPanel } from "../../components/AISuggestionPanel";
import { ClauseViewerPanel, ClauseViewerTarget } from "../../components/ClauseViewerPanel";
import { useAuth } from "../../app/AuthContext";
import { useEffectiveAdmin } from "../../app/ViewModeContext";
import { useToast } from "../../app/ToastContext";
import { renderHighlighted } from "../../utils/highlight";

function spansFor(evidence: EvidenceItem[] | undefined, className: string) {
  return (evidence ?? [])
    .filter((e) => e.doc_span)
    .map((e) => ({ start: e.doc_span!.start, end: e.doc_span!.end, className }));
}
import {
  PageHeader,
  Card,
  Button,
  FormField,
  Select,
  Textarea,
  DataTable,
  StatusBadge,
  Tabs,
  Badge,
  EmptyState,
  Input,
  TableSkeleton,
} from "../../components/ui";
import { formatLabel, formatPercent } from "../../utils/format";

export function M1Page() {
  const [params] = useSearchParams();
  const { user } = useAuth();
  const effectiveIsAdmin = useEffectiveAdmin();
  const toast = useToast();
  const [tab, setTab] = useState(effectiveIsAdmin ? "new" : "review");
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [jobs, setJobs] = useState<ClassificationJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [activeClause, setActiveClause] = useState<ClauseViewerTarget | null>(null);
  const [selected, setSelected] = useState<ClassificationJob | null>(null);
  const [vendorId, setVendorId] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [agents, setAgents] = useState<ClassificationAgent[]>([]);
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([]);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [overrideLabel, setOverrideLabel] = useState("");
  const [justification, setJustification] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmedJob, setConfirmedJob] = useState<ClassificationJob | null>(null);
  const canApprove = effectiveIsAdmin && user?.roles.includes("admin");

  // Fetch a binary endpoint and open it in a new tab. Report PDFs preview
  // inline; the source-document endpoint sets an attachment disposition so the
  // browser downloads it.
  const download = async (path: string, errorMsg: string) => {
    try {
      await openBlobInTab(path);
    } catch {
      toast.error(errorMsg);
    }
  };
  const downloadReport = (job: ClassificationJob) =>
    download(`/classifications/${job.id}/report.pdf`, "Couldn't download the report. Please try again.");
  const downloadSourceDoc = (job: ClassificationJob) =>
    download(`/classifications/${job.id}/document`, "Couldn't download the document. Please try again.");

  // RBI and SEBI are classified independently and can disagree, which is the
  // whole point of the review queue — so each regulator gets its own column
  // with its own confidence rather than being collapsed into the job's legacy
  // ai_label (that field is only a mirror of the RBI result).
  const regulatorCell = (label: string | null, confidence: number | null) => (
    <>
      {formatLabel(label)}
      {confidence != null && (
        <span style={{ marginLeft: 6, color: "var(--color-label-secondary)", fontSize: 12 }}>
          {formatPercent(confidence)}
        </span>
      )}
    </>
  );

  // The typed assessment text only — input_text also carries the extracted
  // document content after a "--- Document content ---" marker, which we drop
  // for this preview. Truncated with the full text on hover.
  const assessmentCell = (j: ClassificationJob) => {
    const full = (j.input_text || "").split("--- Document content ---")[0].trim();
    return full ? (
      <span
        title={full}
        style={{ display: "inline-block", maxWidth: 260, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", verticalAlign: "middle" }}
      >
        {full}
      </span>
    ) : (
      <span style={{ color: "var(--slate-400)" }}>—</span>
    );
  };

  const load = () => {
    api.get<Vendor[]>("/vendors").then(setVendors).catch(() => {});
    api
      .get<ClassificationJob[]>("/classifications")
      .then(setJobs)
      .catch(() => toast.error("Couldn't load classifications. Please refresh."))
      .finally(() => setLoadingJobs(false));
    api.get<{ ai_enabled: boolean }>("/classifications/ai-status").then((s) => setAiEnabled(s.ai_enabled)).catch(() => {});
    api.get<ClassificationAgent[]>("/m1/agents").then(setAgents).catch(() => {});
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    const jobId = params.get("job");
    if (jobId) {
      api.get<ClassificationJob>(`/classifications/${jobId}`).then((j) => {
        setSelected(j);
        setTab("review");
      });
    }
  }, [params]);

  const submit = async () => {
    if (!vendorId || (!text && !file)) return;
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("vendor_id", vendorId);
      fd.append("text", text);
      // Empty = built-in default run (unchanged behavior); otherwise each selected
      // agent runs and produces its own result for side-by-side comparison.
      if (selectedAgentIds.length) fd.append("agent_ids", selectedAgentIds.join(","));
      if (file) fd.append("file", file);
      const job = await api.upload<ClassificationJob>("/classifications", fd);
      setText("");
      setFile(null);
      const ready = await pollJob(job.id);
      setTab("review");
      if (ready) toast.success("Classification ready for review.");
      else toast.info("Classification is taking longer than expected — check the Review tab shortly.");
    } catch {
      toast.error("Couldn't run the classification. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const pollJob = async (id: string): Promise<boolean> => {
    for (let i = 0; i < 15; i++) {
      const j = await api.get<ClassificationJob>(`/classifications/${id}`);
      if (j.status === "ready" || j.status === "confirmed") {
        setSelected(j);
        load();
        return true;
      }
      await new Promise((r) => setTimeout(r, 800));
    }
    return false;
  };

  const [overrideSource, setOverrideSource] = useState<"rbi" | "sebi" | null>(null);
  // Which agent produced the result being overridden (null = built-in default run).
  // Used as the base prompt when the reviewer chooses "create new agent".
  const [overrideAgentId, setOverrideAgentId] = useState<string | null>(null);
  // Optional "learning" the reviewer folds into an agent's prompt on override.
  const [learningInfo, setLearningInfo] = useState("");
  const [learningTarget, setLearningTarget] = useState("");  // agent id, or "__new__"
  const [newAgentName, setNewAgentName] = useState("");

  // Confirm a specific label (used by the multi-agent comparison, where the
  // chosen result may be from any agent). confirm() passes the explicit label,
  // which the backend prefers over deriving from the job's own rbi_/sebi_ fields.
  const confirmLabel = async (label: string | null, source: "rbi" | "sebi") => {
    if (!selected || !label) return;
    setConfirming(true);
    try {
      const updated = await api.post<ClassificationJob>(`/classifications/${selected.id}/confirm`, { label, source });
      load();
      setSelected(null);
      setConfirmedJob(updated);
      toast.success(`Classification confirmed: ${formatLabel(label)}.`);
    } catch {
      toast.error("Couldn't confirm the classification. Please try again.");
    } finally {
      setConfirming(false);
    }
  };

  const confirm = async (source: "rbi" | "sebi") => {
    if (!selected) return;
    setConfirming(true);
    try {
      const updated = await api.post<ClassificationJob>(`/classifications/${selected.id}/confirm`, { source });
      load();
      setSelected(null);
      setConfirmedJob(updated);
      toast.success(`${source.toUpperCase()} classification confirmed.`);
    } catch {
      toast.error("Couldn't confirm the classification. Please try again.");
    } finally {
      setConfirming(false);
    }
  };

  const doOverride = async () => {
    if (!selected || justification.length < 20) return;
    // If a learning was entered, it needs a target (an agent, or "create new"
    // with a name); guard so we don't silently drop it.
    const hasLearning = learningInfo.trim().length > 0;
    if (hasLearning && !learningTarget) {
      toast.error("Choose which agent the learning should go to.");
      return;
    }
    if (hasLearning && learningTarget === "__new__" && !newAgentName.trim()) {
      toast.error("Enter a name for the new agent.");
      return;
    }
    setConfirming(true);
    try {
      const updated = await api.post<ClassificationJob>(`/classifications/${selected.id}/override`, {
        label: overrideLabel,
        justification,
        source: overrideSource,
        ...(hasLearning
          ? {
              learning_info: learningInfo,
              learning_mode: learningTarget === "__new__" ? "new" : "existing",
              target_agent_id: learningTarget === "__new__" ? null : learningTarget,
              new_agent_name: learningTarget === "__new__" ? newAgentName : null,
              base_agent_id: overrideAgentId,
            }
          : {}),
      });
      if (hasLearning) api.get<ClassificationAgent[]>("/m1/agents").then(setAgents).catch(() => {});
      load();
      setSelected(null);
      setOverrideLabel("");
      setJustification("");
      setOverrideSource(null);
      setOverrideAgentId(null);
      setLearningInfo("");
      setLearningTarget("");
      setNewAgentName("");
      setConfirmedJob(updated);
      toast.success(hasLearning ? "Override recorded and learning applied." : "Override recorded.");
    } catch (err) {
      toast.error((err as Error).message || "Couldn't save the override. Please try again.");
    } finally {
      setConfirming(false);
    }
  };

  const pendingReview = jobs.filter((j) => j.status === "ready");

  return (
    <div>
      <ClauseViewerPanel target={activeClause} onClose={() => setActiveClause(null)} />
      <PageHeader
        breadcrumb="M1 · Outsourcing"
        title="Outsourcing Risk Classification"
        subtitle="AI-assisted classification against RBI / SEBI outsourcing definitions. Every label requires human confirmation."
        action={
          pendingReview.length > 0 ? (
            <Badge variant="warning">{pendingReview.length} awaiting review</Badge>
          ) : undefined
        }
      />

      <Tabs
        tabs={[
          ...(effectiveIsAdmin ? [{ id: "new", label: "New assessment" }] : []),
          { id: "review", label: "Review" },
          { id: "history", label: "History" },
        ]}
        active={tab}
        onChange={setTab}
      />

      {effectiveIsAdmin && tab === "new" && (
        <Card className="mb-24">
          <h2 className="card__title">Submit vendor assessment</h2>
          <div className="form-grid form-grid--2">
            <FormField label="Vendor" required>
              <Select value={vendorId} onChange={(e) => setVendorId(e.target.value)}>
                <option value="">Select vendor…</option>
                {vendors.map((v) => (
                  <option key={v.id} value={v.id}>{v.legal_name}</option>
                ))}
              </Select>
            </FormField>
            <FormField label="Document upload" hint="PDF, DOCX, XLSX, or plain text — optional">
              <Input
                type="file"
                accept=".pdf,.docx,.xlsx,.txt"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                disabled={!vendorId}
              />
              {file && <div style={{ fontSize: 12, color: "var(--slate-600)", marginTop: 4 }}>{file.name}</div>}
            </FormField>
            <FormField label="Assessment text" hint="Required if no document attached">
              <Textarea
                rows={6}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste scope-of-work, contract excerpts, or assessment narrative…"
              />
            </FormField>
          </div>
          {agents.length > 0 && (
            <div className="mt-16">
              <FormField
                label="Classification agents"
                hint="Pick one or more to compare their prompts side-by-side. Leave all unchecked to use the built-in default."
              >
                <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                  {agents.map((a) => (
                    <label key={a.id} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14, cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={selectedAgentIds.includes(a.id)}
                        onChange={(e) =>
                          setSelectedAgentIds((prev) =>
                            e.target.checked ? [...prev, a.id] : prev.filter((id) => id !== a.id)
                          )
                        }
                      />
                      {a.name}
                    </label>
                  ))}
                </div>
              </FormField>
            </div>
          )}
          <div className="mt-16">
            <Button variant="primary" onClick={submit} loading={submitting} disabled={!vendorId || (!text && !file)}>
              {submitting ? "Classifying…" : "Run classification"}
            </Button>
          </div>
        </Card>
      )}

      {tab === "review" && (
        <>
          {confirmedJob && (
            <Card className="mb-24">
              <h2 className="card__title">Classification confirmed ✓</h2>
              <p style={{ margin: "0 0 16px", color: "var(--slate-600)" }}>
                Final label: <strong>{formatLabel(confirmedJob.final_label)}</strong> for{" "}
                {vendors.find((v) => v.id === confirmedJob.vendor_id)?.legal_name ?? "this vendor"}.
              </p>
              <div style={{ display: "flex", gap: 12 }}>
                <Button variant="primary" onClick={() => downloadReport(confirmedJob)}>
                  Download report (PDF)
                </Button>
                <Button variant="secondary" onClick={() => { setConfirmedJob(null); setTab("history"); }}>
                  Go to history
                </Button>
              </div>
            </Card>
          )}
          {!selected || selected.status !== "ready" ? (
            <Card>
              {pendingReview.length === 0 ? (
                <EmptyState
                  title="No items in review queue"
                  description="Submit a new assessment or pick one from History."
                  action={<Button variant="secondary" onClick={() => setTab("new")}>New assessment</Button>}
                />
              ) : (
                <>
                  <p style={{ margin: "0 0 16px", color: "var(--slate-600)" }}>Select a job to review:</p>
                  <DataTable>
                    <thead>
                      <tr><th>Vendor</th><th>RBI label</th><th>SEBI label</th><th>Document</th><th>Assessment</th><th></th></tr>
                    </thead>
                    <tbody>
                      {pendingReview.map((j) => {
                        const v = vendors.find((x) => x.id === j.vendor_id);
                        return (
                          <tr key={j.id}>
                            <td>{v?.legal_name ?? j.vendor_id.slice(0, 8)}</td>
                            <td>{regulatorCell(j.rbi_label, j.rbi_confidence)}</td>
                            <td>{regulatorCell(j.sebi_label, j.sebi_confidence)}</td>
                            <td>
                              {j.document_filename ? (
                                <Button size="sm" variant="ghost" onClick={() => downloadSourceDoc(j)}>
                                  {j.document_filename}
                                </Button>
                              ) : (
                                <span style={{ color: "var(--slate-400)" }}>—</span>
                              )}
                            </td>
                            <td>{assessmentCell(j)}</td>
                            <td>
                              <Button size="sm" variant="primary" onClick={() => { setConfirmedJob(null); setSelected(j); }}>Review</Button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </DataTable>
                </>
              )}
            </Card>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <Card>
                <h2 className="card__title">Assessment</h2>
                <dl style={{ margin: 0, display: "grid", gap: 12 }}>
                  <div>
                    <dt style={{ fontSize: 12, color: "var(--slate-500)" }}>Vendor</dt>
                    <dd style={{ fontWeight: 500 }}>{vendors.find((v) => v.id === selected.vendor_id)?.legal_name ?? "—"}</dd>
                  </div>
                  {selected.created_at && (
                    <div>
                      <dt style={{ fontSize: 12, color: "var(--slate-500)" }}>Submitted</dt>
                      <dd>{new Date(selected.created_at).toLocaleString()}</dd>
                    </div>
                  )}
                </dl>
                {selected.input_text && (
                  <div className="mt-16" style={{ padding: 14, background: "var(--slate-50)", borderRadius: 8, fontSize: 13, lineHeight: 1.6 }}>
                    <div style={{ fontSize: 11, color: "var(--slate-500)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                      Assessment text — <span className="mark-rbi">RBI match</span> · <span className="mark-sebi">SEBI match</span>
                    </div>
                    <div className="assessment-text">
                      {renderHighlighted(selected.input_text, [
                        ...spansFor(selected.rbi_evidence?.evidence, "mark-rbi"),
                        ...spansFor(selected.sebi_evidence?.evidence, "mark-sebi"),
                      ])}
                    </div>
                  </div>
                )}
              </Card>
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {selected.agent_runs && selected.agent_runs.length > 0 ? (
                  // One block per agent so the different prompts can be compared;
                  // accepting any panel confirms that agent's chosen label.
                  selected.agent_runs.map((run) => (
                    <Card key={run.id}>
                      <h3 className="card__title">Agent: {run.agent_name}</h3>
                      <div style={{ display: "flex", flexDirection: "row", gap: 16 }}>
                        <div style={{ flex: 1 }}>
                          <AISuggestionPanel
                            regulator="RBI"
                            label={run.rbi_label}
                            confidence={run.rbi_confidence}
                            evidence={run.rbi_evidence?.evidence}
                            reasoning={run.rbi_evidence?.reasoning}
                            truncated={run.rbi_evidence?.truncated}
                            aiEnabled={aiEnabled}
                            onAccept={canApprove ? () => confirmLabel(run.rbi_label, "rbi") : () => toast.error("Risk Manager role required to confirm.")}
                            onReject={() => setSelected(null)}
                            onEdit={() => { setOverrideLabel(run.rbi_label || ""); setOverrideSource("rbi"); setOverrideAgentId(run.agent_id); setLearningTarget(run.agent_id || ""); }}
                            onEvidenceClick={setActiveClause}
                            loading={confirming}
                          />
                        </div>
                        <div style={{ flex: 1 }}>
                          <AISuggestionPanel
                            regulator="SEBI"
                            label={run.sebi_label}
                            confidence={run.sebi_confidence}
                            evidence={run.sebi_evidence?.evidence}
                            reasoning={run.sebi_evidence?.reasoning}
                            truncated={run.sebi_evidence?.truncated}
                            aiEnabled={aiEnabled}
                            onAccept={canApprove ? () => confirmLabel(run.sebi_label, "sebi") : () => toast.error("Risk Manager role required to confirm.")}
                            onReject={() => setSelected(null)}
                            onEdit={() => { setOverrideLabel(run.sebi_label || ""); setOverrideSource("sebi"); setOverrideAgentId(run.agent_id); setLearningTarget(run.agent_id || ""); }}
                            onEvidenceClick={setActiveClause}
                            loading={confirming}
                          />
                        </div>
                      </div>
                    </Card>
                  ))
                ) : (
                <div style={{ display: "flex", flexDirection: "row", gap: 16 }}>
                  <div style={{ flex: 1 }}>
                    <AISuggestionPanel
                      regulator="RBI"
                      label={selected.rbi_label}
                      confidence={selected.rbi_confidence}
                      evidence={selected.rbi_evidence?.evidence}
                      reasoning={selected.rbi_evidence?.reasoning}
                      truncated={selected.rbi_evidence?.truncated}
                      aiEnabled={aiEnabled}
                      onAccept={canApprove ? () => confirm("rbi") : () => toast.error("Risk Manager role required to confirm.")}
                      onReject={() => setSelected(null)}
                      onEdit={() => { setOverrideLabel(selected.rbi_label || ""); setOverrideSource("rbi"); setOverrideAgentId(null); setLearningTarget(""); }}
                      onEvidenceClick={setActiveClause}
                      loading={confirming}
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <AISuggestionPanel
                      regulator="SEBI"
                      label={selected.sebi_label}
                      confidence={selected.sebi_confidence}
                      evidence={selected.sebi_evidence?.evidence}
                      reasoning={selected.sebi_evidence?.reasoning}
                      truncated={selected.sebi_evidence?.truncated}
                      aiEnabled={aiEnabled}
                      onAccept={canApprove ? () => confirm("sebi") : () => toast.error("Risk Manager role required to confirm.")}
                      onReject={() => setSelected(null)}
                      onEdit={() => { setOverrideLabel(selected.sebi_label || ""); setOverrideSource("sebi"); setOverrideAgentId(null); setLearningTarget(""); }}
                      onEvidenceClick={setActiveClause}
                      loading={confirming}
                    />
                  </div>
                </div>
                )}
                {overrideLabel && overrideSource && canApprove && (
                  <Card>
                    <h3 className="card__title">Override — {overrideSource.toUpperCase()} classification</h3>
                    <div className="form-grid">
                      <FormField label="Final label">
                        <Select value={overrideLabel} onChange={(e) => setOverrideLabel(e.target.value)}>
                          <option value="financial_outsourcing">Financial Outsourcing</option>
                          <option value="it_outsourcing">IT Outsourcing</option>
                          <option value="non_outsourcing">Non-Outsourcing</option>
                        </Select>
                      </FormField>
                      <FormField label="Justification" required hint="Minimum 20 characters">
                        <Textarea value={justification} onChange={(e) => setJustification(e.target.value)} rows={3} />
                      </FormField>
                      <FormField
                        label="Learning / prompt improvement"
                        hint="Optional — a note to fold into an agent's prompt so it classifies better next time."
                      >
                        <Textarea
                          value={learningInfo}
                          onChange={(e) => setLearningInfo(e.target.value)}
                          rows={3}
                          placeholder={`e.g. Treat telecom connectivity as non_outsourcing unless the vendor also runs a the client function.`}
                        />
                      </FormField>
                      {learningInfo.trim() && (
                        <FormField
                          label={`Apply learning to (${overrideSource?.toUpperCase()} prompt)`}
                          required
                          hint="Adds it to the chosen agent's prompt in place, or seeds a new agent from the prompt used here."
                        >
                          <Select value={learningTarget} onChange={(e) => setLearningTarget(e.target.value)}>
                            <option value="">Select…</option>
                            {agents.map((a) => (
                              <option key={a.id} value={a.id}>{a.name}</option>
                            ))}
                            <option value="__new__">➕ Create new agent…</option>
                          </Select>
                        </FormField>
                      )}
                      {learningInfo.trim() && learningTarget === "__new__" && (
                        <FormField label="New agent name" required>
                          <Input value={newAgentName} onChange={(e) => setNewAgentName(e.target.value)} placeholder="e.g. Telecom-aware v1" />
                        </FormField>
                      )}
                      <Button variant="primary" onClick={doOverride} loading={confirming} disabled={justification.length < 20}>
                        {confirming ? "Saving…" : "Submit override"}
                      </Button>
                    </div>
                  </Card>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {tab === "history" && (
        <Card>
          <DataTable>
            <thead>
              <tr>
                <th>Vendor</th>
                <th>Status</th>
                <th>AI suggestion</th>
                <th>Final label</th>
                <th>Confidence</th>
                <th>Document</th>
                <th>Assessment</th>
                <th></th>
              </tr>
            </thead>
            {loadingJobs ? (
              <TableSkeleton columns={8} />
            ) : (
            <tbody>
              {jobs.length === 0 ? (
                <tr><td colSpan={8}><EmptyState title="No classifications yet" /></td></tr>
              ) : (
                jobs.map((j) => (
                  <tr key={j.id}>
                    <td>{vendors.find((v) => v.id === j.vendor_id)?.legal_name ?? j.vendor_id.slice(0, 8)}</td>
                    <td><StatusBadge status={j.status} /></td>
                    <td>{formatLabel(j.ai_label)}</td>
                    <td>{formatLabel(j.final_label)}</td>
                    <td>{formatPercent(j.ai_confidence)}</td>
                    <td>
                      {j.document_filename ? (
                        <Button size="sm" variant="ghost" onClick={() => downloadSourceDoc(j)}>
                          {j.document_filename}
                        </Button>
                      ) : (
                        <span style={{ color: "var(--slate-400)" }}>—</span>
                      )}
                    </td>
                    <td>{assessmentCell(j)}</td>
                    <td style={{ display: "flex", gap: 8 }}>
                      <Button size="sm" variant="ghost" onClick={() => { setConfirmedJob(null); setSelected(j); setTab("review"); }}>
                        Open
                      </Button>
                      {j.final_label && (
                        <Button size="sm" variant="ghost" onClick={() => downloadReport(j)}>
                          Download
                        </Button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
            )}
          </DataTable>
        </Card>
      )}
    </div>
  );
}
