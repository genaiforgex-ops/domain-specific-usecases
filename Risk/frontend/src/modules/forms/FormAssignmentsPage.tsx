import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  FormAssignment,
  FormAssignmentBulkCreate,
  FormTemplate,
  User,
  Vendor,
} from "../../api/client";
import { downloadBlob } from "../../api/download";
import { useToast } from "../../app/ToastContext";
import {
  PageHeader,
  Card,
  DataTable,
  Button,
  StatusBadge,
  FormField,
  Input,
  Select,
  EmptyState,
  ConfirmDialog,
} from "../../components/ui";

interface AssignRow {
  assignee_id: string;
  vendor_id: string;
  vendor_name: string;
}

function emptyRow(): AssignRow {
  return { assignee_id: "", vendor_id: "", vendor_name: "" };
}

export function FormAssignmentsPage() {
  const toast = useToast();
  const [assignments, setAssignments] = useState<FormAssignment[]>([]);
  const [templates, setTemplates] = useState<FormTemplate[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ template_id: "", title: "", due_at: "" });
  const [rows, setRows] = useState<AssignRow[]>([emptyRow()]);
  const [saving, setSaving] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  // The assignment awaiting confirmation. null = dialog closed.
  const [pendingDelete, setPendingDelete] = useState<FormAssignment | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = () => {
    Promise.all([
      api.get<FormAssignment[]>("/forms/assignments"),
      api.get<FormTemplate[]>("/forms/templates"),
      api.get<User[]>("/admin/users"),
      api.get<Vendor[]>("/vendors"),
    ]).then(([a, t, u, v]) => {
      setAssignments(a);
      setTemplates(t);
      setUsers(u.filter((x) => x.is_active !== false));
      setVendors(v);
    });
  };

  useEffect(() => { load(); }, []);

  const updateRow = (idx: number, patch: Partial<AssignRow>) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  const resolveVendor = (row: AssignRow): { vendor_id?: string; vendor_name?: string } => {
    if (row.vendor_id) return { vendor_id: row.vendor_id };
    const name = row.vendor_name.trim();
    const match = vendors.find((v) => v.legal_name.toLowerCase() === name.toLowerCase());
    if (match) return { vendor_id: match.id };
    return { vendor_name: name };
  };

  const assign = async (e: FormEvent) => {
    e.preventDefault();
    const validRows = rows.filter((r) => r.assignee_id && (r.vendor_id || r.vendor_name.trim()));
    if (validRows.length === 0) {
      toast.error("Add at least one assignee with a vendor");
      return;
    }
    setSaving(true);
    try {
      const body: FormAssignmentBulkCreate = {
        template_id: form.template_id,
        title: form.title,
        due_at: form.due_at ? new Date(form.due_at).toISOString() : null,
        assignments: validRows.map((r) => ({
          assignee_id: r.assignee_id,
          ...resolveVendor(r),
        })),
      };
      await api.post("/forms/assignments/bulk", body);
      toast.success(`Assigned to ${validRows.length} user(s)`);
      setShowForm(false);
      setForm({ template_id: "", title: "", due_at: "" });
      setRows([emptyRow()]);
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Assign failed");
    } finally {
      setSaving(false);
    }
  };

  const remind = async (id: string) => {
    try {
      await api.post(`/forms/assignments/${id}/remind`);
      toast.success("Reminder sent");
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Reminder failed");
    }
  };

  const download = async (a: FormAssignment) => {
    setDownloadingId(a.id);
    try {
      await downloadBlob(`/forms/assignments/${a.id}/export.xlsx`, `${a.title}.xlsx`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloadingId(null);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.delete(`/forms/assignments/${pendingDelete.id}`);
      toast.success("Assignment deleted");
      setPendingDelete(null);
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div>
      <PageHeader
        breadcrumb="Forms"
        title="Form Assignments"
        subtitle="Share vendor due diligence forms with users and track completion."
        action={<Button onClick={() => setShowForm(true)}>Assign form</Button>}
      />

      {showForm && (
        <Card className="mb-24">
          <h2 className="card__title">New assignment</h2>
          <form onSubmit={assign} className="assign-form">
            <div className="form-grid form-grid--2">
              <FormField label="Template" required>
                <Select
                  value={form.template_id}
                  onChange={(e) => setForm({ ...form, template_id: e.target.value })}
                  required
                >
                  <option value="">Select template…</option>
                  {templates.filter((t) => t.is_active).map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </Select>
              </FormField>
              <FormField label="Due date">
                <Input type="date" value={form.due_at} onChange={(e) => setForm({ ...form, due_at: e.target.value })} />
              </FormField>
            </div>
            <FormField label="Title" required hint="Each row gets: Title — Vendor name">
              <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
            </FormField>

            <div className="assign-rows">
              <div className="assign-rows__header">
                <span>Assignee</span>
                <span>Vendor</span>
                <span />
              </div>
              {rows.map((row, idx) => (
                <div key={idx} className="assign-rows__row">
                  <Select
                    value={row.assignee_id}
                    onChange={(e) => updateRow(idx, { assignee_id: e.target.value })}
                    required={idx === 0}
                  >
                    <option value="">Select user…</option>
                    {users.map((u) => (
                      <option key={u.id} value={u.id}>{u.display_name} ({u.email})</option>
                    ))}
                  </Select>
                  <div className="assign-rows__vendor">
                    <Select
                      value={row.vendor_id ? row.vendor_id : "__new__"}
                      onChange={(e) => {
                        const val = e.target.value;
                        if (val === "__new__") {
                          updateRow(idx, { vendor_id: "", vendor_name: row.vendor_name });
                        } else {
                          const v = vendors.find((x) => x.id === val);
                          updateRow(idx, { vendor_id: val, vendor_name: v?.legal_name ?? "" });
                        }
                      }}
                    >
                      <option value="__new__">New vendor…</option>
                      {vendors.map((v) => (
                        <option key={v.id} value={v.id}>{v.legal_name}</option>
                      ))}
                    </Select>
                    {!row.vendor_id && (
                      <Input
                        placeholder="Vendor name"
                        value={row.vendor_name}
                        onChange={(e) => updateRow(idx, { vendor_name: e.target.value })}
                        list={`vendor-suggestions-${idx}`}
                      />
                    )}
                    {!row.vendor_id && (
                      <datalist id={`vendor-suggestions-${idx}`}>
                        {vendors.map((v) => (
                          <option key={v.id} value={v.legal_name} />
                        ))}
                      </datalist>
                    )}
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="danger"
                    disabled={rows.length === 1}
                    onClick={() => setRows((prev) => prev.filter((_, i) => i !== idx))}
                  >
                    Remove
                  </Button>
                </div>
              ))}
            </div>
            <div>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => setRows((prev) => [...prev, emptyRow()])}
              >
                Add row
              </Button>
            </div>

            <div className="assign-form__actions">
              <Button type="submit" disabled={saving}>{saving ? "Assigning…" : "Assign all"}</Button>
              <Button type="button" variant="secondary" onClick={() => setShowForm(false)}>Cancel</Button>
            </div>
          </form>
        </Card>
      )}

      {assignments.length === 0 ? (
        <EmptyState title="No assignments yet" description="Assign a form to a user to get started." />
      ) : (
        <Card>
          <DataTable>
            <thead>
              <tr>
                <th>Title</th>
                <th>Assignee</th>
                <th>Vendor</th>
                <th>Status</th>
                <th>Due</th>
                <th>Classification</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {assignments.map((a) => (
                <tr key={a.id}>
                  <td><strong>{a.title}</strong></td>
                  <td>{a.assignee_display_name ?? "—"}</td>
                  <td>{a.vendor_legal_name ?? "—"}</td>
                  <td><StatusBadge status={a.status} /></td>
                  <td>{a.due_at ? new Date(a.due_at).toLocaleDateString() : "—"}</td>
                  <td>
                    {a.classification_job_id ? (
                      <>
                        {a.classification_status && <StatusBadge status={a.classification_status} />}{" "}
                        <Link to={`/m1?job=${a.classification_job_id}`}>View job</Link>
                      </>
                    ) : "—"}
                  </td>
                  <td style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {a.status !== "submitted" && (
                      <Button size="sm" variant="secondary" onClick={() => remind(a.id)}>Remind</Button>
                    )}
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={downloadingId === a.id}
                      onClick={() => download(a)}
                    >
                      Download
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => setPendingDelete(a)}>Delete</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </Card>
      )}
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete assignment?"
        message={
          <>
            <strong>{pendingDelete?.title}</strong> will be permanently deleted, along
            with any answers already saved against it.
          </>
        }
        confirmLabel="Delete assignment"
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
