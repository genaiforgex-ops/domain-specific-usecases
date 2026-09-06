import { useCallback, useEffect, useRef, useState } from 'react';
import { ImagePlus, Trash2, Loader2, AlertCircle } from 'lucide-react';
import { api, ApiError } from '../../lib/api';
import type { BriefReferenceImage } from '../../lib/types';
import { cn } from '../../lib/cn';

const MAX_IMAGES = 8;

/**
 * The "Samples / Examples / References" attachment on a brief — the Product Lead
 * (or the reviewing Marketing Lead) uploads example images so everyone down the
 * chain can see the visual references. Shown in the brief form beside the free-text
 * references field. Uploads need a persisted brief, so `ensureBriefId` saves the
 * draft first when the brief hasn't been created yet.
 */
export function BriefReferenceImages({
  briefId,
  ensureBriefId,
  onToast,
}: Readonly<{
  briefId: string | null;
  ensureBriefId: () => Promise<string | null>;
  onToast?: (msg: string, kind?: 'success' | 'error' | 'default') => void;
}>) {
  const [images, setImages] = useState<BriefReferenceImage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!briefId) return;
    let active = true;
    api
      .briefReferenceImages(briefId)
      .then((list) => active && setImages(list))
      .catch(() => active && setImages([]));
    return () => {
      active = false;
    };
  }, [briefId]);

  const onPick = useCallback(
    async (files: FileList | null) => {
      if (!files || !files.length) return;
      setBusy(true);
      setError(null);
      try {
        const id = briefId ?? (await ensureBriefId());
        if (!id) {
          setError('Save the brief before adding references.');
          return;
        }
        const room = MAX_IMAGES - images.length;
        const picked = Array.from(files).slice(0, Math.max(0, room));
        if (picked.length < files.length) {
          onToast?.(`A brief can carry at most ${MAX_IMAGES} references`, 'default');
        }
        const added: BriefReferenceImage[] = [];
        for (const file of picked) {
          added.push(await api.uploadBriefReferenceImage(id, file));
        }
        setImages((prev) => [...prev, ...added]);
        if (added.length) onToast?.(`Added ${added.length} reference${added.length > 1 ? 's' : ''}`, 'success');
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Could not upload that image.');
      } finally {
        setBusy(false);
        if (fileRef.current) fileRef.current.value = '';
      }
    },
    [briefId, ensureBriefId, images.length, onToast],
  );

  const onDelete = useCallback(
    async (image: BriefReferenceImage) => {
      if (!briefId) return;
      setError(null);
      const prev = images;
      setImages((list) => list.filter((i) => i.id !== image.id));
      try {
        await api.deleteBriefReferenceImage(briefId, image.id);
      } catch (e) {
        setImages(prev); // put it back if the delete failed
        setError(e instanceof ApiError ? e.message : 'Could not remove that image.');
      }
    },
    [briefId, images],
  );

  const full = images.length >= MAX_IMAGES;

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-3">
        <div>
          <p className="text-footnote font-semibold text-label-secondary">Reference images</p>
          <p className="text-caption text-label-tertiary mt-0.5">
            Sample copies / examples — shown with the brief and used as visual references for the
            design. Up to {MAX_IMAGES}, PNG/JPEG/WEBP, 10 MB each.
          </p>
        </div>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={busy || full}
          className={cn(
            'inline-flex shrink-0 items-center gap-1.5 rounded-md border border-separator px-3 h-9 text-footnote font-semibold text-label',
            'hover:bg-fill-quaternary focus-ring disabled:opacity-50 disabled:cursor-not-allowed',
          )}
        >
          {busy ? <Loader2 size={15} className="animate-spin" /> : <ImagePlus size={15} />}
          Add images
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          className="hidden"
          onChange={(e) => onPick(e.target.files)}
        />
      </div>

      {images.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {images.map((img) => (
            <ReferenceThumb
              key={img.id}
              briefId={briefId!}
              image={img}
              onDelete={() => onDelete(img)}
            />
          ))}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className="flex w-full flex-col items-center justify-center gap-1.5 rounded-md border border-dashed border-separator py-8 text-label-tertiary hover:bg-fill-quaternary focus-ring"
        >
          <ImagePlus size={20} />
          <span className="text-footnote">Add sample copies / example references</span>
        </button>
      )}

      {error && (
        <p className="flex items-center gap-1.5 text-caption text-error mt-2" role="alert">
          <AlertCircle size={13} className="shrink-0" /> {error}
        </p>
      )}
    </div>
  );
}

/** One thumbnail — fetches its PNG as an object URL (cookie-authenticated) and
 *  revokes it on unmount. */
function ReferenceThumb({
  briefId,
  image,
  onDelete,
}: Readonly<{
  briefId: string;
  image: BriefReferenceImage;
  onDelete: () => void;
}>) {
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

  return (
    <div className="group relative overflow-hidden rounded-md border border-separator bg-bg-secondary">
      <div className="aspect-[4/3] w-full">
        {url ? (
          <img src={url} alt={image.caption ?? image.filename} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-label-tertiary">
            <Loader2 size={16} className="animate-spin" />
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={onDelete}
        title="Remove"
        className="absolute right-1.5 top-1.5 inline-flex h-7 w-7 items-center justify-center rounded-md bg-black/55 text-white opacity-0 transition-opacity group-hover:opacity-100 focus-ring"
      >
        <Trash2 size={14} />
      </button>
      {image.caption && (
        <p className="truncate px-2 py-1.5 text-caption2 text-label-secondary" title={image.caption}>
          {image.caption}
        </p>
      )}
    </div>
  );
}
