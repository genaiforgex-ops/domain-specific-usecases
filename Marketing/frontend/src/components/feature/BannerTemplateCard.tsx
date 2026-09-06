import { useEffect, useState } from 'react';
import { Check, ImageOff, Star } from 'lucide-react';
import { Pill } from '../ui/primitives';
import { api } from '../../lib/api';
import { AD_SIZE_LABELS } from '../../lib/adSizes';
import { cn } from '../../lib/cn';
import type { BannerTemplateSummary } from '../../lib/types';

// One selectable banner template, shown as its reference artwork — the Designer
// picks the layout by looking at a sample banner, not by reading a name. The
// artwork lives in the DB (banner_templates.preview_image), so it needs the bearer
// token: fetch it as a blob and revoke the object URL on unmount. Templates with no
// artwork uploaded yet fall back to a labelled placeholder, so the picker still works.
export function BannerTemplateCard({
  template,
  selected,
  disabled,
  onSelect,
}: Readonly<{
  template: BannerTemplateSummary;
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
}>) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!template.has_preview) {
      setUrl(null);
      setFailed(true);
      return;
    }
    let revoked: string | null = null;
    let active = true;
    setFailed(false);
    api
      .bannerTemplatePreviewObjectUrl(template.id)
      .then((u) => {
        if (active) {
          revoked = u;
          setUrl(u);
        } else {
          URL.revokeObjectURL(u);
        }
      })
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [template.id, template.has_preview, template.updated_at]);

  const sizes = template.size_names.map((n) => AD_SIZE_LABELS[n] ?? n).join(' · ');

  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        'group text-left rounded-lg border bg-bg-secondary overflow-hidden focus-ring transition-shadow',
        selected ? 'border-accent ring-2 ring-accent/40' : 'border-separator hover:shadow-card',
        disabled ? 'cursor-default opacity-60' : 'cursor-pointer',
      )}
    >
      <div className="relative bg-fill-quaternary flex items-center justify-center overflow-hidden aspect-[4/3]">
        {url ? (
          <img src={url} alt={`${template.name} sample banner`} className="block h-full w-full object-contain" />
        ) : failed ? (
          <span className="flex flex-col items-center gap-1 text-label-tertiary">
            <ImageOff size={20} />
            <span className="text-caption2">No sample yet</span>
          </span>
        ) : (
          <span
            className="h-5 w-5 rounded-full border-2 border-separator border-t-accent animate-spin"
            aria-label="Loading template preview"
          />
        )}
        {selected && (
          <span className="absolute top-2 right-2 grid place-items-center h-6 w-6 rounded-full bg-accent text-[color:var(--color-on-accent)] shadow-card">
            <Check size={14} />
          </span>
        )}
      </div>
      <div className="p-3">
        <div className="flex items-start justify-between gap-2">
          <p className="text-footnote font-semibold text-label line-clamp-2">{template.name}</p>
          {template.is_default && (
            <Pill icon={<Star size={10} />} className="shrink-0">
              Default
            </Pill>
          )}
        </div>
        {template.description && (
          <p className="mt-1 text-caption2 text-label-secondary line-clamp-2">{template.description}</p>
        )}
        {sizes && <p className="mt-1 text-caption2 text-label-tertiary line-clamp-2">{sizes}</p>}
      </div>
    </button>
  );
}
