import { useApp } from '../../state/AppContext';
import { ROLES } from '../../lib/roles';
import type { RoleId } from '../../lib/types';

const SELECT_CLASS =
  'w-full h-11 px-3.5 rounded-md bg-bg-secondary border border-separator text-body text-label focus-ring transition-shadow duration-fast disabled:opacity-50';

/** A labelled dropdown of the active accounts holding a given role — used to
 *  allocate a brief's next owner (copywriter, approvers, designer). */
export function AssigneeSelect({
  role,
  value,
  onChange,
  label,
  required,
  disabled,
  exclude,
}: Readonly<{
  role: RoleId;
  value: string | null;
  onChange: (id: string | null) => void;
  label?: string;
  required?: boolean;
  disabled?: boolean;
  /** Account id to hide from the list (e.g. the current holder reassigning). */
  exclude?: string | null;
}>) {
  const { people } = useApp();
  // Offer everyone IAM grants this role (a user may hold several), not just
  // those whose cached last-active role happens to match.
  const options = people.filter((p) => (p.roles ?? [p.role]).includes(role) && p.id !== exclude);
  const title = label ?? ROLES[role].title;

  return (
    <label className="block">
      <span className="block mb-1.5 text-footnote font-semibold text-label-secondary">
        {title}
        {required && <span className="text-error"> *</span>}
      </span>
      <select
        className={SELECT_CLASS}
        value={value ?? ''}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">{options.length ? `Select a ${title}…` : `No ${title} accounts`}</option>
        {options.map((p) => (
          <option key={p.id} value={p.id}>
            {p.full_name} · {p.email}
          </option>
        ))}
      </select>
    </label>
  );
}
