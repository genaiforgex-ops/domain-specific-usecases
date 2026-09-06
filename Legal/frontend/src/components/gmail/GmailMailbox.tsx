import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { GmailLogo } from "@/components/Icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { api } from "@/lib/api";
import { classNames, formatDate } from "@/lib/utils";
import type { GmailMessage, GmailMessageSummary, GmailSettings, GmailStatus, GmailThread } from "@/types";

function extractEmail(fromAddr: string): string {
  const m = fromAddr.match(/<([^>]+)>/);
  return (m?.[1] ?? fromAddr).trim().toLowerCase();
}

export function GmailMailbox({
  status,
  settings,
  onSettingsUpdated,
  onTasksUpdated,
  onReply,
  onClose,
}: {
  status: GmailStatus | null;
  settings: GmailSettings | null;
  onSettingsUpdated: () => void;
  onTasksUpdated: () => void;
  onReply: (threadId: string, messageId: string) => void;
  onClose?: () => void;
}) {
  const [labels, setLabels] = useState<{ id: string; name: string }[]>([]);
  const [labelFilter, setLabelFilter] = useState(settings?.poll_labels?.[0] ?? "");
  const [senderFilter, setSenderFilter] = useState("");
  const [lookbackDays, setLookbackDays] = useState(settings?.poll_lookback_days ?? 7);
  const [watchedOnly, setWatchedOnly] = useState(false);
  const [messages, setMessages] = useState<GmailMessageSummary[]>([]);
  const [nextPageToken, setNextPageToken] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedMessage, setSelectedMessage] = useState<GmailMessage | null>(null);
  const [thread, setThread] = useState<GmailThread | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const watchedThreadIds = useMemo(
    () => new Set((settings?.watched_threads ?? []).map((w) => w.thread_id)),
    [settings?.watched_threads],
  );
  const watchedSenders = useMemo(
    () => new Set((settings?.watched_senders ?? []).map((s) => s.toLowerCase())),
    [settings?.watched_senders],
  );

  const isWatched = useCallback(
    (m: GmailMessageSummary) =>
      watchedThreadIds.has(m.thread_id) || watchedSenders.has(extractEmail(m.from_addr)),
    [watchedThreadIds, watchedSenders],
  );

  const visibleMessages = useMemo(
    () => (watchedOnly ? messages.filter(isWatched) : messages),
    [messages, watchedOnly, isWatched],
  );

  useEffect(() => {
    if (status?.connected) {
      api.gmailLabels().then((ls) => setLabels(ls.map((l) => ({ id: l.id, name: l.name })))).catch(() => null);
    }
  }, [status?.connected]);

  useEffect(() => {
    if (settings?.poll_lookback_days) setLookbackDays(settings.poll_lookback_days);
  }, [settings?.poll_lookback_days]);

  const loadMessages = useCallback(
    async (append = false) => {
      if (!status?.connected) return;
      setBusy(true);
      setError(null);
      try {
        const result = await api.gmailMessages({
          label: labelFilter || undefined,
          from_addr: senderFilter.trim() || undefined,
          newer_than_days: lookbackDays,
          max_results: 30,
          page_token: append ? nextPageToken ?? undefined : undefined,
        });
        setMessages((prev) => (append ? [...prev, ...result.messages] : result.messages));
        setNextPageToken(result.next_page_token);
        if (!append) {
          setSelectedId(null);
          setSelectedMessage(null);
          setThread(null);
        }
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [status?.connected, labelFilter, senderFilter, lookbackDays, nextPageToken],
  );

  useEffect(() => {
    if (status?.connected) loadMessages(false);
  }, [status?.connected, labelFilter, senderFilter, lookbackDays]); // eslint-disable-line react-hooks/exhaustive-deps

  async function selectMessage(m: GmailMessageSummary) {
    setSelectedId(m.id);
    setBusy(true);
    setError(null);
    try {
      const [full, th] = await Promise.all([
        api.gmailMessage(m.id),
        api.gmailThread(m.thread_id),
      ]);
      setSelectedMessage(full);
      setThread(th);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function pollNow() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.pollGmail(true);
      const base = `Scanned ${result.messages_scanned} email(s) (${lookbackDays}d) — created ${result.tasks_created} task(s), skipped ${result.skipped}`;
      setNotice(result.hint ? `${base}. ${result.hint}` : base);
      onTasksUpdated();
      onSettingsUpdated();
      await loadMessages(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function ingestMessage(id: string) {
    setBusy(true);
    try {
      const result = await api.ingestGmailMessageTasks(id);
      setNotice(
        result.count > 0
          ? `Created ${result.count} task(s)`
          : `No tasks created (${result.reason ?? "no action"})`,
      );
      onTasksUpdated();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleWatchThread() {
    if (!selectedMessage || !thread) return;
    setBusy(true);
    try {
      if (watchedThreadIds.has(thread.id)) {
        await api.unwatchGmailThread(thread.id);
        setNotice("Thread unwatched");
      } else {
        await api.watchGmailThread({
          thread_id: thread.id,
          subject: selectedMessage.subject,
          from_addr: selectedMessage.from_addr,
        });
        setNotice("Thread watched — new messages will be polled with full context");
      }
      onSettingsUpdated();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleWatchSender() {
    if (!selectedMessage) return;
    const email = extractEmail(selectedMessage.from_addr);
    if (!email) return;
    setBusy(true);
    try {
      if (watchedSenders.has(email)) {
        await api.unwatchGmailSender(email);
        setNotice("Sender unwatched");
      } else {
        await api.watchGmailSender(email);
        setNotice("Sender watched — future mail will be polled with context");
      }
      onSettingsUpdated();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!status?.connected) {
    return (
      <Card
        title={
          <div className="flex items-center gap-2">
            <GmailLogo className="w-5 h-5" />
            <span>Gmail mailbox</span>
          </div>
        }
        actions={onClose ? <Button variant="secondary" size="sm" onClick={onClose}>Close</Button> : undefined}
      >
        <p className="text-sm text-label-secondary mb-3">Connect Gmail to browse and reply.</p>
        <Link to="/settings?connector=gmail"><Button size="sm">Connect in Settings</Button></Link>
      </Card>
    );
  }

  const senderEmail = selectedMessage ? extractEmail(selectedMessage.from_addr) : "";
  const threadWatched = thread ? watchedThreadIds.has(thread.id) : false;
  const senderWatched = senderEmail ? watchedSenders.has(senderEmail) : false;

  return (
    <Card
      className="animate-slide-up"
      title={
        <div className="flex items-center gap-2">
          <GmailLogo className="w-5 h-5" />
          <span>Gmail mailbox</span>
          <Badge className="bg-emerald-50 text-emerald-800 border-emerald-200 text-[10px]">{status.email}</Badge>
        </div>
      }
      subtitle="Browse mail from the last week, watch threads/senders, ingest tasks, and reply."
      actions={
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={pollNow} disabled={busy}>Poll now</Button>
          {onClose && <Button variant="secondary" size="sm" onClick={onClose}>Close</Button>}
        </div>
      }
    >
      <div className="grid lg:grid-cols-5 gap-4 min-h-[480px]">
        <div className="lg:col-span-2 flex flex-col gap-3 border-r border-separator/30 pr-0 lg:pr-4">
          <div className="grid grid-cols-2 gap-2">
            <Select label="Label" value={labelFilter} onChange={(e) => setLabelFilter(e.target.value)}>
              <option value="">All mail</option>
              {labels.map((l) => (
                <option key={l.id} value={l.name}>{l.name}</option>
              ))}
            </Select>
            <Select label="Period" value={String(lookbackDays)} onChange={(e) => setLookbackDays(Number(e.target.value))}>
              <option value="7">Last 7 days</option>
              <option value="14">Last 14 days</option>
              <option value="30">Last 30 days</option>
            </Select>
          </div>
          <Input
            label="From (sender filter)"
            value={senderFilter}
            onChange={(e) => setSenderFilter(e.target.value)}
            placeholder="email@company.com"
          />
          <label className="flex items-center gap-2 text-xs text-label-secondary">
            <input type="checkbox" checked={watchedOnly} onChange={(e) => setWatchedOnly(e.target.checked)} />
            Watched only
          </label>
          {notice && <p className="text-xs text-emerald-700">{notice}</p>}
          {error && <p className="text-xs text-error">{error}</p>}
          <ul className="flex-1 overflow-y-auto space-y-1 max-h-[420px] border border-separator/30 rounded-lg">
            {visibleMessages.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => selectMessage(m)}
                  className={classNames(
                    "w-full text-left p-2 text-sm border-b border-separator/20 hover:bg-bg-secondary transition-colors",
                    selectedId === m.id && "bg-accent/10",
                  )}
                >
                  <div className="flex items-center gap-1">
                    <span className="font-medium truncate flex-1">{m.subject || "(no subject)"}</span>
                    {isWatched(m) && (
                      <Badge className="text-[9px] bg-violet-50 text-violet-700 border-violet-100 shrink-0">Watched</Badge>
                    )}
                  </div>
                  <div className="text-xs text-label-secondary truncate">{m.from_addr}</div>
                  {m.date && <div className="text-[10px] text-label-tertiary">{formatDate(m.date)}</div>}
                </button>
              </li>
            ))}
            {visibleMessages.length === 0 && (
              <li className="p-6 text-center text-sm text-label-secondary">No messages in this period.</li>
            )}
          </ul>
          {nextPageToken && (
            <Button variant="secondary" size="sm" onClick={() => loadMessages(true)} disabled={busy}>
              Load more
            </Button>
          )}
        </div>

        <div className="lg:col-span-3 flex flex-col min-h-0">
          {!selectedMessage ? (
            <div className="flex-1 flex items-center justify-center text-sm text-label-secondary">
              Select a message to read the full email and thread.
            </div>
          ) : (
            <>
              <div className="border-b border-separator/30 pb-3 mb-3">
                <h3 className="text-base font-semibold text-label">{selectedMessage.subject}</h3>
                <div className="text-sm text-label-secondary mt-1">{selectedMessage.from_addr}</div>
                {selectedMessage.date && (
                  <div className="text-xs text-label-tertiary mt-0.5">{formatDate(selectedMessage.date)}</div>
                )}
                <div className="flex flex-wrap gap-2 mt-3">
                  <Button size="sm" variant="secondary" onClick={() => ingestMessage(selectedMessage.id)} disabled={busy}>
                    Ingest tasks
                  </Button>
                  <Button size="sm" onClick={() => onReply(selectedMessage.thread_id, selectedMessage.id)} disabled={busy}>
                    Reply
                  </Button>
                  <Button size="sm" variant="secondary" onClick={toggleWatchThread} disabled={busy}>
                    {threadWatched ? "Unwatch thread" : "Watch thread"}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={toggleWatchSender} disabled={busy}>
                    {senderWatched ? "Unwatch sender" : "Watch sender"}
                  </Button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto space-y-4">
                <div className="rounded-lg border border-separator/30 bg-bg-secondary p-4">
                  <div className="text-xs font-medium text-label-secondary mb-2">Message</div>
                  <pre className="text-sm whitespace-pre-wrap font-sans text-label">{selectedMessage.body}</pre>
                </div>
                {thread && thread.messages.length > 1 && (
                  <div>
                    <div className="text-xs font-medium text-label-secondary mb-2">
                      Thread ({thread.messages.length} messages)
                    </div>
                    <ul className="space-y-2 max-h-64 overflow-y-auto">
                      {thread.messages.map((tm) => (
                        <li
                          key={tm.id}
                          className={classNames(
                            "p-2 rounded border text-xs",
                            tm.id === selectedMessage.id ? "border-accent/40 bg-accent/5" : "border-separator/30",
                          )}
                        >
                          <div className="text-label-secondary">{tm.from_addr}</div>
                          <pre className="mt-1 whitespace-pre-wrap font-sans text-label-secondary max-h-32 overflow-y-auto">
                            {tm.body}
                          </pre>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </Card>
  );
}
