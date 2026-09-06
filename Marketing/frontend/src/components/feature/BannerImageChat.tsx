import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Sparkles, Send, AlertCircle, ImageIcon, ImagePlus, Check, CheckCircle2, Sliders, Wand2, X } from 'lucide-react';
import { Button } from '../ui/Button';
import { MagicOverlay, MAGIC_PHRASES } from './MagicOverlay';
import { api, ApiError } from '../../lib/api';
import { cn } from '../../lib/cn';
import type { BannerImage, BannerImageMessage } from '../../lib/types';

// Mirrors banner_image_service.MAX_REFERENCES — the server rejects the fifth, so the
// Attach button hides rather than offering a pick that will bounce.
const MAX_REFERENCES = 4;

// Chat-with-image: a centered dialog — the live preview on the left, the version
// history on the right, and a comment composer across the bottom. The Designer
// types a change ("warmer light", "lose the phone") and Nano Banana edits the
// previewed version to match. Every turn is a new version; the one marked Current
// is what the card shows and what the Figma export uses.
export function BannerImageChat({
  briefId,
  image,
  headline,
  onClose,
  onUpdated,
  onSwitchToManual,
}: {
  briefId: string;
  image: BannerImage | null;
  headline: string;
  onClose: () => void;
  onUpdated: (img: BannerImage) => void;
  /** Hand this image to the Design Studio's manual tools instead. */
  onSwitchToManual?: () => void;
}) {
  const [messages, setMessages] = useState<BannerImageMessage[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<'edit' | 'switch' | null>(null); // what busy is doing
  const [error, setError] = useState<string | null>(null);
  // Reference images attached to the turn being composed — "make it look like this".
  // They're held in the browser and posted with the comment, so they belong to that
  // one edit and there's nothing to clean up if the Designer changes their mind.
  const [attachments, setAttachments] = useState<File[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const threadEndRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [stageBox, setStageBox] = useState({ w: 0, h: 0 });
  // The previewed version's shape, learnt when its PNG loads. Heroes come in
  // square, 16:9 and 9:16, so the frame is sized to the image rather than the
  // other way round — otherwise a square sits marooned in a stage-wide box.
  const [aspect, setAspect] = useState<number | null>(null);
  // Shown on the preview so the Designer can see the frame hold across versions.
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  const measure = (w: number, h: number) => {
    setAspect(w / h);
    setSize({ w, h });
  };

  const imageId = image?.id ?? null;
  const activeId = image?.active_message_id ?? null; // the live version (card + export)
  const open = imageId !== null;

  // Load the thread whenever the dialog opens on a new image.
  useEffect(() => {
    if (imageId === null) return;
    let active = true;
    setMessages(null);
    setSelectedId(null);
    setDraft('');
    setAttachments([]);
    setError(null);
    setAspect(null);
    setSize(null);
    api
      .bannerImageMessages(briefId, imageId)
      .then((ms) => {
        if (!active) return;
        setMessages(ms);
        // Preview the live version (fall back to the latest turn).
        const live = ms.find((m) => m.id === activeId) ?? ms[ms.length - 1];
        if (live) setSelectedId(live.id);
      })
      .catch(() => active && setError('Could not load this image’s history.'));
    return () => {
      active = false;
    };
    // activeId intentionally omitted: re-selecting the live version on every
    // pointer change would yank the Designer's preview away mid-review.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [briefId, imageId]);

  // Close on Escape; lock body scroll while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !busy && onClose();
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, busy, onClose]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages?.length]);

  // Track the free space around the preview so the frame can be fitted to it.
  // contentRect excludes the stage's padding, which is the space actually usable.
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) =>
      setStageBox({ w: entry.contentRect.width, h: entry.contentRect.height }),
    );
    ro.observe(el);
    return () => ro.disconnect();
  }, [open]);

  // Largest box of the image's shape that fits the stage — the contain maths the
  // browser would do for `object-fit`, lifted out so the border hugs the image.
  const display = useMemo(() => {
    if (!aspect || !stageBox.w || !stageBox.h) return null;
    let w = stageBox.w;
    let h = w / aspect;
    if (h > stageBox.h) {
      h = stageBox.h;
      w = h * aspect;
    }
    return { w, h };
  }, [aspect, stageBox.w, stageBox.h]);

  const attachReferences = (files: FileList | null) => {
    if (!files?.length) return;
    const room = MAX_REFERENCES - attachments.length;
    const skipped = files.length - room;
    setError(
      skipped > 0
        ? `Up to ${MAX_REFERENCES} reference images per edit — ${skipped} ${
            skipped === 1 ? 'was' : 'were'
          } skipped.`
        : null,
    );
    setAttachments((prev) => [...prev, ...Array.from(files).slice(0, room)]);
  };

  const send = async () => {
    if (imageId === null || !draft.trim() || busy) return;
    setBusy(true);
    setPhase('edit');
    setError(null);
    try {
      // Branch from the previewed version; with no thread yet (legacy image),
      // pass undefined so the backend edits the image's current bytes.
      const { image: updated, message } = await api.commentBannerImage(
        briefId,
        imageId,
        draft.trim(),
        selectedId ?? undefined,
        attachments,
      );
      setMessages((prev) => (prev ? [...prev, message] : [message]));
      setSelectedId(message.id);
      setDraft('');
      setAttachments([]); // consumed by this turn
      onUpdated(updated); // refresh the card thumbnail + parent state
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not update the image.');
    } finally {
      setBusy(false);
      setPhase(null);
    }
  };

  // Promote the previewed version to live without editing it.
  const useVersion = async () => {
    if (imageId === null || selectedId === null || selectedId === activeId || busy) return;
    setBusy(true);
    setPhase('switch');
    setError(null);
    try {
      onUpdated(await api.selectBannerImageVersion(briefId, imageId, selectedId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not switch versions.');
    } finally {
      setBusy(false);
      setPhase(null);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const previewKey = selectedId !== null ? `v${selectedId}` : 'current';

  // Portal to <body> so the dialog escapes the page's `main` stacking context
  // (z-10) and renders above the sticky Topbar (z-40).
  return createPortal(
    <AnimatePresence>
      {open && imageId !== null && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
          <div className="absolute inset-0 bg-black/45 backdrop-blur-sm" onClick={() => !busy && onClose()} aria-hidden />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Edit with AI"
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ type: 'spring', stiffness: 360, damping: 30 }}
            /* Same footprint as the manual editor, so switching modes doesn't
               resize the window under the Designer. */
            className="relative w-full max-w-[100rem] h-[94vh] flex flex-col rounded-2xl bg-bg shadow-elevated overflow-hidden"
          >
            {/* Header */}
            <header className="flex items-center justify-between gap-3 px-5 py-3.5 hairline-b shrink-0">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-headline text-label">
                  <Wand2 size={17} className="text-accent shrink-0" /> Edit with AI
                </div>
                <p className="text-caption text-label-tertiary line-clamp-1 mt-0.5">{headline}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {onSwitchToManual && (
                  <Button variant="plain" size="sm" onClick={onSwitchToManual} disabled={busy}>
                    <Sliders size={14} /> <span className="hidden sm:inline">Edit manually</span>
                  </Button>
                )}
                <button
                  onClick={() => !busy && onClose()}
                  aria-label="Close"
                  className="grid place-items-center h-9 w-9 -mr-1.5 rounded-full text-label-secondary hover:bg-fill-quaternary focus-ring"
                >
                  <X size={18} />
                </button>
              </div>
            </header>

            {/* Body: image (left) + versions (right) */}
            <div className="flex-1 min-h-0 flex flex-col md:flex-row">
              {/* Live preview — the frame is fitted to the image's own shape, so a
                  16:9 messaging hero uses the full width and a square one keeps a
                  square border instead of floating in a stage-wide box. */}
              <div
                ref={stageRef}
                className="flex-1 min-w-0 min-h-0 grid place-items-center bg-bg-secondary p-3 md:p-4"
              >
                <div
                  className="relative rounded-xl border border-separator bg-bg overflow-hidden grid place-items-center transition-[width,height] duration-200 ease-out"
                  style={display ? { width: display.w, height: display.h } : { width: '100%', height: '100%' }}
                >
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={previewKey}
                      className="absolute inset-0 grid place-items-center"
                      initial={{ opacity: 0, scale: 1.02 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.22, ease: 'easeOut' }}
                    >
                      {selectedId !== null ? (
                        <VersionImage
                          briefId={briefId}
                          imageId={imageId}
                          messageId={selectedId}
                          alt={headline}
                          onMeasured={measure}
                        />
                      ) : messages === null ? (
                        <ImageIcon size={30} className="text-label-tertiary" />
                      ) : (
                        // No thread yet (legacy image): show its current bytes.
                        <CurrentImage
                          briefId={briefId}
                          imageId={imageId}
                          alt={headline}
                          onMeasured={measure}
                        />
                      )}
                    </motion.div>
                  </AnimatePresence>

                  <AnimatePresence>
                    {phase === 'edit' ? (
                      <MagicOverlay
                        key="edit"
                        phrases={MAGIC_PHRASES.imageEdit}
                        label="Reworking the image"
                        className="rounded-xl"
                      />
                    ) : phase === 'switch' ? (
                      <motion.div
                        key="switch"
                        className="absolute inset-0 z-10 grid place-items-center bg-black/40 backdrop-blur-[2px]"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                      >
                        <span className="h-5 w-5 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                      </motion.div>
                    ) : null}
                  </AnimatePresence>

                  {size && (
                    <span className="absolute bottom-2 left-2 rounded-md bg-black/55 px-1.5 py-0.5 text-caption2 font-medium text-white/90 tabular-nums pointer-events-none">
                      {size.w} × {size.h}
                    </span>
                  )}
                </div>
              </div>

              {/* Versions */}
              <div className="w-full md:w-[300px] shrink-0 flex flex-col border-t md:border-t-0 md:border-l border-separator min-h-0">
                <div className="flex items-center justify-between gap-2 px-4 py-3 hairline-b shrink-0">
                  <p className="text-caption2 font-semibold text-label-tertiary uppercase tracking-wide">
                    Versions
                  </p>
                  {selectedId !== null &&
                    (selectedId === activeId ? (
                      <span className="flex items-center gap-1 text-caption2 font-semibold text-success">
                        <CheckCircle2 size={12} /> Current
                      </span>
                    ) : (
                      <Button size="sm" variant="tinted" onClick={useVersion} disabled={busy}>
                        <Check size={14} /> Use this version
                      </Button>
                    ))}
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto px-3 py-3 max-h-[28vh] md:max-h-none">
                  {messages === null ? (
                    <div className="flex justify-center py-6">
                      <span className="h-5 w-5 rounded-full border-2 border-separator border-t-accent animate-spin" />
                    </div>
                  ) : messages.length === 0 ? (
                    <p className="text-caption text-label-tertiary px-1 py-2">
                      No edits yet. Describe a change below to create the first version.
                    </p>
                  ) : (
                    <ol className="space-y-1.5">
                      {messages.map((m, i) => {
                        const selected = m.id === selectedId;
                        return (
                          <motion.li
                            key={m.id}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.18, delay: Math.min(i * 0.025, 0.2) }}
                          >
                            <button
                              onClick={() => setSelectedId(m.id)}
                              className={cn(
                                'w-full text-left rounded-lg border px-3 py-2 focus-ring transition-colors',
                                selected
                                  ? 'border-accent bg-accent-soft'
                                  : 'border-separator bg-bg-secondary hover:bg-fill-quaternary',
                              )}
                            >
                              <div className="flex items-center gap-2">
                                <span className="grid place-items-center h-5 w-5 shrink-0 rounded-full bg-fill-quaternary text-caption2 font-bold text-label-tertiary">
                                  {i + 1}
                                </span>
                                <span className="flex-1 text-footnote text-label line-clamp-2">
                                  {m.comment ?? 'Original image'}
                                </span>
                                {m.id === activeId && (
                                  <CheckCircle2 size={13} className="text-success shrink-0" />
                                )}
                              </div>
                            </button>
                          </motion.li>
                        );
                      })}
                      <div ref={threadEndRef} />
                    </ol>
                  )}
                </div>
              </div>
            </div>

            {/* Composer */}
            <div className="shrink-0 px-4 py-3 hairline-t glass">
              <AnimatePresence>
                {error && (
                  <motion.p
                    className="flex items-center gap-1.5 text-footnote text-error mb-2"
                    role="alert"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                  >
                    <AlertCircle size={14} className="shrink-0" /> {error}
                  </motion.p>
                )}
              </AnimatePresence>

              {/* Reference images attached to this turn. */}
              {attachments.length > 0 && (
                <div className="flex items-center gap-2 flex-wrap mb-2">
                  {attachments.map((file, i) => (
                    <AttachmentThumb
                      key={`${file.name}-${i}`}
                      file={file}
                      disabled={busy}
                      onRemove={() => setAttachments((prev) => prev.filter((_, j) => j !== i))}
                    />
                  ))}
                </div>
              )}

              <div className="flex items-end gap-2 rounded-xl border border-separator bg-bg-secondary p-2 focus-within:border-accent transition-colors">
                <button
                  onClick={() => fileRef.current?.click()}
                  disabled={busy || attachments.length >= MAX_REFERENCES}
                  title={
                    attachments.length >= MAX_REFERENCES
                      ? `Up to ${MAX_REFERENCES} reference images per edit`
                      : 'Attach a reference image'
                  }
                  aria-label="Attach a reference image"
                  className="grid place-items-center h-9 w-9 shrink-0 rounded-lg text-label-secondary hover:bg-fill-quaternary hover:text-label focus-ring transition-colors disabled:opacity-40 disabled:pointer-events-none"
                >
                  <ImagePlus size={17} />
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  hidden
                  onChange={(e) => {
                    attachReferences(e.target.files);
                    e.target.value = ''; // let the same file be re-picked after a removal
                  }}
                />
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={onKeyDown}
                  disabled={busy}
                  rows={1}
                  maxLength={2000}
                  placeholder={
                    attachments.length
                      ? 'What should it take from the reference? — e.g. “use this colour grade and mood”'
                      : 'Describe a change — e.g. “warmer light, lose the phone, more space on the left”'
                  }
                  className="flex-1 resize-none bg-transparent px-2 py-1.5 text-body text-label placeholder:text-label-tertiary focus:outline-none disabled:opacity-50 max-h-28"
                />
                <Button size="sm" onClick={send} disabled={busy || !draft.trim()}>
                  <Send size={14} /> {busy ? 'Editing…' : 'Send'}
                </Button>
              </div>
              <p className="text-caption2 text-label-tertiary mt-1.5 px-1">
                <Sparkles size={11} className="inline -mt-0.5 mr-1 text-accent" />
                {attachments.length > 0 && (
                  <>
                    {attachments.length} reference{attachments.length === 1 ? '' : 's'} on this
                    edit ·{' '}
                  </>
                )}
                Edits the previewed version · Enter to send, Shift+Enter for a new line
              </p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

// One reference image attached to the turn being composed. The file is still in the
// browser, so the preview comes straight off it — no upload, nothing to fetch back.
function AttachmentThumb({
  file,
  disabled,
  onRemove,
}: {
  file: File;
  disabled: boolean;
  onRemove: () => void;
}) {
  const url = useMemo(() => URL.createObjectURL(file), [file]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.16 }}
      className="group relative h-14 w-14 rounded-lg overflow-hidden border border-separator bg-bg-secondary"
      title={file.name}
    >
      <img src={url} alt={file.name} className="h-full w-full object-cover" />
      <button
        onClick={onRemove}
        disabled={disabled}
        aria-label={`Remove ${file.name}`}
        className="absolute top-0.5 right-0.5 grid place-items-center h-5 w-5 rounded-full bg-black/55 text-white opacity-0 group-hover:opacity-100 focus:opacity-100 focus-ring transition-opacity disabled:pointer-events-none"
      >
        <X size={11} />
      </button>
    </motion.div>
  );
}

// The image's current bytes — used as the preview when it has no chat thread yet.
function CurrentImage({
  briefId,
  imageId,
  alt,
  onMeasured,
}: {
  briefId: string;
  imageId: string;
  alt: string;
  onMeasured?: (width: number, height: number) => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let revoked: string | null = null;
    let active = true;
    api
      .bannerImageObjectUrl(briefId, imageId)
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
  }, [briefId, imageId]);
  if (!url) {
    return <span className="h-6 w-6 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading image" />;
  }
  return (
    <img
      src={url}
      alt={alt}
      onLoad={(e) => onMeasured?.(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight)}
      className="h-full w-full object-contain"
    />
  );
}

// One version's PNG — fetched with the bearer token, revoked on change/unmount.
function VersionImage({
  briefId,
  imageId,
  messageId,
  alt,
  onMeasured,
}: {
  briefId: string;
  imageId: string;
  messageId: string;
  alt: string;
  onMeasured?: (width: number, height: number) => void;
}) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let revoked: string | null = null;
    let active = true;
    setUrl(null);
    api
      .bannerImageMessageObjectUrl(briefId, imageId, messageId)
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
  }, [briefId, imageId, messageId]);

  if (!url) {
    return <span className="h-6 w-6 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading image" />;
  }
  return (
    <img
      src={url}
      alt={alt}
      onLoad={(e) => onMeasured?.(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight)}
      className="h-full w-full object-contain"
    />
  );
}
