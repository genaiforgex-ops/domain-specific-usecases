import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X, Check, RotateCcw, History, AlertCircle, Eye, Pencil } from 'lucide-react';
import { Button } from '../ui/Button';
import { CreativeCard } from './CreativeCard';
import { api, ApiError } from '../../lib/api';
import { timeAgo } from '../../lib/select';
import type { Creative, CreativeEdit, CreativeVersion } from '../../lib/types';

const toEdit = (c: Creative): CreativeEdit => ({
  id: c.id,
  headline: c.headline,
  body: c.body,
  cta: c.cta,
  visual_reference: c.visual_reference,
  entity_attribution: c.entity_attribution,
  terms: c.terms,
});

// Per-creative editor — a panel that zooms in from the left (Mac-style) over the
// Copy Studio. It carries everything for one creative: the editable fields and
// the version history (select a past version, or save the edit as a new one).
export function CreativeEditor({
  open,
  onClose,
  briefId,
  creative,
  index,
  onUpdated,
}: Readonly<{
  open: boolean;
  onClose: () => void;
  briefId: string;
  creative: Creative;
  index: number;
  onUpdated: (c: Creative) => void;
}>) {
  const [draft, setDraft] = useState<CreativeEdit>(() => toEdit(creative));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [versions, setVersions] = useState<CreativeVersion[] | null>(null);
  // A version the user is previewing (read-only) instead of editing the draft.
  const [previewId, setPreviewId] = useState<string | null>(null);
  const preview = previewId ? versions?.find((v) => v.id === previewId) ?? null : null;

  const loadVersions = () => {
    setVersions(null);
    api.creativeVersions(briefId, creative.id).then(setVersions).catch(() => setVersions([]));
  };

  // Reseed the draft from the live copy whenever the editor opens or the creative
  // changes (e.g. after restoring a version), and load its history on open.
  useEffect(() => {
    if (!open) return;
    setDraft(toEdit(creative));
    setError(null);
    setPreviewId(null);
  }, [open, creative]);

  useEffect(() => {
    if (open) loadVersions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, creative.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !busy && onClose();
    if (open) document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, busy, onClose]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onUpdated(await api.editCreative(briefId, creative.id, draft));
      loadVersions();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not save this version.');
    } finally {
      setBusy(false);
    }
  };

  const select = async (versionId: string) => {
    setBusy(true);
    setError(null);
    try {
      onUpdated(await api.selectCreativeVersion(briefId, creative.id, versionId));
      loadVersions();
      setPreviewId(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not switch version.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-x-0 bottom-0 top-0 sm:top-16 z-[60] flex items-center justify-center p-4 sm:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
          <div className="absolute inset-0 bg-black/45 backdrop-blur-sm" onClick={() => !busy && onClose()} aria-hidden />
          <motion.div
            role="dialog"
            aria-modal="true"
            initial={{ opacity: 0, scale: 0.94, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ type: 'spring', stiffness: 320, damping: 30 }}
            className="relative w-full max-w-lg sm:max-w-3xl max-h-[90vh] flex flex-col rounded-2xl bg-bg shadow-elevated overflow-hidden"
          >
            <header className="flex items-center justify-between gap-3 px-5 py-3.5 hairline-b shrink-0">
              <div className="text-headline text-label">Edit creative {index + 1}</div>
              <button
                onClick={() => !busy && onClose()}
                aria-label="Close"
                className="grid place-items-center h-9 w-9 -mr-1.5 rounded-full text-label-secondary hover:bg-fill-quaternary focus-ring shrink-0"
              >
                <X size={18} />
              </button>
            </header>

            <div className="flex-1 min-h-0 flex flex-col md:flex-row">
              {/* Left — version history */}
              <div className="md:w-[260px] shrink-0 overflow-y-auto px-4 py-4 border-b md:border-b-0 md:border-r border-separator bg-bg-secondary">
                <p className="text-footnote font-semibold text-label flex items-center gap-1.5 mb-2">
                  <History size={14} className="text-label-secondary" /> Version history
                </p>
                {versions === null ? (
                  <div className="flex justify-center py-4">
                    <span className="h-5 w-5 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading" />
                  </div>
                ) : versions.length === 0 ? (
                  <p className="text-caption text-label-tertiary">No versions yet.</p>
                ) : (
                  <div className="space-y-2">
                    {[...versions].reverse().map((v) => {
                      const activePreview = previewId ? previewId === v.id : v.is_active;
                      return (
                        <button
                          key={v.id}
                          onClick={() => setPreviewId(v.id)}
                          className={`w-full text-left rounded-md border p-2.5 focus-ring transition-colors ${activePreview ? 'border-accent bg-bg ring-1 ring-accent' : 'border-separator bg-bg hover:border-label-tertiary'}`}
                        >
                          <p className="text-footnote font-semibold text-label flex items-center gap-1.5">
                            {v.label}
                            {v.is_active && (
                              <span className="text-caption2 font-semibold text-success inline-flex items-center gap-0.5">
                                <Check size={11} /> Live
                              </span>
                            )}
                          </p>
                          <p className="text-caption2 text-label-tertiary mt-0.5">
                            {v.editor_name ?? 'Copy Agent'} · {timeAgo(v.created_at)}
                          </p>
                          <p className="text-caption text-label-secondary line-clamp-2 mt-0.5">{v.headline}</p>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Right — preview a selected version, or edit the live copy */}
              <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-3">
                {preview ? (
                  <>
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <p className="text-footnote font-semibold text-label-secondary inline-flex items-center gap-1.5">
                        <Eye size={14} /> Previewing · {preview.label}
                        {preview.is_active && <span className="text-success">(live)</span>}
                      </p>
                      <div className="flex items-center gap-2">
                        <Button variant="plain" size="sm" onClick={() => setPreviewId(null)}>
                          <Pencil size={13} /> Back to editing
                        </Button>
                        {!preview.is_active && (
                          <Button size="sm" onClick={() => select(preview.id)} disabled={busy}>
                            <RotateCcw size={13} /> {busy ? 'Applying…' : 'Use this version'}
                          </Button>
                        )}
                      </div>
                    </div>
                    <CreativeCard c={preview} index={index} />
                  </>
                ) : (
                  <>
                    <CreativeCard c={draft} index={index} editing onChange={(p) => setDraft((d) => ({ ...d, ...p }))} />
                    {error && (
                      <p className="flex items-center gap-1.5 text-footnote text-error" role="alert">
                        <AlertCircle size={14} className="shrink-0" /> {error}
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>

            <footer className="px-5 py-3.5 hairline-t shrink-0 glass flex justify-end gap-2">
              <Button variant="plain" onClick={() => !busy && onClose()} disabled={busy}>Close</Button>
              <Button onClick={save} disabled={busy || !!preview} title={preview ? 'Close the preview to edit' : undefined}>
                <Check size={16} /> {busy ? 'Saving…' : 'Save as new version'}
              </Button>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
