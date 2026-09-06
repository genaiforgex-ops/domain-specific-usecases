import { useRef, useState, type DragEvent } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Sparkles, Wand2, Upload, Loader2, AlertCircle } from 'lucide-react';
import { api, ApiError } from '../../lib/api';
import type { BriefForm, BriefSize } from '../../lib/types';
import { cn } from '../../lib/cn';
import { MagicOverlay, MAGIC_PHRASES } from './MagicOverlay';

// The Brief Creator Agent input — paste or drop raw notes and it drafts the
// form. A gradient shell signals "this is the magic part" while staying inside
// the design tokens (accent → violet → blue). On success the parent reveals the
// filled form for review, so this card shows only what's needed to draft.
export function AiBriefFiller({
  size,
  onFilled,
}: {
  size: BriefSize;
  onFilled: (values: BriefForm, model: string, count: number) => void;
}) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const ingestFile = (f?: File) => {
    if (!f) return;
    f.text().then((t) => setText((prev) => (prev ? `${prev}\n${t}` : t)));
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    ingestFile(e.dataTransfer.files?.[0]);
  };

  const generate = async () => {
    if (!text.trim()) {
      setError('Paste or drop some notes first.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api.extractBrief(size, text);
      onFilled(res.values, res.model_version, Object.keys(res.values).length);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The agent could not draft this.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative rounded-2xl p-[1.5px] overflow-hidden" style={{ background: 'linear-gradient(120deg, var(--color-accent), #af52de, #0a84ff)' }}>
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-30"
        style={{ background: 'linear-gradient(120deg, transparent 30%, rgba(255,255,255,0.6), transparent 70%)' }}
        animate={{ x: ['-120%', '120%'] }}
        transition={{ duration: 3.5, repeat: Infinity, ease: 'linear' }}
      />

      <AnimatePresence>
        {busy && <MagicOverlay phrases={MAGIC_PHRASES.brief} label="Drafting your brief" />}
      </AnimatePresence>

      <div className="relative rounded-2xl bg-bg-tertiary p-5">
        <div className="flex items-center gap-3 mb-4">
          <span className="grid place-items-center h-10 w-10 rounded-xl text-white shrink-0" style={{ background: 'linear-gradient(135deg, var(--color-accent), #af52de)' }}>
            <Sparkles size={20} />
          </span>
          <div className="min-w-0">
            <p className="text-headline text-label">Brief Creator Agent</p>
            <p className="text-caption text-label-secondary">Paste your raw notes — the agent extracts only what's there, you review the rest.</p>
          </div>
        </div>

        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn('rounded-xl border-2 border-dashed transition-colors', dragging ? 'border-accent bg-[color:var(--color-accent-soft)]' : 'border-separator')}
        >
          <textarea
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={'Paste anything — an email, meeting notes, a Slack thread, a rough outline…'}
            className="w-full min-h-[180px] p-4 bg-transparent text-body text-label placeholder:text-label-tertiary resize-y focus:outline-none"
          />
        </div>

        <input ref={fileRef} type="file" accept=".txt,.md,text/plain" className="hidden" onChange={(e) => ingestFile(e.target.files?.[0] ?? undefined)} />

        {error && (
          <p className="flex items-center gap-1.5 text-footnote text-error mt-3" role="alert">
            <AlertCircle size={14} className="shrink-0" /> {error}
          </p>
        )}

        <div className="flex items-center gap-2 mt-3">
          <button
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="inline-flex items-center gap-1.5 h-9 px-3 rounded-full text-footnote font-semibold text-label-secondary hover:bg-[color:var(--color-fill-quaternary)] focus-ring disabled:opacity-40"
          >
            <Upload size={15} /> Upload .txt
          </button>
          {text && (
            <button onClick={() => setText('')} disabled={busy} className="text-footnote text-label-tertiary hover:text-label-secondary focus-ring rounded px-1 disabled:opacity-40">
              Clear
            </button>
          )}
          <span className="flex-1" />
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={generate}
            disabled={busy}
            className="inline-flex items-center justify-center gap-2 h-11 px-5 rounded-full font-semibold text-white focus-ring disabled:opacity-60"
            style={{ background: 'linear-gradient(135deg, var(--color-accent), #af52de)' }}
          >
            {busy ? (<><Loader2 size={17} className="animate-spin" /> Drafting…</>) : (<><Wand2 size={17} /> Generate brief</>)}
          </motion.button>
        </div>
      </div>
    </div>
  );
}
