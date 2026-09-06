import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { roleLabel } from "@/lib/auth";
import { formatDate } from "@/lib/utils";
import type { Role, User } from "@/types";

const ROLES: Role[] = ["super_admin", "legal_admin", "legal_user", "business_user", "read_only"];

function statusOf(u: User): { label: string; className: string } {
  if (u.is_active) return { label: "Active", className: "bg-emerald-100 text-emerald-800 border-emerald-200" };
  if (!u.last_login_at) return { label: "Invited · pending", className: "bg-amber-100 text-amber-800 border-amber-200" };
  return { label: "Disabled", className: "bg-bg-secondary text-label-secondary border-separator/40" };
}

export function UserManagementPage() {
  const { user: actor } = useAuth();
  const isSuperAdmin = actor?.role === "super_admin";
  const [users, setUsers] = useState<User[]>([]);
  const [showInvite, setShowInvite] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [banner, setBanner] = useState<{ kind: "ok" | "warn" | "err"; text: string } | null>(null);

  const iamManaged = users.some((u) => u.iam_managed);

  const load = useCallback(async () => {
    setUsers(await api.listUsers());
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function syncFromIam() {
    setSyncing(true);
    try {
      const result = await api.syncUsersFromIam();
      await load();
      setBanner({
        kind: "ok",
        text: `Synced from Central IAM — ${result.created} added, ${result.updated} updated, ${result.deactivated} deactivated.`,
      });
    } catch (err) {
      setBanner({ kind: "err", text: (err as Error).message });
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        title="User Management"
        subtitle={
          iamManaged
            ? "Users and roles are managed centrally via IAM. This page reflects the latest sync from the Central Platform."
            : "Invite members, assign roles, and manage access. All changes are audit-logged."
        }
        actions={
          <>
            {iamManaged && isSuperAdmin && (
              <Button variant="secondary" onClick={syncFromIam} disabled={syncing} className="mr-2">
                {syncing ? "Syncing…" : "Sync from IAM"}
              </Button>
            )}
            {!iamManaged && (
              <Button onClick={() => setShowInvite((s) => !s)}>
                {showInvite ? "Cancel" : "+ Invite user"}
              </Button>
            )}
          </>
        }
      />

      {banner && (
        <div
          role="status"
          className={`rounded-lg border px-4 py-3 text-sm ${
            banner.kind === "ok"
              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-700"
              : banner.kind === "warn"
                ? "bg-amber-500/10 border-amber-500/30 text-amber-800"
                : "bg-error/10 border-error/30 text-error"
          }`}
        >
          {banner.text}
        </div>
      )}

      {showInvite && !iamManaged && (
        <InviteForm
          canAssignSuperAdmin={isSuperAdmin}
          onResult={(kind, text) => setBanner({ kind, text })}
          onDone={() => {
            load();
            setShowInvite(false);
          }}
        />
      )}

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-label-secondary border-b border-separator/30">
              <tr>
                <th className="py-2">Email</th>
                <th className="py-2">Name</th>
                <th className="py-2">Role</th>
                <th className="py-2">Status</th>
                <th className="py-2">Source</th>
                <th className="py-2">Last login</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  isSelf={u.id === actor?.id}
                  canAssignSuperAdmin={isSuperAdmin}
                  onChanged={load}
                  onResult={(kind, text) => setBanner({ kind, text })}
                />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function UserRow({
  user,
  isSelf,
  canAssignSuperAdmin,
  onChanged,
  onResult,
}: {
  user: User;
  isSelf: boolean;
  canAssignSuperAdmin: boolean;
  onChanged: () => void;
  onResult: (kind: "ok" | "warn" | "err", text: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [role, setRole] = useState(user.role);
  const [active, setActive] = useState(user.is_active);
  const [busy, setBusy] = useState(false);

  const status = statusOf(user);
  const isInvited = !user.is_active && !user.last_login_at;
  const isIamManaged = Boolean(user.iam_managed);
  const roleOptions = ROLES.filter((r) => r !== "super_admin" || canAssignSuperAdmin || user.role === "super_admin");

  async function save() {
    setBusy(true);
    try {
      await api.updateUser(user.id, { role, is_active: active });
      setEditing(false);
      onChanged();
      onResult("ok", `Updated ${user.email}.`);
    } catch (err) {
      onResult("err", (err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setBusy(true);
    try {
      const res = await api.resendInvite(user.id);
      onResult(res.email_sent ? "ok" : "warn", res.detail);
    } catch (err) {
      onResult("err", (err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (
      !window.confirm(
        `Permanently delete ${user.email}? This removes the account and its data and cannot be undone.`,
      )
    )
      return;
    setBusy(true);
    try {
      await api.deleteUser(user.id);
      onResult("ok", `Deleted ${user.email}.`);
      onChanged();
    } catch (err) {
      onResult("err", (err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr className="border-b border-separator/20">
      <td className="py-2">{user.email}</td>
      <td className="py-2">{user.full_name}</td>
      <td className="py-2">
        {editing && !isIamManaged ? (
          <select
            className="border border-separator/60 rounded px-2 py-1 text-sm bg-bg text-label"
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
          >
            {roleOptions.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </select>
        ) : (
          roleLabel(user.role)
        )}
      </td>
      <td className="py-2">
        {editing && !isIamManaged ? (
          <label className="inline-flex items-center gap-1 text-sm">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
            Active
          </label>
        ) : (
          <Badge className={status.className}>{status.label}</Badge>
        )}
      </td>
      <td className="py-2">
        {isIamManaged ? (
          <Badge className="bg-blue-100 text-blue-800 border-blue-200">Central IAM</Badge>
        ) : (
          <span className="text-label-secondary text-xs">Local</span>
        )}
      </td>
      <td className="py-2 text-label-secondary text-xs">
        {user.last_login_at ? formatDate(user.last_login_at) : "—"}
      </td>
      <td className="py-2 text-right whitespace-nowrap">
        {editing && !isIamManaged ? (
          <>
            <Button size="sm" onClick={save} disabled={busy} className="mr-2">
              Save
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setEditing(false);
                setRole(user.role);
                setActive(user.is_active);
              }}
            >
              Cancel
            </Button>
          </>
        ) : (
          <>
            {isInvited && !isIamManaged && (
              <Button size="sm" variant="ghost" onClick={resend} disabled={busy} className="mr-2">
                Resend invite
              </Button>
            )}
            {!isIamManaged && (
              <>
                <Button size="sm" variant="secondary" onClick={() => setEditing(true)} className="mr-2">
                  Edit
                </Button>
                {!isSelf && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={remove}
                    disabled={busy}
                    className="text-red-500 hover:bg-red-500/10"
                  >
                    Delete
                  </Button>
                )}
              </>
            )}
          </>
        )}
      </td>
    </tr>
  );
}

function InviteForm({
  canAssignSuperAdmin,
  onResult,
  onDone,
}: {
  canAssignSuperAdmin: boolean;
  onResult: (kind: "ok" | "warn" | "err", text: string) => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState({ email: "", full_name: "", role: "legal_user" as Role });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const roleOptions = ROLES.filter((r) => r !== "super_admin" || canAssignSuperAdmin);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.inviteUser(form);
      onResult(res.email_sent ? "ok" : "warn", res.detail);
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Invite a user">
      <p className="text-sm text-label-secondary mb-3">
        They'll receive an email with a secure link to set their password and activate their account.
      </p>
      <form className="space-y-3" onSubmit={submit}>
        <div className="grid sm:grid-cols-2 gap-3">
          <Input
            label="Email"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required
            placeholder="name@jiofinance.in"
          />
          <Input
            label="Full name"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            required
          />
        </div>
        <div className="grid sm:grid-cols-2 gap-3">
          <Select
            label="Role"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
          >
            {roleOptions.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </Select>
        </div>
        {error && <p className="text-sm text-error">{error}</p>}
        <div className="flex justify-end">
          <Button type="submit" disabled={busy}>
            {busy ? "Sending invite…" : "Send invite"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
