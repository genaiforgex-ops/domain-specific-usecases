import { useEffect, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { api } from '../../lib/api';
import type { BriefReferenceImage } from '../../lib/types';

/**
 * Read-only gallery of a brief's sample/example reference images — shown with the
 * brief wherever it's read (detail page, review, sign-off) so everyone down the
 * chain sees what it's built against. Click a thumbnail to enlarge it.
 */
export function BriefReferenceGallery({
  briefId,
  images,
}: Readonly<{ briefId: string; images: BriefReferenceImage[] }>) {
  const [zoom, setZoom] = useState<BriefReferenceImage | null>(null);

  if (!images.length) return null;

  return (
    <section className="mt-10">
      <h2 className="text-title-3 font-bold text-label tracking-tight mb-5 pb-2 border-b border-separator">
        Samples / Examples / References
      </h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {images.map((img) => (
          <button
            key={img.id}
            type="button"
            onClick={() => setZoom(img)}
            className="group block overflow-hidden rounded-md border border-separator bg-bg-secondary text-left focus-ring"
          >
            <div className="aspect-[4/3] w-full">
              <ReferenceImg briefId={briefId} image={img} className="h-full w-full object-cover" />
            </div>
            {img.caption && (
              <p className="truncate px-2 py-1.5 text-caption2 text-label-secondary" title={img.caption}>
                {img.caption}
              </p>
            )}
          </button>
        ))}
      </div>

      {zoom && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
          onClick={() => setZoom(null)}
          role="dialog"
          aria-modal="true"
        >
          <button
            type="button"
            onClick={() => setZoom(null)}
            className="absolute right-4 top-4 inline-flex h-9 w-9 items-center justify-center rounded-md bg-white/15 text-white focus-ring"
            aria-label="Close"
          >
            <X size={18} />
          </button>
          <div className="max-h-full max-w-4xl" onClick={(e) => e.stopPropagation()}>
            <ReferenceImg
              briefId={briefId}
              image={zoom}
              className="max-h-[80vh] w-auto rounded-md object-contain"
            />
            {zoom.caption && (
              <p className="mt-3 text-center text-footnote text-white/90">{zoom.caption}</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

/** Fetches the image's PNG as an object URL (cookie-authenticated) and revokes it
 *  on unmount. */
function ReferenceImg({
  briefId,
  image,
  className,
}: Readonly<{ briefId: string; image: BriefReferenceImage; className?: string }>) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    api
      .briefReferenceImageObjectUrl(briefId, image.id)
      .then((u) => {
        objectUrl = u;
        if (active) setUrl(u);
        else URL.revokeObjectURL(u);
      })
      .catch(() => active && setUrl(null));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [briefId, image.id]);

  if (!url) {
    return (
      <div className="flex h-full w-full items-center justify-center text-label-tertiary">
        <Loader2 size={16} className="animate-spin" />
      </div>
    );
  }
  return <img src={url} alt={image.caption ?? image.filename} className={className} />;
}
