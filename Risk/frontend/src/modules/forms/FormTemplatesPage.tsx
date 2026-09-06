import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ExcelImportPreview, ExcelSheetPreview, FormTemplate } from "../../api/client";
import { useToast } from "../../app/ToastContext";
import { PageHeader, Card, DataTable, Button, Badge, EmptyState, ConfirmDialog } from "../../components/ui";

export function FormTemplatesPage() {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const pendingFileRef = useRef<File | null>(null);
  const [templates, setTemplates] = useState<FormTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [sheetModal, setSheetModal] = useState<{ sheets: ExcelSheetPreview[] } | null>(null);
  const [importing, setImporting] = useState(false);
  // The template awaiting confirmation. null = dialog closed.
  const [pendingDelete, setPendingDelete] = useState<FormTemplate | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = () => {
    setLoading(true);
    api.get<FormTemplate[]>("/forms/templates")
      .then(setTemplates)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const importWithSheet = async (file: File, sheetIndex: number) => {
    setImporting(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.upload<FormTemplate>(`/forms/templates/import-excel?sheet_index=${sheetIndex}`, fd);
      toast.success("Template imported from Excel");
      setSheetModal(null);
      pendingFileRef.current = null;
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  const onFileSelected = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    try {
      const preview = await api.upload<ExcelImportPreview>("/forms/templates/import-excel/preview", fd);
      pendingFileRef.current = file;
      if (preview.sheets.length <= 1) {
        await importWithSheet(file, preview.sheets[0]?.index ?? 0);
        return;
      }
      setSheetModal({ sheets: preview.sheets });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not read workbook");
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.delete(`/forms/templates/${pendingDelete.id}`);
      toast.success("Template deleted");
      setPendingDelete(null);
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  if (loading && templates.length === 0) {
    return <div className="empty-state">Loading templates…</div>;
  }

  return (
    <div>
      <PageHeader
        breadcrumb="Governance"
        title="Form Templates"
        subtitle="Vendor due diligence form definitions. Import from Excel or edit in the builder."
        action={<Button onClick={() => fileRef.current?.click()}>Import Excel</Button>}
      />
      <input
        ref={fileRef}
        type="file"
        accept=".xlsx"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFileSelected(f);
          e.target.value = "";
        }}
      />

      {sheetModal && pendingFileRef.current && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <Card className="modal-card">
            <h2 className="card__title">Select worksheet</h2>
            <p className="form-field__hint" style={{ marginBottom: 16 }}>
              This workbook has {sheetModal.sheets.length} sheets. Choose which one to import as the form template.
            </p>
            <div className="sheet-picker-list">
              {sheetModal.sheets.map((s) => (
                <button
                  key={s.index}
                  type="button"
                  className="sheet-picker-item"
                  disabled={importing}
                  onClick={() => importWithSheet(pendingFileRef.current!, s.index)}
                >
                  <span className="sheet-picker-item__name">{s.name}</span>
                  <span className="sheet-picker-item__meta">Sheet {s.index + 1} · ~{s.row_count} rows</span>
                </button>
              ))}
            </div>
            <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
              <Button
                type="button"
                variant="secondary"
                disabled={importing}
                onClick={() => {
                  setSheetModal(null);
                  pendingFileRef.current = null;
                }}
              >
                Cancel
              </Button>
            </div>
          </Card>
        </div>
      )}

      {templates.length === 0 ? (
        <EmptyState
          title="No templates yet"
          description="Import the Vendor Due Diligence Excel workbook to create the first template."
        />
      ) : (
        <Card>
          <DataTable>
            <thead>
              <tr>
                <th>Name</th>
                <th>Version</th>
                <th>Status</th>
                <th>Sections</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((t) => (
                <tr key={t.id}>
                  <td><strong>{t.name}</strong></td>
                  <td>v{t.version}</td>
                  <td>{t.is_active ? <Badge variant="success">Active</Badge> : <Badge>Inactive</Badge>}</td>
                  <td>{t.schema.sections?.length ?? 0}</td>
                  <td style={{ display: "flex", gap: 8 }}>
                    <Link to={`/admin/forms/${t.id}/edit`}>
                      <Button size="sm">Edit</Button>
                    </Link>
                    <Button size="sm" variant="danger" onClick={() => setPendingDelete(t)}>Delete</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </Card>
      )}
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete template?"
        message={
          <>
            <strong>{pendingDelete?.name}</strong> and all of its assignments will be
            permanently deleted. This cannot be undone.
          </>
        }
        confirmLabel="Delete template"
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
