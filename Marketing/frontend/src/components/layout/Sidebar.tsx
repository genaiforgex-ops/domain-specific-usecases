import { NavLink } from 'react-router-dom';
import { useApp } from '../../state/AppContext';
import { ROLES, can } from '../../lib/roles';
import { Icon } from '../ui/Icon';
import type { NavItem } from '../../lib/types';
import { cn } from '../../lib/cn';

// A single slim, labelled icon rail — every one of the role's pages, plus the
// read-only Audit log for roles that may see it (Admin only), stacked as
// icon-over-label. No secondary panel.

function useCounts() {
  const { role, bcInbox, cwCopyPending, approvalPending, designPending } = useApp();
  return (badgeKey: NonNullable<NavItem['badgeKey']>): number => {
    if (!role) return 0;
    switch (role) {
      case 'PL':
        if (badgeKey === 'inbox') return bcInbox.length + approvalPending;
        if (badgeKey === 'pl.mybriefs') return bcInbox.filter((b) => b.priority === 'high').length;
        if (badgeKey === 'pl.approvals') return approvalPending;
        return 0;
      case 'CW':
        return badgeKey === 'cw.copies' || badgeKey === 'inbox' ? cwCopyPending : 0;
      case 'ML':
        return badgeKey === 'ml.approvals' || badgeKey === 'inbox' ? approvalPending : 0;
      case 'DS':
        return badgeKey === 'ds.assets' || badgeKey === 'inbox' ? designPending : 0;
      default:
        return 0;
    }
  };
}

export function Sidebar({
  onNavigate,
  drawer = false,
}: {
  onNavigate?: () => void;
  drawer?: boolean;
}) {
  const { role } = useApp();
  const countFor = useCounts();
  if (!role) return null;
  const r = ROLES[role];

  return (
    <nav
      className={cn(
        'flex h-full w-[68px] shrink-0 flex-col items-center gap-1 overflow-y-auto border-r border-separator bg-bg py-3',
        drawer && 'shadow-elevated',
      )}
      aria-label="Primary"
    >
      {r.nav.map((item) => (
        <RailLink key={item.to} item={item} homeTo={r.home} onNavigate={onNavigate} count={item.badgeKey ? countFor(item.badgeKey) : 0} />
      ))}
      {can(role, 'audit.view') && (
        <>
          <span className="my-1 h-px w-8 shrink-0 bg-separator" aria-hidden />
          <RailLink
            item={{ label: 'Audit', to: '/audit', icon: 'ScrollText' }}
            homeTo={r.home}
            onNavigate={onNavigate}
            count={0}
          />
        </>
      )}
    </nav>
  );
}

// A rail entry: icon stacked over a tiny label, Monday-style, blue when active.
function RailLink({
  item,
  homeTo,
  onNavigate,
  count,
}: {
  item: NavItem;
  homeTo: string;
  onNavigate?: () => void;
  count: number;
}) {
  return (
    <NavLink
      to={item.to}
      end={item.to === homeTo}
      onClick={onNavigate}
      title={item.label}
      className={({ isActive }) =>
        cn(
          'relative flex h-14 w-[60px] flex-col items-center justify-center gap-1 rounded-lg transition-colors duration-fast focus-ring',
          isActive ? 'bg-accent-soft text-accent' : 'text-label-secondary hover:bg-fill-quaternary hover:text-label',
        )
      }
    >
      <span className="relative">
        <Icon name={item.icon} size={20} />
        {count > 0 && (
          <span
            className="absolute -right-1.5 -top-1.5 h-2 w-2 rounded-full ring-2 ring-[color:var(--color-bg)]"
            style={{ background: item.badgeKey === 'inbox' ? 'var(--color-error)' : 'var(--color-accent)' }}
          />
        )}
      </span>
      <span className="px-0.5 text-center text-[10px] font-semibold leading-tight">{item.label}</span>
    </NavLink>
  );
}
