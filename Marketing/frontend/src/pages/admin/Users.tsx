import { useEffect, useMemo, useState } from 'react';
import { Page } from '../../components/layout/Page';
import { ListToolbar } from '../../components/layout/ListToolbar';
import { Avatar, Pill } from '../../components/ui/primitives';
import { Loader } from '../../components/feature/HomeKit';
import { DataTable, type Column, type TableGroup } from '../../components/ui/DataTable';
import { activeFill } from '../../components/ui/cells';
import { ROLES, ROLE_ORDER } from '../../lib/roles';
import { api, ApiError } from '../../lib/api';
import type { AdminUser, RoleId } from '../../lib/types';

const rolesOf = (u: AdminUser): RoleId[] =>
  ROLE_ORDER.filter((r) => (u.roles?.length ? u.roles : [u.role]).includes(r));

const dedupeByEmail = (users: AdminUser[]): AdminUser[] => {
  const byEmail = new Map<string, AdminUser>();
  for (const u of users) {
    const key = u.email.trim().toLowerCase();
    const cur = byEmail.get(key);
    if (!cur) {
      byEmail.set(key, u);
    } else if (
      (u.is_active && !cur.is_active) ||
      (u.is_active === cur.is_active && rolesOf(u).length > rolesOf(cur).length)
    ) {
      byEmail.set(key, u);
    }
  }
  return [...byEmail.values()];
};

export default function Users() {
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [denied, setDenied] = useState(false);
  const [q, setQ] = useState('');

  useEffect(() => {
    api
      .adminListUsers()
      .then(setUsers)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) setDenied(true);
        else setUsers([]);
      });
  }, []);

  const columns: Column<AdminUser>[] = useMemo(() => [
    {
      key: 'user', header: 'User',
      cell: (u) => (
        <div className="flex items-center gap-3 min-w-0">
          <Avatar name={u.full_name} ring={ROLES[rolesOf(u)[0]]?.accent} size={30} />
          <span className="text-subheadline font-semibold text-label truncate">{u.full_name}</span>
        </div>
      ),
    },
    { key: 'email', header: 'Email', width: '280px', cell: (u) => <span className="text-footnote text-label-secondary truncate">{u.email}</span>, hideBelow: 'sm' },
    {
      key: 'roles', header: 'Role', width: '240px',
      cell: (u) => {
        const roles = rolesOf(u);
        return roles.length ? (
          <div className="flex flex-wrap gap-1">
            {roles.map((r) => <Pill key={r} hue={ROLES[r]?.accent}>{r}</Pill>)}
          </div>
        ) : (
          <span className="text-footnote text-label-tertiary">No role</span>
        );
      },
    },
    {
      key: 'status', header: 'Status', width: '120px', align: 'center',
      cell: (u) => (u.is_active ? 'Active' : 'Disabled'),
      cellStyle: (u) => activeFill(u.is_active),
    },
  ], []);

  const directory = useMemo(() => dedupeByEmail(users ?? []), [users]);

  const groups: TableGroup<AdminUser>[] = useMemo(() => {
    const term = q.trim().toLowerCase();
    const rows = directory.filter((u) =>
      !term
      || u.full_name.toLowerCase().includes(term)
      || u.email.toLowerCase().includes(term)
      || rolesOf(u).some((r) => r.toLowerCase().includes(term)),
    );
    const activeCount = rows.filter((u) => u.is_active).length;
    return [{
      id: 'all',
      label: 'Accounts',
      hue: 'var(--color-accent)',
      rows,
      meta: activeCount !== rows.length ? `${activeCount} active` : undefined,
    }];
  }, [directory, q]);

  if (denied) {
    return (
      <Page>
        <ListToolbar title="Users" />
        <p className="text-footnote text-label-secondary">Sign in as the Admin account to view users.</p>
      </Page>
    );
  }
  if (!users) return <Page><ListToolbar title="Users" /><Loader /></Page>;

  const active = directory.filter((u) => u.is_active).length;

  return (
    <Page>
      <ListToolbar
        title="Users"
        subtitle={`Local accounts and roles — ${active} of ${directory.length} active.`}
        count={directory.length}
        search={q}
        onSearch={setQ}
        searchPlaceholder="Search name, email, role…"
      />

      <DataTable columns={columns} groups={groups} rowKey={(u) => u.id} />
    </Page>
  );
}
