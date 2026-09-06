import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { useAuth } from "@/contexts/AuthContext";
import { api, ApiError } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import type {
  TemplateLibraryCategories,
  TemplateLibraryItem,
  TemplateLibraryPreview,
} from "@/types";

function formatBytes(n: number | null | undefined): string {
  if (n == null || n <= 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function kindLabel(kind: string): string {
  if (kind === "executed") return "Executed";
  if (kind === "template") return "Template";
  return kind;
}

export function ContractTemplatesPage() {
  const { user } = useAuth();
  const canEdit = hasPermission(user, "playbook_management");
  const [categories, setCategories] = useState<TemplateLibraryCategories | null>(null);
  const [rows, setRows] = useState<TemplateLibraryItem[]>([]);
  const [filterKind, setFilterKind] = useState("");
  const [filterType, setFilterType] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({
    doc_kind: "template",
    contract_type: "MSA",
    name: "",
    description: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<TemplateLibraryPreview | null>(null);
  const [previewLoadingKey, setPreviewLoadingKey] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  function reload() {
    setLoading(true);
    setError(null);
    api
      .listTemplateLibrary({
        doc_kind: filterKind || undefined,
        contract_type: filterType || undefined,
      })
      .then(setRows)
      .catch((e: unknown) => {
        setRows([]);
        setError(e instanceof ApiError ? e.detail : "Failed to load template library");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    api.templateLibraryCategories().then(setCategories).catch(() => setCategories(null));
  }, []);

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKind, filterType]);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Choose a .docx, .pdf, or .txt file");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("doc_kind", form.doc_kind);
      body.append("contract_type", form.contract_type);
      if (form.name.trim()) body.append("name", form.name.trim());
      if (form.description.trim()) body.append("description", form.description.trim());
      await api.uploadTemplateLibrary(body);
      setShowForm(false);
      setFile(null);
      setForm({ doc_kind: "template", contract_type: "MSA", name: "", description: "" });
      reload();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.detail : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function openPreview(item: TemplateLibraryItem) {
    setPreviewLoadingKey(item.storage_key);
    setPreviewError(null);
    try {
      const data = await api.previewTemplateLibrary(item.storage_key);
      setPreview(data);
    } catch (err: unknown) {
      setPreviewError(err instanceof ApiError ? err.detail : "Could not open document");
      setPreview(null);
    } finally {
      setPreviewLoadingKey(null);
    }
  }

  const bucket = categories?.bucket || "legalos";
  const templatesPrefix = categories?.templates_prefix || categories?.prefix || "legal_templates";
  const contractsPrefix = categories?.contracts_prefix || "contracts";
  const subtitle =
    filterKind === "executed"
      ? `Executed documents from gs://${bucket}/${contractsPrefix}/`
      : filterKind === "template"
        ? `Templates from gs://${bucket}/${templatesPrefix}/`
        : `Templates: gs://${bucket}/${templatesPrefix}/ · Executed: gs://${bucket}/${contractsPrefix}/`;

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        title="Template Library"
        subtitle={subtitle}
        actions={
          canEdit ? (
            <Button onClick={() => setShowForm((s) => !s)}>
              {showForm ? "Cancel" : "+ Upload document"}
            </Button>
          ) : undefined
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl">
        <Select
          label="Kind"
          value={filterKind}
          onChange={(e) => setFilterKind(e.target.value)}
        >
          <option value="">All kinds</option>
          {(categories?.doc_kinds ?? [
            { id: "template", label: "Template" },
            { id: "executed", label: "Executed legal document" },
          ]).map((k) => (
            <option key={k.id} value={k.id}>
              {k.label}
            </option>
          ))}
        </Select>
        <Select
          label="Contract type"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
        >
          <option value="">All types</option>
          {(categories?.contract_types ?? ["MSA", "NDA", "SLA", "Employment", "Policy", "Other"]).map(
            (t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ),
          )}
        </Select>
      </div>

      {showForm && canEdit && (
        <Card title="Upload to library">
          <form className="space-y-3" onSubmit={upload}>
            <p className="text-sm text-label-secondary">
              {form.doc_kind === "executed"
                ? `Executed files go to gs://${bucket}/${contractsPrefix}/{type}/.`
                : `Templates go to gs://${bucket}/${templatesPrefix}/{type}/.`}{" "}
              Accepted: {(categories?.allowed_extensions ?? [".docx", ".pdf", ".txt"]).join(", ")}.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Select
                label="Document kind"
                value={form.doc_kind}
                onChange={(e) => setForm((f) => ({ ...f, doc_kind: e.target.value }))}
              >
                <option value="template">Template</option>
                <option value="executed">Executed legal document</option>
              </Select>
              <Select
                label="Contract type"
                value={form.contract_type}
                onChange={(e) => setForm((f) => ({ ...f, contract_type: e.target.value }))}
              >
                {(categories?.contract_types ?? ["MSA", "NDA", "SLA", "Employment", "Policy", "Other"]).map(
                  (t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ),
                )}
              </Select>
            </div>
            <Input
              label="Display name (optional)"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Defaults to file name"
            />
            <Textarea
              label="Description (optional)"
              rows={2}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
            <label className="block w-full">
              <span className="block text-subheadline font-medium text-label mb-1.5">File</span>
              <input
                type="file"
                accept=".docx,.pdf,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                className="block w-full text-sm text-label file:mr-3 file:rounded-md file:border-0 file:bg-bg-secondary file:px-3 file:py-2 file:text-sm"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                required
              />
            </label>
            <div className="flex justify-end">
              <Button type="submit" disabled={busy || !file}>
                {busy ? "Uploading…" : "Upload to bucket"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {(error || previewError) && (
        <p className="text-sm text-error" role="alert">
          {error || previewError}
        </p>
      )}

      <Card>
        {loading ? (
          <p className="text-sm text-label-secondary">Loading library…</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-label-secondary">
            No documents in the library yet. Upload a template or executed agreement to get started.
          </p>
        ) : (
          <ul className="divide-y divide-separator/30">
            {rows.map((r) => (
              <li key={r.storage_key} className="py-3 flex justify-between items-start gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-label">{r.name}</span>
                    <Badge>{kindLabel(r.doc_kind)}</Badge>
                    <Badge className="bg-bg-secondary text-label-secondary">{r.contract_type}</Badge>
                  </div>
                  {r.description && (
                    <p className="text-sm text-label-secondary mt-1">{r.description}</p>
                  )}
                  <p className="text-xs text-label-tertiary mt-1 truncate">
                    {r.filename}
                    {r.size_bytes != null ? ` · ${formatBytes(r.size_bytes)}` : ""}
                    {r.updated_at
                      ? ` · ${new Date(r.updated_at).toLocaleString()}`
                      : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <button
                    type="button"
                    className="text-sm text-accent hover:underline disabled:opacity-50"
                    disabled={previewLoadingKey === r.storage_key}
                    onClick={() => openPreview(r)}
                  >
                    {previewLoadingKey === r.storage_key ? "Opening…" : "View"}
                  </button>
                  {r.db_id && r.doc_kind === "template" && (
                    <Link
                      to={`/msa-automation/start?template=${r.db_id}`}
                      className="text-sm text-accent hover:underline"
                    >
                      Use in negotiation →
                    </Link>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {preview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="template-preview-title"
          onClick={() => setPreview(null)}
        >
          <div
            className="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-lg bg-bg shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 border-b border-separator/40 px-5 py-4">
              <div className="min-w-0">
                <h2 id="template-preview-title" className="truncate text-lg font-semibold text-label">
                  {preview.name}
                </h2>
                <p className="mt-1 text-xs text-label-tertiary">
                  {preview.filename}
                  {preview.size_bytes != null ? ` · ${formatBytes(preview.size_bytes)}` : ""}
                  {` · ${preview.char_count.toLocaleString()} characters`}
                  {preview.truncated ? " · preview truncated" : ""}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Badge>{kindLabel(preview.doc_kind)}</Badge>
                  <Badge className="bg-bg-secondary text-label-secondary">
                    {preview.contract_type}
                  </Badge>
                </div>
              </div>
              <Button type="button" variant="secondary" onClick={() => setPreview(null)}>
                Close
              </Button>
            </div>
            <pre className="flex-1 overflow-auto whitespace-pre-wrap break-words px-5 py-4 text-sm leading-relaxed text-label">
              {preview.text.trim() || "(No extractable text in this file.)"}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
