import { ImageIcon } from 'lucide-react';
import { Pill } from '../ui/primitives';
import type { Creative, CreativeEdit } from '../../lib/types';

// One generated creative. In view mode it renders in the standard format
// (visual reference, headline, body, CTA, attribution/terms footer). In edit
// mode every field becomes editable so the Strategist can refine the copy
// before handing the set to the Designer.
export function CreativeCard({
  c,
  index,
  editing,
  onChange,
}: {
  c: Creative | CreativeEdit;
  index: number;
  editing?: boolean;
  onChange?: (patch: Partial<CreativeEdit>) => void;
}) {
  if (editing && onChange) {
    return (
      <div className="rounded-lg border border-separator bg-bg-secondary overflow-hidden">
        <div className="flex items-center justify-between px-4 pt-3">
          <span className="text-caption2 font-semibold text-label-tertiary uppercase tracking-wide">
            Creative {index + 1}
          </span>
        </div>
        <div className="p-4 pt-2 space-y-3">
          <EditField label="Visual reference" value={c.visual_reference ?? ''} onChange={(v) => onChange({ visual_reference: v })} textarea placeholder="Describe the art direction…" />
          <EditField label="Headline" value={c.headline} onChange={(v) => onChange({ headline: v })} placeholder="Headline" />
          <EditField label="Body" value={c.body} onChange={(v) => onChange({ body: v })} textarea placeholder="Body copy" />
          <div className="grid grid-cols-2 gap-3">
            <EditField label="CTA" value={c.cta} onChange={(v) => onChange({ cta: v })} maxLength={120} placeholder="Learn More" />
            <EditField label="Attribution" value={c.entity_attribution ?? ''} onChange={(v) => onChange({ entity_attribution: v })} placeholder="Brand / entity" />
          </div>
          <EditField label="Terms" value={c.terms ?? ''} onChange={(v) => onChange({ terms: v })} placeholder="Mandatory terms / disclaimer" />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-separator bg-bg-secondary overflow-hidden">
      {/* Visual reference — a stand-in for the art direction the brief describes. */}
      <div className="flex items-start gap-2 p-3 bg-[color:var(--color-fill-quaternary)]">
        <ImageIcon size={15} className="text-label-tertiary mt-0.5 shrink-0" />
        <p className="text-caption text-label-secondary leading-snug">
          {c.visual_reference || 'No visual reference provided.'}
        </p>
      </div>

      <div className="p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-caption2 font-semibold text-label-tertiary uppercase tracking-wide">
            Creative {index + 1}
          </span>
          <Pill>{c.cta}</Pill>
        </div>

        <p className="text-headline text-label leading-snug">{c.headline}</p>
        <p className="text-subheadline text-label-secondary mt-1.5 leading-snug">{c.body}</p>

        {(c.entity_attribution || c.terms) && (
          <div className="mt-3 pt-3 border-t border-separator flex flex-wrap items-center gap-x-3 gap-y-1">
            {c.entity_attribution && (
              <span className="text-caption font-semibold text-accent">{c.entity_attribution}</span>
            )}
            {c.terms && <span className="text-caption2 text-label-tertiary">{c.terms}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

function EditField({
  label,
  value,
  onChange,
  textarea,
  maxLength,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  textarea?: boolean;
  maxLength?: number;
  placeholder?: string;
}) {
  const cls =
    'w-full px-3 py-2 rounded-md bg-bg border border-separator text-subheadline text-label placeholder:text-label-tertiary focus-ring transition-shadow duration-fast';
  return (
    <label className="block">
      <span className="block mb-1 text-caption2 font-semibold text-label-tertiary uppercase tracking-wide">{label}</span>
      {textarea ? (
        <textarea value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} rows={2} className={`${cls} resize-y min-h-[56px]`} />
      ) : (
        <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} maxLength={maxLength} className={`${cls} h-11`} />
      )}
    </label>
  );
}
