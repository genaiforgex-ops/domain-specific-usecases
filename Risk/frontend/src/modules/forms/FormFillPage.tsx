import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, FormAssignment, FormImportResult } from "../../api/client";
import { downloadBlob } from "../../api/download";
import { useToast } from "../../app/ToastContext";
import {
  DynamicFormRenderer,
  FormAnswers,
  computeFormProgress,
  findMissingRequired,
} from "../../components/DynamicFormRenderer";
import { Button, StatusBadge } from "../../components/ui";

/** Statuses the M1 job will not move on from, so polling can stop. */
const TERMINAL_CLASSIFICATION = ["ready", "confirmed", "failed"];

/** Idle time before an edit is autosaved. */
const AUTOSAVE_DELAY_MS = 2000;

export function FormFillPage() {
  const { assignmentId } = useParams<{ assignmentId: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const [assignment, setAssignment] = useState<FormAssignment | null>(null);
  const [answers, setAnswers] = useState<FormAnswers>({});
  const [submitting, setSubmitting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [importing, setImporting] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);
  const [invalidFieldIds, setInvalidFieldIds] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // What the server last has. Compared against `answers` to decide whether an
  // autosave is warranted and whether leaving the page would lose work.
  const savedAnswersRef = useRef<string>("{}");
  const [dirty, setDirty] = useState(false);

  const applyAssignment = useCallback((a: FormAssignment) => {
    setAssignment(a);
    const draft = (a.draft_answers ?? a.submission?.answers ?? {}) as FormAnswers;
    setAnswers(draft);
    savedAnswersRef.current = JSON.stringify(draft);
    setDirty(false);
  }, []);

  const load = useCallback(() => {
    if (!assignmentId) return;
    api.get<FormAssignment>(`/forms/assignments/${assignmentId}`).then(applyAssignment);
  }, [assignmentId, applyAssignment]);

  useEffect(() => { load(); }, [load]);

  // Once submitted, M1 classification is running in the background. Poll until
  // it settles so the user sees the outcome without reloading. Only the status
  // fields are copied over — re-applying the whole assignment mid-poll would
  // reset the answers the user can still be looking at.
  const classificationStatus = assignment?.classification_status ?? null;
  const jobId = assignment?.classification_job_id ?? null;
  useEffect(() => {
    if (!assignmentId || !jobId) return;
    if (classificationStatus && TERMINAL_CLASSIFICATION.includes(classificationStatus)) return;
    const timer = window.setInterval(async () => {
      try {
        const fresh = await api.get<FormAssignment>(`/forms/assignments/${assignmentId}`);
        setAssignment((prev) =>
          prev
            ? {
                ...prev,
                classification_status: fresh.classification_status,
                classification_label: fresh.classification_label,
              }
            : fresh,
        );
      } catch {
        /* transient — the next tick retries */
      }
    }, 4000);
    return () => window.clearInterval(timer);
  }, [assignmentId, jobId, classificationStatus]);

  const progress = useMemo(() => {
    if (!assignment?.template) return { pct: 0, done: 0, total: 0 };
    return computeFormProgress(assignment.template.schema, answers);
  }, [assignment, answers]);

  /** Persist the draft. `silent` suppresses the toast for autosaves. */
  const saveDraft = useCallback(
    async (silent = false) => {
      if (!assignmentId || assignment?.status === "submitted") return false;
      const payload = JSON.stringify(answers);
      if (payload === savedAnswersRef.current) return true;
      setSaving(true);
      try {
        await api.patch(`/forms/assignments/${assignmentId}`, { answers });
        savedAnswersRef.current = payload;
        setDirty(false);
        setJustSaved(true);
        if (!silent) toast.success("Draft saved");
        window.setTimeout(() => setJustSaved(false), 2000);
        return true;
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Save failed");
        return false;
      } finally {
        setSaving(false);
      }
    },
    [assignmentId, assignment?.status, answers, toast],
  );

  // Autosave: a 38-question form used to lose everything typed since the last
  // manual save on a refresh. Fires once the user stops typing; the payload
  // comparison in saveDraft means an unchanged form never re-POSTs.
  useEffect(() => {
    if (!assignment || assignment.status === "submitted") return;
    if (JSON.stringify(answers) === savedAnswersRef.current) {
      setDirty(false);
      return;
    }
    setDirty(true);
    const timer = window.setTimeout(() => { void saveDraft(true); }, AUTOSAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [answers, assignment, saveDraft]);

  // Belt and braces for the window between an edit and its autosave.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const submit = async () => {
    if (!assignmentId || !assignment?.template) return;
    setSubmitting(true);
    try {
      // Save first. The server validates inside the same transaction it would
      // write the submission in, so a rejected submit rolls back any draft it
      // might otherwise have persisted — leaving the answers only in this tab.
      await saveDraft(true);
      await api.post(`/forms/assignments/${assignmentId}/submit`, { answers });
      setInvalidFieldIds([]);
      toast.success("Submitted — classification started");
      navigate("/my-forms");
    } catch (e) {
      // Flag the gaps in place; the toast alone can't be acted on in a
      // 7-section wizard.
      const gaps = findMissingRequired(assignment.template.schema, answers);
      setInvalidFieldIds(gaps.map((g) => g.field.id));
      toast.error(
        gaps.length
          ? `${gaps.length} required answer${gaps.length === 1 ? "" : "s"} still missing`
          : e instanceof Error ? e.message : "Submit failed",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const download = async (blank: boolean) => {
    if (!assignmentId) return;
    setShowDownloadMenu(false);
    setDownloading(true);
    try {
      await downloadBlob(
        `/forms/assignments/${assignmentId}/export.xlsx${blank ? "?blank=true" : ""}`,
        "vendor-due-diligence.xlsx",
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  };

  const pickFile = async () => {
    // The server merges the file onto whatever draft it holds, so any edit that
    // autosave hasn't flushed yet must be pushed first or the import would
    // silently drop it.
    await saveDraft(true);
    fileInputRef.current?.click();
  };

  const importFile = async (file: File) => {
    if (!assignmentId) return;
    setImporting(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const result = await api.upload<FormImportResult>(
        `/forms/assignments/${assignmentId}/import-excel`,
        body,
      );
      applyAssignment(result.assignment);
      toast.success(
        `Imported ${result.imported_count} answer${result.imported_count === 1 ? "" : "s"}`,
      );
      if (result.unmatched.length) {
        toast.error(
          `${result.unmatched.length} row(s) didn't match this form: ${result.unmatched.slice(0, 3).join("; ")}`,
        );
      }
      result.warnings.forEach((w) => toast.error(w));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  if (!assignment?.template) {
    return <div className="empty-state">Loading form…</div>;
  }

  const readOnly = assignment.status === "submitted";

  return (
    <div className="form-fill">
      <header className="form-fill__top">
        <div className="form-fill__top-left">
          <button type="button" className="form-fill__back" onClick={() => navigate("/my-forms")}>
            ← My Forms
          </button>
          <div>
            <h1 className="form-fill__title">{assignment.title}</h1>
            <p className="form-fill__sub">
              {assignment.vendor_legal_name ? (
                <><strong>{assignment.vendor_legal_name}</strong></>
              ) : "Vendor due diligence"}
              {assignment.due_at && (
                <> · Due {new Date(assignment.due_at).toLocaleDateString()}</>
              )}
              {" · "}
              {progress.done}/{progress.total} required
            </p>
          </div>
        </div>
        <div className="form-fill__top-right">
          <div className="form-fill__pct" aria-label={`${progress.pct}% complete`}>
            <span className="form-fill__pct-value">{progress.pct}%</span>
          </div>
          <StatusBadge status={assignment.status} />

          <div className="form-fill__menu">
            <Button
              size="sm"
              variant="secondary"
              loading={downloading}
              aria-haspopup="menu"
              aria-expanded={showDownloadMenu}
              onClick={() => (readOnly ? download(false) : setShowDownloadMenu((s) => !s))}
            >
              Download
            </Button>
            {showDownloadMenu && !readOnly && (
              <div className="form-fill__menu-list" role="menu">
                <button type="button" role="menuitem" onClick={() => download(true)}>
                  Blank form
                  <span>Send this to the vendor</span>
                </button>
                <button type="button" role="menuitem" onClick={() => download(false)}>
                  With current answers
                  <span>Includes everything saved so far</span>
                </button>
              </div>
            )}
          </div>

          {!readOnly && (
            <>
              <Button size="sm" variant="secondary" loading={importing} onClick={pickFile}>
                Import filled form
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx"
                style={{ display: "none" }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  // Reset first, so re-picking the same file fires onChange again.
                  e.target.value = "";
                  if (file) importFile(file);
                }}
              />
              <span className="form-fill__save-state" aria-live="polite">
                {saving ? "Saving…" : dirty ? "Unsaved changes" : justSaved ? "Saved ✓" : "All changes saved"}
              </span>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => saveDraft()}
                disabled={saving || !dirty}
              >
                Save now
              </Button>
            </>
          )}

          {assignment.classification_job_id && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => navigate(`/m1?job=${assignment.classification_job_id}`)}
            >
              Classification
              {assignment.classification_status && (
                <> · <StatusBadge status={assignment.classification_status} /></>
              )}
            </Button>
          )}
        </div>
      </header>

      <div className="form-fill__progress">
        <div
          className="form-fill__progress-bar"
          style={{ width: `${progress.pct}%` }}
          role="progressbar"
          aria-valuenow={progress.pct}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>

      <DynamicFormRenderer
        schema={assignment.template.schema}
        answers={answers}
        onChange={setAnswers}
        onSubmit={submit}
        readOnly={readOnly}
        submitting={submitting}
        invalidFieldIds={invalidFieldIds}
        branded
      />
    </div>
  );
}
