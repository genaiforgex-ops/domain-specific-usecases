import { useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import { Page } from '../../components/layout/Page';
import { ListToolbar } from '../../components/layout/ListToolbar';
import { Avatar, Pill } from '../../components/ui/primitives';
import { Loader } from '../../components/feature/HomeKit';
import { DataTable, type Column, type TableGroup } from '../../components/ui/DataTable';
import { ROLES } from '../../lib/roles';
import { api, ApiError } from '../../lib/api';
import { useApp } from '../../state/AppContext';
import type { RoleDefault, RoleId } from '../../lib/types';

const SELECT_CLASS =
  'w-full h-9 px-3 rounded-md bg-bg-secondary border border-separator text-footnote text-label focus-ring transition-shadow duration-fast disabled:opacity-50';

export default function RoleDefaults() {
  const { people, toast } = useApp();
  const [defaults, setDefaults] = useState<RoleDefault[] | null>(null);
  const [denied, setDenied] = useState(false);
  const [savingRole, setSavingRole] = useState<RoleId | null>(null);

  useEffect(() => {
    api
      .adminRoleDefaults()
      .then(setDefaults)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) setDenied(true);
        else setDefaults([]);
      });
  }, []);

  const change = async (role: RoleId, userId: string) => {
    if (!userId) return;
    setSavingRole(role);
    try {
      const updated = await api.adminSetRoleDefault(role, userId);
      setDefaults((cur) => (cur ?? []).map((d) => (d.role === role ? updated : d)));
      toast(`${updated.role_label} default updated`, 'success');
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Could not update the default', 'error');
    } finally {
      setSavingRole(null);
    }
  };

  const columns: Column<RoleDefault>[] = [
    {
      key: 'role', header: 'Role', width: '220px',
      cell: (d) => (
        <div className="flex items-center gap-2">
          <span className="text-subheadline font-semibold text-label">{d.role_label}</span>
          <Pill hue={ROLES[d.role as RoleId]?.accent}>{d.role}</Pill>
        </div>
      ),
    },
    {
      key: 'current', header: 'Current default',
      cell: (d) =>
        d.full_name ? (
          <div className="flex items-center gap-2">
            <Avatar name={d.full_name} ring={ROLES[d.role as RoleId]?.accent} size={26} />
            <span className="text-footnote text-label-secondary truncate">{d.full_name}</span>
          </div>
        ) : (
          <span className="text-footnote text-label-tertiary">Not set</span>
        ),
    },
    {
      key: 'assign', header: 'Assign', width: '320px',
      cell: (d) => {
        const role = d.role as RoleId;
        // Everyone IAM grants this role — a multi-role user shows under each.
        const options = people.filter((p) => (p.roles ?? [p.role]).includes(role));
        return (
          <div className="flex items-center gap-2">
            <select
              className={SELECT_CLASS}
              value={d.user_id ?? ''}
              disabled={savingRole === d.role}
              onChange={(e) => change(role, e.target.value)}
            >
              <option value="">{options.length ? `Select a ${d.role_label}…` : `No ${d.role_label} accounts`}</option>
              {options.map((p) => (
                <option key={p.id} value={p.id}>{p.full_name} · {p.email}</option>
              ))}
            </select>
            {savingRole === d.role && <Check size={16} className="text-accent shrink-0 animate-pulse" />}
          </div>
        );
      },
    },
  ];

  if (denied) {
    return (
      <Page>
        <ListToolbar title="Default assignees" />
        <p className="text-footnote text-label-secondary">Sign in as the Admin account to manage defaults.</p>
      </Page>
    );
  }
  if (!defaults) return <Page><ListToolbar title="Default assignees" /><Loader /></Page>;

  const groups: TableGroup<RoleDefault>[] = [
    { id: 'defaults', label: 'Auto-routing defaults', hue: 'var(--color-accent)', rows: defaults },
  ];

  return (
    <Page>
      <ListToolbar
        title="Default assignees"
        subtitle="Every new brief auto-routes to these accounts. The person a task lands on can still reassign it to a teammate."
      />
      <DataTable columns={columns} groups={groups} rowKey={(d) => d.role} />
    </Page>
  );
}
