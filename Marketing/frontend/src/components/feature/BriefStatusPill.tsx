import { Pill } from '../ui/primitives';
import type { BriefStatus } from '../../lib/types';

// Status meaning never rides on color alone — every pill carries a label.
const META: Record<BriefStatus, { label: string; hue: string }> = {
  draft: { label: 'Draft', hue: 'var(--color-label-tertiary)' },
  submitted: { label: 'Pending approval', hue: 'var(--color-warning)' },
  approved: { label: 'Approved', hue: 'var(--color-success)' },
  changes_requested: { label: 'Changes requested', hue: 'var(--color-error)' },
};

export function BriefStatusPill({ status }: { status: BriefStatus }) {
  const m = META[status];
  return <Pill hue={m.hue}>{m.label}</Pill>;
}

export const SIZE_LABEL: Record<string, string> = {
  small: 'Small',
  medium: 'Medium',
  large: 'Large',
};
