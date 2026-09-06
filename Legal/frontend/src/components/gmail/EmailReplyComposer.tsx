import { useEffect, useState } from "react";

import { GmailLogo } from "@/components/Icons";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import type { EmailDraft, GmailThread } from "@/types";

export function EmailReplyComposer({
  threadId,
  messageId,
  draftId,
  onClose,
  onSent,
}: {
  threadId: string;
  messageId: string;
  draftId?: number;
  onClose: () => void;
  onSent?: () => void;
}) {
  const { user } = useAuth();
  const canSend = hasPermission(user, "send_email");
  const [thread, setThread] = useState<GmailThread | null>(null);
  const [draft, setDraft] = useState<EmailDraft | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setBusy(true);
      setError(null);
      try {
        const [th, d] = await Promise.all([
          api.gmailThread(threadId),
          // Load the existing (e.g. auto-generated) draft when given one, else
          // generate a fresh draft for this message.
          draftId
            ? api.getEmailDraft(draftId)
            : api.createEmailDraft({
                gmail_thread_id: threadId,
                gmail_message_id: messageId,
              }),
        ]);
        if (cancelled) return;
        setThread(th);
        setDraft(d);
        setSubject(d.draft_subject);
        setBody(d.draft_body);
        setFeedback(d.user_feedback ?? "");
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [threadId, messageId, draftId]);

  async function saveDraft() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.updateEmailDraft(draft.id, {
        draft_subject: subject,
        draft_body: body,
        user_feedback: feedback || undefined,
      });
      setDraft(updated);
      setStatus("Draft saved");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function regenerate() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      if (feedback !== (draft.user_feedback ?? "")) {
        await api.updateEmailDraft(draft.id, { user_feedback: feedback || undefined });
      }
      const updated = await api.regenerateEmailDraft(draft.id);
      setDraft(updated);
      setSubject(updated.draft_subject);
      setBody(updated.draft_body);
      setStatus("Reply regenerated");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function approveReply() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      // Persist any edits first (this downgrades status to user_edited), then approve.
      await api.updateEmailDraft(draft.id, {
        draft_subject: subject,
        draft_body: body,
        user_feedback: feedback || undefined,
      });
      const approved = await api.approveEmailDraft(draft.id, 0);
      setDraft(approved);
      setSubject(approved.draft_subject);
      setBody(approved.draft_body);
      setStatus("Approved — ready to send");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function sendReply() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const sent = await api.sendEmailDraft(draft.id);
      setDraft(sent);
      setStatus("Email sent");
      onSent?.();
      setTimeout(onClose, 800);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // Send is only allowed once the shown text has been approved with no later edits.
  const isApproved =
    draft?.status === "approved" &&
    subject === draft.draft_subject &&
    body === draft.draft_body;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        className="bg-bg rounded-xl shadow-xl border border-separator/40 max-w-3xl w-full max-h-[90vh] flex flex-col"
        role="dialog"
        aria-labelledby="reply-composer-title"
      >
        <div className="flex items-center justify-between gap-3 p-4 border-b border-separator/30 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <GmailLogo className="w-5 h-5 shrink-0" />
            <h2 id="reply-composer-title" className="text-lg font-semibold text-label truncate">
              Compose reply
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-md text-label-secondary hover:bg-bg-secondary text-lg leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="overflow-y-auto flex-1 p-4 space-y-4">
          {busy && !draft && (
            <p className="text-sm text-label-secondary">Generating AI draft from thread…</p>
          )}
          {error && <p className="text-sm text-error">{error}</p>}
          {status && <p className="text-sm text-emerald-700">{status}</p>}

          {thread && (
            <details className="rounded-lg border border-separator/30 bg-bg-secondary p-3">
              <summary className="cursor-pointer text-sm font-medium text-label">
                Thread ({thread.messages.length} message{thread.messages.length === 1 ? "" : "s"})
              </summary>
              <ul className="mt-3 space-y-3 max-h-48 overflow-y-auto">
                {thread.messages.map((m) => (
                  <li
                    key={m.id}
                    className={m.id === messageId ? "ring-1 ring-accent/40 rounded p-2" : "p-2"}
                  >
                    <div className="text-xs text-label-secondary">
                      {m.from_addr}
                      {m.date ? ` · ${new Date(m.date).toLocaleString()}` : ""}
                    </div>
                    <div className="text-sm font-medium text-label">{m.subject}</div>
                    <pre className="mt-1 text-xs whitespace-pre-wrap text-label-secondary font-sans">
                      {m.body.slice(0, 1200)}
                      {m.body.length > 1200 ? "…" : ""}
                    </pre>
                  </li>
                ))}
              </ul>
            </details>
          )}

          {draft && (
            <>
              <Input label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
              <Textarea
                label="Reply body"
                rows={10}
                value={body}
                onChange={(e) => setBody(e.target.value)}
              />
              <Textarea
                label="Instructions for AI (optional)"
                rows={2}
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="e.g. Decline the liability cap increase; propose 2x annual fees instead."
              />
              {draft.model_version && (
                <p className="text-xs text-label-tertiary">Model: {draft.model_version}</p>
              )}
            </>
          )}
        </div>

        <div className="flex flex-wrap justify-end gap-2 p-4 border-t border-separator/30 shrink-0">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          {draft && (
            <>
              <Button variant="secondary" onClick={saveDraft} disabled={busy}>
                {busy ? "Saving…" : "Save"}
              </Button>
              <Button variant="secondary" onClick={regenerate} disabled={busy}>
                {busy ? "Working…" : "Regenerate"}
              </Button>
              <Button
                variant="secondary"
                onClick={approveReply}
                disabled={busy || !body.trim() || isApproved}
              >
                {isApproved ? "Approved ✓" : busy ? "Working…" : "Approve"}
              </Button>
              {canSend ? (
                <Button onClick={sendReply} disabled={busy || !isApproved}>
                  {busy ? "Sending…" : "Send"}
                </Button>
              ) : (
                <span className="text-xs text-label-tertiary self-center px-2">
                  Send requires send_email permission
                </span>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
