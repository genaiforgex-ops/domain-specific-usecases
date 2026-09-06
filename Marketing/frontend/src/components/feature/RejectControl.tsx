import { useState } from 'react';
import { MessageSquareWarning, AlertCircle } from 'lucide-react';
import { Area } from '../ui/primitives';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { api, ApiError } from '../../lib/api';
import { useApp } from '../../state/AppContext';
import type { Brief } from '../../lib/types';

type ButtonSize = 'sm' | 'md' | 'lg';

// The reject action for a work-stage owner — the Copywriter or Designer sending
// the brief back a step for changes. Renders a top-level button that opens a
// popup; the server derives where it lands from the brief's stage (Copywriter →
// author, Designer → Copywriter). The reason is required and travels to whoever
// it bounces back to.
export function RejectControl({
  brief,
  onChanged,
  title,
  description,
  placeholder,
  confirmLabel,
  triggerLabel,
  size = 'md',
}: Readonly<{
  brief: Brief;
  onChanged: (b: Brief) => void;
  /** Popup heading, e.g. "Send this brief back". */
  title: string;
  /** One-line explanation of where it goes and why. */
  description: string;
  /** Note textarea placeholder. */
  placeholder: string;
  /** The confirm button label, e.g. "Send back to Copywriter". */
  confirmLabel: string;
  /** The trigger button label — defaults to the confirm label. */
  triggerLabel?: string;
  /** Trigger-button size (defaults to md). */
  size?: ButtonSize;
}>) {
  const { toast } = useApp();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setOpen(false);
    setNote('');
    setError(null);
  };

  const submit = async () => {
    if (!note.trim()) {
      setError('Add a note explaining what needs to change.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api.rejectBrief(brief.id, note.trim());
      toast('Sent back for changes', 'success');
      reset();
      onChanged(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not send the brief back.');
      setBusy(false);
    }
  };

  return (
    <>
      <Button variant="glass" size={size} onClick={() => setOpen(true)}>
        <MessageSquareWarning size={16} className="text-warning" /> {triggerLabel ?? confirmLabel}
      </Button>

      <Modal
        open={open}
        onClose={reset}
        size="sm"
        title={
          <span className="flex items-center gap-2">
            <MessageSquareWarning size={17} className="text-warning shrink-0" /> {title}
          </span>
        }
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="plain" onClick={reset} disabled={busy}>Cancel</Button>
            <Button variant="destructive" onClick={submit} disabled={busy}>
              <MessageSquareWarning size={16} /> {busy ? 'Sending…' : confirmLabel}
            </Button>
          </div>
        }
      >
        <p className="text-caption text-label-tertiary mb-3">{description}</p>
        <Area
          autoFocus
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={placeholder}
        />
        {error && (
          <p className="flex items-center gap-1.5 text-footnote text-error mt-3" role="alert">
            <AlertCircle size={14} className="shrink-0" /> {error}
          </p>
        )}
      </Modal>
    </>
  );
}
