import { FormEvent, useEffect, useState } from "react";
import { api, User } from "../api/client";
import { useAuth } from "../app/AuthContext";
import { useToast } from "../app/ToastContext";
import {
  PageHeader,
  Card,
  DataTable,
  Button,
  Badge,
  FormField,
  Input,
  Select,
  EmptyState,
  ConfirmDialog,
} from "../components/ui";

const ROLE_OPTIONS = [
  { value: "admin", label: "Admin" },
  { value: "user", label: "User" },
];

const ROLE_LABEL: Record<string, string> = {
  admin: "Admin",
  user: "User",
};

type PanelMode = null | "create" | { edit: User };

interface FormState {
  email: string;
  display_name: string;
  password: string;
  role: string;
  is_active: boolean;
}

const EMPTY_FORM: FormState = {
  email: "",
  display_name: "",
  password: "",
  role: "user",
  is_active: true,
};

export function UserManagementPage() {
  const { user: currentUser } = useAuth();
  const toast = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [panel, setPanel] = useState<PanelMode>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  // The user awaiting deactivation confirmation. null = dialog closed.
  const [pendingDeactivate, setPendingDeactivate] = useState<User | null>(null);
  const [deactivating, setDeactivating] = useState(false);

  const load = () => api.get<User[]>("/admin/users").then(setUsers).catch(() => {});

  useEffect(() => {
    load();
  }, []);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setPanel("create");
  };

  const openEdit = (u: User) => {
    setForm({
      email: u.email,
      display_name: u.display_name,
      password: "",
      role: u.roles[0] ?? "user",
      is_active: u.is_active ?? true,
    });
    setPanel({ edit: u });
  };

  const closePanel = () => {
    setPanel(null);
    setForm(EMPTY_FORM);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (panel === "create") {
        await api.post("/admin/users", {
          email: form.email.trim(),
          display_name: form.display_name.trim(),
          password: form.password,
          role: form.role,
        });
        toast.success("User created.");
      } else if (panel && "edit" in panel) {
        await api.patch(`/admin/users/${panel.edit.id}`, {
          display_name: form.display_name.trim(),
          role: form.role,
          is_active: form.is_active,
        });
        if (form.password.trim()) {
          await api.post(`/admin/users/${panel.edit.id}/reset-password`, {
            new_password: form.password,
          });
        }
        toast.success("User updated.");
      }
      closePanel();
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const confirmDeactivate = async () => {
    if (!pendingDeactivate) return;
    setDeactivating(true);
    try {
      await api.delete(`/admin/users/${pendingDeactivate.id}`);
      toast.success("User deactivated.");
      setPendingDeactivate(null);
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to deactivate");
    } finally {
      setDeactivating(false);
    }
  };

  const isEditing = panel && panel !== "create" && "edit" in panel;

  return (
    <div>
      <PageHeader
        breadcrumb="Governance"
        title="User Management"
        subtitle="Invite members, assign roles, and manage access. All changes are audit-logged."
        action={
          <Button variant="primary" onClick={openCreate}>
            + Invite user
          </Button>
        }
      />

      {panel && (
        <Card className="user-panel">
          <h2 className="card__title">{isEditing ? "Edit user" : "Invite user"}</h2>
          <form className="form-grid form-grid--2" onSubmit={save}>
            <FormField label="Email">
              <Input
                type="email"
                value={form.email}
                disabled={!!isEditing}
                placeholder="you@genaiforge.local"
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
              />
            </FormField>
            <FormField label="Name">
              <Input
                value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                required
              />
            </FormField>
            <FormField label="Role">
              <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                {ROLE_OPTIONS.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </Select>
            </FormField>
            <FormField label={isEditing ? "New password (leave blank to keep)" : "Initial password"}>
              <Input
                type="password"
                value={form.password}
                autoComplete="new-password"
                placeholder="••••••••"
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required={!isEditing}
              />
            </FormField>
            {isEditing && (
              <FormField label="Status">
                <Select
                  value={form.is_active ? "active" : "inactive"}
                  onChange={(e) => setForm({ ...form, is_active: e.target.value === "active" })}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </Select>
              </FormField>
            )}
            <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "end" }}>
              <Button variant="primary" type="submit" loading={saving}>
                {isEditing ? "Save changes" : "Create user"}
              </Button>
              <Button variant="ghost" type="button" onClick={closePanel}>
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      <Card>
        {users.length === 0 ? (
          <EmptyState title="No users" description="Invite your first user to get started." />
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>Email</th>
                <th>Name</th>
                <th>Role</th>
                <th>Status</th>
                <th>Last login</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>{u.display_name}</td>
                  <td>{ROLE_LABEL[u.roles[0]] ?? u.roles[0] ?? "—"}</td>
                  <td>
                    <Badge variant={u.is_active ? "success" : "neutral"}>
                      {u.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {u.last_login ? new Date(u.last_login).toLocaleString() : "—"}
                  </td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <Button size="sm" variant="secondary" onClick={() => openEdit(u)}>
                      Edit
                    </Button>{" "}
                    {u.is_active && u.id !== currentUser?.id && (
                      <Button size="sm" variant="danger" onClick={() => setPendingDeactivate(u)}>
                        Deactivate
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </Card>
      <ConfirmDialog
        open={pendingDeactivate !== null}
        title="Deactivate user?"
        message={
          <>
            <strong>{pendingDeactivate?.email}</strong> will no longer be able to sign
            in. Their history and audit records are kept.
          </>
        }
        confirmLabel="Deactivate"
        loading={deactivating}
        onConfirm={confirmDeactivate}
        onCancel={() => setPendingDeactivate(null)}
      />
    </div>
  );
}
