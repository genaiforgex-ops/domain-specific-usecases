import { useEffect, useRef, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { RefreshCw, CheckCircle2, ImageUp, Sliders, Wand2 } from 'lucide-react';
import { Pill } from '../ui/primitives';
import { Button } from '../ui/Button';
import { MagicOverlay, MAGIC_PHRASES } from './MagicOverlay';
import { api } from '../../lib/api';
import type { BannerImage } from '../../lib/types';

// Let the OS picker offer any image — the server decodes and normalises to PNG,
// so restricting to three MIME types here only greyed out real files (e.g. an
// iPhone/Mac HEIC photo) and made the Upload button look broken.
const ACCEPTED_UPLOAD_TYPES = 'image/*';

// Icon stacked over a tiny label, Monday-style — same shape as the sidebar rail.
const ACTION_BUTTON_CLASS = 'flex-1 flex-col gap-0.5 h-12 px-0.5 py-1.5';
const ACTION_LABEL_CLASS = 'w-full truncate text-center text-[10px] font-semibold leading-tight';

// One reviewable hero image. Fetches the PNG with the bearer token (an <img src>
// can't carry it), shows it, and revokes the object URL on unmount/reload.
export function BannerImageCard({
  briefId,
  img,
  headline,
  onRegenerate,
  onEdit,
  onManualEdit,
  onUpload,
  regenerating,
  uploading,
  disabled,
}: Readonly<{
  briefId: string;
  img: BannerImage;
  headline: string;
  onRegenerate: () => void;
  onEdit?: () => void;
  /** Open the Design Studio's hand tools — crop, straighten, tune, sharpen. */
  onManualEdit?: () => void;
  /** Not satisfied with the AI output? Swap in a file the Designer supplies instead. */
  onUpload?: (file: File) => void;
  regenerating?: boolean;
  uploading?: boolean;
  disabled?: boolean;
}>) {
  const [url, setUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let revoked: string | null = null;
    let active = true;
    api
      .bannerImageObjectUrl(briefId, img.id)
      .then((u) => {
        if (active) {
          revoked = u;
          setUrl(u);
        } else {
          URL.revokeObjectURL(u);
        }
      })
      .catch(() => setUrl(null));
    return () => {
      active = false;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [briefId, img.id, img.updated_at]);

  return (
    <div className="rounded-lg border border-separator bg-bg-secondary overflow-hidden">
      {/* Show the hero at its true shape (square / 16:9 / 9:16, per the template's
          output aspect) so vertical and horizontal images are fully visible — never
          cropped to a square. */}
      <div className="relative bg-fill-quaternary flex items-center justify-center overflow-hidden min-h-[8rem]">
        {url ? (
          <img
            src={url}
            alt={headline}
            className="block w-full h-auto max-h-[70vh] object-contain"
          />
        ) : (
          <span className="my-12 h-5 w-5 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading image" />
        )}
        <AnimatePresence>
          {(regenerating || uploading) && (
            <MagicOverlay
              phrases={MAGIC_PHRASES.image}
              label={uploading ? 'Uploading your image' : 'Regenerating image'}
              className="rounded-none"
            />
          )}
        </AnimatePresence>
      </div>
      <div className="p-3">
        <div className="flex items-start justify-between gap-2 mb-2">
          <p className="text-footnote text-label line-clamp-2">{headline}</p>
          {img.status === 'approved' ? (
            <Pill hue="var(--color-success)" icon={<CheckCircle2 size={11} />}>Approved</Pill>
          ) : (
            <Pill>Pending</Pill>
          )}
        </div>
        {/* Two ways to change the photo: describe it to the AI, or reach for the
            hand tools. Regenerating rolls a brand-new shot from the prompt. Icon
            over a tiny label, single row, same shape as the sidebar rail. */}
        <div className="flex items-center gap-1">
          {onEdit && (
            <Button
              variant="tinted"
              size="sm"
              onClick={onEdit}
              disabled={disabled}
              title="Edit with AI"
              className={ACTION_BUTTON_CLASS}
            >
              <Wand2 size={15} />
              <span className={ACTION_LABEL_CLASS}>AI Edit</span>
            </Button>
          )}
          {onManualEdit && (
            <Button
              variant="glass"
              size="sm"
              onClick={onManualEdit}
              disabled={disabled}
              title="Edit manually"
              className={ACTION_BUTTON_CLASS}
            >
              <Sliders size={15} />
              <span className={ACTION_LABEL_CLASS}>Manual</span>
            </Button>
          )}
          <Button
            variant="plain"
            size="sm"
            onClick={onRegenerate}
            disabled={disabled}
            title="Regenerate"
            className={ACTION_BUTTON_CLASS}
          >
            <RefreshCw size={15} />
            <span className={ACTION_LABEL_CLASS}>Regen</span>
          </Button>
          {onUpload && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_UPLOAD_TYPES}
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = ''; // allow re-picking the same file next time
                  if (file) onUpload(file);
                }}
              />
              <Button
                variant="plain"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled}
                title="Not happy with this? Upload your own"
                className={ACTION_BUTTON_CLASS}
              >
                <ImageUp size={15} />
                <span className={ACTION_LABEL_CLASS}>Upload</span>
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
