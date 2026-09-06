import { useEffect, useState } from 'react';
import { ImageIcon, ExternalLink, CheckCircle2 } from 'lucide-react';
import { Card, Pill, EmptyState } from '../ui/primitives';
import { api } from '../../lib/api';
import type { BannerImage, Creative } from '../../lib/types';

// One read-only banner tile — fetches the PNG with the bearer token (an <img src>
// can't carry it) and revokes the object URL on unmount.
function ReviewTile({ briefId, img, headline }: Readonly<{ briefId: string; img: BannerImage; headline: string }>) {
  const [url, setUrl] = useState<string | null>(null);
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
      {/* True aspect (square / 16:9 / 9:16) so reviewers see the real hero, uncropped. */}
      <div className="relative bg-fill-quaternary flex items-center justify-center overflow-hidden min-h-[8rem]">
        {url ? (
          <img src={url} alt={headline} className="block w-full h-auto max-h-[70vh] object-contain" />
        ) : (
          <span className="my-12 h-5 w-5 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading image" />
        )}
      </div>
      <div className="p-3 flex items-start justify-between gap-2">
        <p className="text-footnote text-label line-clamp-2">{headline}</p>
        {img.status === 'approved' && (
          <Pill hue="var(--color-success)" icon={<CheckCircle2 size={11} />}>Approved</Pill>
        )}
      </div>
    </div>
  );
}

// The finished banners, shown read-only for the design review + sign-off. Surfaces
// the images the Marketing Lead approves and the Product Lead signs off on, plus a
// link to the exported Figma file when there is one.
export function DesignReviewGallery({
  briefId,
  figmaUrl,
}: Readonly<{ briefId: string; figmaUrl: string | null }>) {
  const [images, setImages] = useState<BannerImage[] | null>(null);
  const [headlines, setHeadlines] = useState<Record<string, string>>({});

  useEffect(() => {
    let active = true;
    Promise.all([api.bannerImages(briefId), api.listCreatives(briefId)])
      .then(([imgs, creatives]: [BannerImage[], Creative[]]) => {
        if (!active) return;
        setImages(imgs);
        setHeadlines(Object.fromEntries(creatives.map((c) => [c.id, c.headline])));
      })
      .catch(() => active && setImages([]));
    return () => {
      active = false;
    };
  }, [briefId]);

  // Nothing produced yet — don't render an empty shell.
  if (images !== null && images.length === 0 && !figmaUrl) return null;

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-2 mb-3">
        <p className="text-subheadline font-bold text-label flex items-center gap-2">
          <ImageIcon size={16} /> Design for review
        </p>
        {figmaUrl && (
          <a
            href={figmaUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-footnote font-medium text-accent focus-ring rounded-md"
          >
            Open in Figma <ExternalLink size={13} />
          </a>
        )}
      </div>

      {images === null ? (
        <div className="flex justify-center py-8">
          <span className="h-6 w-6 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading banners" />
        </div>
      ) : images.length === 0 ? (
        <EmptyState icon={<ImageIcon size={22} />} title="No banners yet" body="The Designer hasn't produced the banners for this brief." />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-3">
          {images.map((img) => (
            <ReviewTile key={img.id} briefId={briefId} img={img} headline={headlines[img.creative_id] ?? 'Banner'} />
          ))}
        </div>
      )}
    </Card>
  );
}
