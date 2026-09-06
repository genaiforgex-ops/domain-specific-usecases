import { useEffect, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { Sparkles, RefreshCw, Send, AlertCircle } from 'lucide-react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { CreativeStudioCard } from './CreativeStudioCard';
import { MagicOverlay, MAGIC_PHRASES } from './MagicOverlay';
import { api, ApiError } from '../../lib/api';
import { useApp } from '../../state/AppContext';
import type { Brief, Creative, CreativeEdit } from '../../lib/types';

const toEdit = (c: Creative): CreativeEdit => ({
  id: c.id,
  headline: c.headline,
  body: c.body,
  cta: c.cta,
  visual_reference: c.visual_reference,
  entity_attribution: c.entity_attribution,
  terms: c.terms,
});

// The Copywriter's focused work surface, opened as a centered dialog from the
// brief — the copy counterpart to the Designer's image workspace. Generate the
// copies, review them, edit each one (every save is a version you can restore),
// then submit for approval. Approvers + Designer auto-route to the admin-set
// defaults, so there's nothing to assign here.
export function CopyStudio({
  open,
  onClose,
  brief,
  creatives,
  onCreatives,
  onSubmitted,
}: Readonly<{
  open: boolean;
  onClose: () => void;
  brief: Brief;
  creatives: Creative[];
  /** Push a fresh copy list up to the page (after generation / edits / on submit). */
  onCreatives: (list: Creative[]) => void;
  /** The brief advanced to approval — the page updates and the dialog closes. */
  onSubmitted: (b: Brief) => void;
}>) {
  const { refreshBriefs, toast } = useApp();

  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const has = creatives.length > 0;

  useEffect(() => {
    if (open) setError(null);
  }, [open]);

  const updateOne = (u: Creative) => onCreatives(creatives.map((c) => (c.id === u.id ? u : c)));

  const generate = async () => {
    setBusy(true);
    setGenerating(true);
    setError(null);
    try {
      onCreatives(await api.generateCreatives(brief.id));
      refreshBriefs();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not generate copies.');
    } finally {
      setBusy(false);
      setGenerating(false);
    }
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      // Copies are already saved (each edit is a version) — submit the current set
      // and advance the brief to approval. Routing is automatic.
      const updated = await api.submitCopies(brief.id, creatives.map(toEdit));
      refreshBriefs();
      toast('Copies submitted for approval', 'success');
      onSubmitted(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not submit the copies.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Copy studio"
      size="lg"
      footer={
        has ? (
          <div className="flex items-center justify-between gap-2">
            <Button variant="tinted" onClick={generate} disabled={busy}>
              <RefreshCw size={16} /> {busy && generating ? 'Working…' : 'Regenerate all'}
            </Button>
            <Button onClick={submit} disabled={busy}>
              <Send size={16} /> {busy && !generating ? 'Saving…' : 'Save & submit for approval'}
            </Button>
          </div>
        ) : undefined
      }
    >
      <div className="relative">
        <AnimatePresence>
          {generating && (
            <MagicOverlay phrases={MAGIC_PHRASES.copy} label="Writing your copies" className="rounded-lg" />
          )}
        </AnimatePresence>

        {error && (
          <p className="flex items-center gap-1.5 text-footnote text-error mb-3" role="alert">
            <AlertCircle size={14} className="shrink-0" /> {error}
          </p>
        )}

        {!has ? (
          <div className="flex flex-col items-center text-center py-10">
            <span className="grid place-items-center h-14 w-14 rounded-full bg-accent/10 text-accent mb-3">
              <Sparkles size={26} />
            </span>
            <p className="text-title-3 font-bold text-label">Draft the copies</p>
            <p className="text-subheadline text-label-secondary mt-1 max-w-sm">
              The Copy Agent writes a set of copies from this brief. Review them, edit any line,
              and route them for approval when they're ready.
            </p>
            <Button size="lg" onClick={generate} disabled={busy} className="mt-5">
              <Sparkles size={18} /> {busy ? 'Generating…' : 'Generate copies'}
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Review + edit each creative (each save is a version you can restore). */}
            <div className="grid sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
              {creatives.map((c, i) => (
                <CreativeStudioCard key={c.id} briefId={brief.id} creative={c} index={i} onUpdated={updateOne} />
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
