import { useEffect, useState } from "react";

import { GmailLogo, GoogleCalendarLogo, GoogleDriveLogo, Icon } from "@/components/Icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { api } from "@/lib/api";
import { classNames, formatDate } from "@/lib/utils";
import type { GmailSettings, GmailStatus } from "@/types";

export function GmailConnectorPanel({
  status,
  settings,
  connectError,
  returnTo = "settings",
  onUpdated,
  onClose,
  embedded = false,
}: {
  status: GmailStatus | null;
  settings: GmailSettings | null;
  connectError?: string | null;
  returnTo?: string;
  onUpdated: () => void;
  onClose?: () => void;
  embedded?: boolean;
}) {
  const [labels, setLabels] = useState<{ id: string; name: string }[]>([]);
  const [pollEnabled, setPollEnabled] = useState(settings?.poll_enabled ?? false);
  const [autoIngest, setAutoIngest] = useState(settings?.auto_task_ingest ?? false);
  const [selectedLabels, setSelectedLabels] = useState<string[]>(settings?.poll_labels ?? []);
  const [lookbackDays, setLookbackDays] = useState(settings?.poll_lookback_days ?? 7);
  const [newSender, setNewSender] = useState("");
  const [pollNotice, setPollNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status?.connected) {
      api.gmailLabels().then((ls) => setLabels(ls.map((l) => ({ id: l.id, name: l.name })))).catch(() => null);
    }
  }, [status?.connected]);

  useEffect(() => {
    setPollEnabled(settings?.poll_enabled ?? false);
    setAutoIngest(settings?.auto_task_ingest ?? false);
    setSelectedLabels(settings?.poll_labels ?? []);
    setLookbackDays(settings?.poll_lookback_days ?? 7);
  }, [settings]);

  async function connect() {
    const { authorization_url } = await api.gmailOAuthStart(returnTo);
    window.location.href = authorization_url;
  }

  async function saveSettings() {
    setBusy(true);
    setError(null);
    try {
      await api.updateGmailSettings({
        poll_enabled: pollEnabled,
        auto_task_ingest: autoIngest,
        poll_labels: selectedLabels,
        poll_lookback_days: lookbackDays,
      });
      onUpdated();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function pollNow() {
    setBusy(true);
    setPollNotice(null);
    try {
      const result = await api.pollGmail(true);
      const base = `Scanned ${result.messages_scanned} email(s), created ${result.tasks_created} task(s), skipped ${result.skipped}`;
      setPollNotice(result.hint ? `${base}. ${result.hint}` : base);
      onUpdated();
    } finally {
      setBusy(false);
    }
  }

  async function addSender() {
    const email = newSender.trim();
    if (!email) return;
    setBusy(true);
    try {
      await api.watchGmailSender(email);
      setNewSender("");
      onUpdated();
    } finally {
      setBusy(false);
    }
  }

  async function removeSender(email: string) {
    setBusy(true);
    try {
      await api.unwatchGmailSender(email);
      onUpdated();
    } finally {
      setBusy(false);
    }
  }

  function toggleLabel(name: string) {
    setSelectedLabels((prev) =>
      prev.includes(name) ? prev.filter((l) => l !== name) : [...prev, name],
    );
  }

  const body = (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        {status?.connected ? (
          <Badge className="bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200">
            Connected · {status.email}
          </Badge>
        ) : status?.configured ? (
          <Button size="sm" onClick={connect}>
            Connect Gmail
          </Button>
        ) : (
          <span className="text-sm text-label-secondary">
            Server Gmail OAuth not configured — set GMAIL_CLIENT_ID/SECRET in .env.
          </span>
        )}
        {status?.connected && (
          <Button variant="secondary" size="sm" onClick={pollNow} disabled={busy}>
            Poll now
          </Button>
        )}
        {settings?.last_poll_at && (
          <span className="text-xs text-label-tertiary">Last poll: {formatDate(settings.last_poll_at)}</span>
        )}
      </div>
      {pollNotice && <p className="text-sm text-emerald-700">{pollNotice}</p>}

      {status?.connected && (
        <>
          <div className="w-48">
            <Select label="Poll lookback" value={String(lookbackDays)} onChange={(e) => setLookbackDays(Number(e.target.value))}>
              <option value="7">Last 7 days</option>
              <option value="14">Last 14 days</option>
              <option value="30">Last 30 days</option>
            </Select>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={pollEnabled} onChange={(e) => setPollEnabled(e.target.checked)} />
              Enable background polling
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={autoIngest} onChange={(e) => setAutoIngest(e.target.checked)} />
              Auto-create tasks from new mail
            </label>
          </div>

          <div>
            <div className="text-sm font-medium text-label mb-2">Labels to watch</div>
            <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
              {labels.map((l) => (
                <button
                  key={l.id}
                  type="button"
                  onClick={() => toggleLabel(l.name)}
                  className={classNames(
                    "text-xs px-2 py-1 rounded border",
                    selectedLabels.includes(l.name)
                      ? "bg-accent/10 border-accent text-accent"
                      : "bg-bg-secondary border-separator/40",
                  )}
                >
                  {l.name}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="text-sm font-medium text-label mb-2">Watched senders</div>
            <div className="flex gap-2 mb-2">
              <Input
                value={newSender}
                onChange={(e) => setNewSender(e.target.value)}
                placeholder="vendor@example.com"
              />
              <Button size="sm" variant="secondary" onClick={addSender} disabled={busy || !newSender.trim()}>
                Add
              </Button>
            </div>
            <ul className="space-y-1">
              {(settings?.watched_senders ?? []).map((s) => (
                <li key={s} className="flex items-center justify-between text-sm p-1 rounded bg-bg-secondary">
                  <span>{s}</span>
                  <Button size="sm" variant="secondary" onClick={() => removeSender(s)} disabled={busy}>
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
            {(settings?.watched_threads?.length ?? 0) > 0 && (
              <p className="text-xs text-label-tertiary mt-2">
                {settings?.watched_threads.length} watched thread(s) — manage from Task Manager mailbox.
              </p>
            )}
          </div>

          <Button size="sm" onClick={saveSettings} disabled={busy}>
            Save settings
          </Button>

          <p className="text-xs text-label-tertiary border-t border-separator/30 pt-4">
            Browse messages, ingest tasks, and compose replies from Task Manager.
          </p>
        </>
      )}
      {error && <p className="text-sm text-error">{error}</p>}
      {connectError && <p className="text-sm text-error">{connectError}</p>}
    </div>
  );

  if (embedded) return body;

  return (
    <Card
      className="animate-slide-up"
      title={
        <div className="flex items-center gap-2">
          <GmailLogo className="w-5 h-5" />
          <span>Gmail</span>
        </div>
      }
      subtitle="Connect Gmail and configure label polling for Task Manager."
      actions={
        onClose ? (
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        ) : undefined
      }
    >
      {body}
    </Card>
  );
}

export function ConnectorBrandIcon({ id, className }: { id: string; className?: string }) {
  const cn = className ?? "w-8 h-8";
  switch (id) {
    case "gmail":
      return <GmailLogo className={cn} />;
    case "google_drive":
      return <GoogleDriveLogo className={cn} />;
    case "google_calendar":
      return <GoogleCalendarLogo className={cn} />;
    default:
      return <Icon.Plug className={cn} />;
  }
}
