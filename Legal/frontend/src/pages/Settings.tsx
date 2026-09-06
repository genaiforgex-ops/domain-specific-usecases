import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ConnectorBrandIcon, GmailConnectorPanel } from "@/components/connectors/GmailConnectorPanel";
import { Icon } from "@/components/Icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { PageHeader } from "@/components/ui/PageHeader";
import { Tabs } from "@/components/ui/Tabs";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import {
  CONNECTOR_CATEGORIES,
  CONNECTORS,
  type ConnectorCategory,
  type ConnectorDefinition,
  type ConnectorId,
} from "@/lib/connectors";
import { classNames } from "@/lib/utils";
import type { GmailSettings, GmailStatus, NotificationSettings } from "@/types";

type SettingsTab = "connectors" | "notifications";

const NOTIFICATION_CATEGORIES: { key: keyof NotificationSettings; label: string; desc: string }[] = [
  { key: "chat_share", label: "Chat shared with me", desc: "LawGenie chat shares" },
  { key: "msa_share", label: "MSA shared with me", desc: "Contract negotiation shares" },
  { key: "task_assigned", label: "Task assigned", desc: "New or reassigned tasks" },
  { key: "approvals", label: "Approvals", desc: "Escalations and answers" },
  { key: "msa_updates", label: "Contract updates", desc: "Vendor docs and executions" },
  { key: "regulatory", label: "Regulatory alerts", desc: "Action-required RBI, SEBI, IRDAI…" },
];

function NotificationPreferences() {
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getNotificationSettings()
      .then(setSettings)
      .catch((e) => setError((e as Error).message));
  }, []);

  async function toggle(key: keyof NotificationSettings) {
    if (!settings) return;
    const next = { ...settings, [key]: !settings[key] };
    setSettings(next);
    setSaving(key);
    setError(null);
    try {
      setSettings(await api.updateNotificationSettings({ [key]: next[key] }));
    } catch (e) {
      setSettings(settings);
      setError((e as Error).message);
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="rounded-lg border border-separator/40 bg-bg shadow-card overflow-hidden">
      <div className="px-4 py-3 border-b border-separator/30 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Icon.Mail className="w-4 h-4 text-accent shrink-0" />
          <div>
            <h2 className="text-sm font-semibold text-label">Email notifications</h2>
            <p className="text-xs text-label-tertiary">Sent to your account email</p>
          </div>
        </div>
        {settings && (
          <Toggle
            label="All emails"
            desc=""
            compact
            checked={settings.email_enabled}
            disabled={saving === "email_enabled"}
            onChange={() => void toggle("email_enabled")}
            emphasize
          />
        )}
      </div>

      {error && <p className="text-sm text-red-500 px-4 pt-3">{error}</p>}

      {!settings ? (
        <p className="text-sm text-label-tertiary px-4 py-6">Loading…</p>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2 p-3">
          {NOTIFICATION_CATEGORIES.map((c) => (
            <div
              key={c.key}
              className="rounded-lg border border-separator/30 bg-bg-secondary/30 px-3 py-2.5"
            >
              <Toggle
                label={c.label}
                desc={c.desc}
                compact
                checked={settings[c.key]}
                disabled={!settings.email_enabled || saving === c.key}
                onChange={() => void toggle(c.key)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Toggle({
  label,
  desc,
  checked,
  disabled,
  onChange,
  emphasize,
  compact,
}: {
  label: string;
  desc: string;
  checked: boolean;
  disabled?: boolean;
  onChange: () => void;
  emphasize?: boolean;
  compact?: boolean;
}) {
  return (
    <label
      className={classNames(
        "flex items-center justify-between gap-3 cursor-pointer",
        compact ? "py-0" : "py-2",
        disabled && "opacity-50 cursor-not-allowed",
      )}
    >
      <span className="min-w-0">
        <span className={classNames("block text-sm text-label", emphasize && "font-semibold")}>{label}</span>
        {desc && <span className="block text-xs text-label-tertiary mt-0.5">{desc}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={onChange}
        className={classNames(
          "relative shrink-0 h-5 w-9 rounded-full transition-colors",
          checked ? "bg-accent" : "bg-separator",
        )}
      >
        <span
          className={classNames(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform",
            checked ? "translate-x-4" : "translate-x-0.5",
          )}
        />
      </button>
    </label>
  );
}

function connectorStatus(
  id: ConnectorId,
  gmail: GmailStatus | null,
): "connected" | "configured" | "coming_soon" | "available" {
  const def = CONNECTORS.find((c) => c.id === id);
  if (!def?.available) return "coming_soon";
  if (id === "gmail") {
    if (gmail?.connected) return "connected";
    if (gmail?.configured) return "available";
    return "available";
  }
  return "coming_soon";
}

export function SettingsPage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<SettingsTab>("connectors");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<ConnectorCategory>("all");
  const [selected, setSelected] = useState<ConnectorId | null>(
    (searchParams.get("connector") as ConnectorId) || null,
  );
  const [gmailStatus, setGmailStatus] = useState<GmailStatus | null>(null);
  const [gmailSettings, setGmailSettings] = useState<GmailSettings | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [gs, gset] = await Promise.all([
      api.gmailStatus().catch(() => null),
      api.gmailSettings().catch(() => null),
    ]);
    setGmailStatus(gs);
    setGmailSettings(gset);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const gmail = searchParams.get("gmail");
    const connector = searchParams.get("connector") as ConnectorId | null;
    if (connector) {
      setSelected(connector);
      setTab("connectors");
    }
    if (gmail === "connected") {
      setConnectError(null);
      setSelected("gmail");
      setTab("connectors");
      setSearchParams({}, { replace: true });
      refresh();
    }
    if (gmail === "error") {
      const reason = searchParams.get("reason");
      setConnectError(
        reason === "code_already_used"
          ? "OAuth code expired — click Connect again."
          : "Connection failed — try Connect again.",
      );
      setSelected("gmail");
      setTab("connectors");
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, refresh, setSearchParams]);

  const visible = useMemo(() => {
    return CONNECTORS.filter((c) => {
      if (!user) return false;
      if (c.permissions && !hasPermission(user, ...c.permissions)) return false;
      if (category !== "all" && c.category !== category) return false;
      if (query.trim()) {
        const q = query.toLowerCase();
        return c.name.toLowerCase().includes(q) || c.description.toLowerCase().includes(q);
      }
      return true;
    });
  }, [user, category, query]);

  const selectedDef = selected ? CONNECTORS.find((c) => c.id === selected) : null;

  const settingsTabs = [
    { id: "connectors", label: "Connectors" },
    { id: "notifications", label: "Notifications" },
  ];

  return (
    <div className="space-y-5 pb-10">
      <PageHeader
        title="Settings"
        subtitle="Connect Gmail and workspace tools, and control which events email you."
      />

      <Tabs tabs={settingsTabs} active={tab} onChange={(id) => setTab(id as SettingsTab)} />

      {tab === "notifications" && <NotificationPreferences />}

      {tab === "connectors" && (
        <div className="relative">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Input
                placeholder="Search connectors…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="flex-1 min-w-[12rem] max-w-md"
              />
              <div className="flex flex-wrap gap-1.5">
                {CONNECTOR_CATEGORIES.map((cat) => (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => setCategory(cat.id)}
                    className={classNames(
                      "text-xs px-2.5 py-1 rounded-full border transition-colors whitespace-nowrap",
                      category === cat.id
                        ? "bg-accent/10 border-accent text-accent"
                        : "border-separator/40 text-label-secondary hover:border-accent/30",
                    )}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-2.5">
              {visible.map((c) => (
                <ConnectorCard
                  key={c.id}
                  connector={c}
                  status={connectorStatus(c.id, gmailStatus)}
                  gmailEmail={c.id === "gmail" ? gmailStatus?.email : null}
                  onOpen={() => setSelected(c.id)}
                />
              ))}
            </div>

            {visible.length === 0 && (
              <p className="text-sm text-label-secondary text-center py-10">No connectors match your search.</p>
            )}
          </div>

          {selectedDef && (
            <ConnectorDetailPanel
              connector={selectedDef}
              gmailStatus={gmailStatus}
              gmailSettings={gmailSettings}
              connectError={connectError}
              onClose={() => setSelected(null)}
              onUpdated={refresh}
            />
          )}
        </div>
      )}
    </div>
  );
}

function ConnectorCard({
  connector,
  status,
  gmailEmail,
  onOpen,
}: {
  connector: ConnectorDefinition;
  status: ReturnType<typeof connectorStatus>;
  gmailEmail: string | null | undefined;
  onOpen: () => void;
}) {
  const isComingSoon = status === "coming_soon";

  return (
    <button
      type="button"
      onClick={() => !isComingSoon && onOpen()}
      disabled={isComingSoon}
      className={classNames(
        "text-left p-3 rounded-lg border border-separator/40 bg-bg transition-all",
        isComingSoon ? "opacity-70 cursor-not-allowed" : "hover:border-accent/30 hover:shadow-card hover:bg-bg-secondary/40",
      )}
    >
      <div className="flex items-center gap-2.5">
        <ConnectorBrandIcon id={connector.id} className="w-8 h-8 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm text-label truncate">{connector.name}</span>
            {isComingSoon && <Badge className="text-[10px] shrink-0">Soon</Badge>}
            {status === "connected" && (
              <span className="text-[10px] text-emerald-700 dark:text-emerald-400 shrink-0">Connected</span>
            )}
          </div>
          {connector.popularity && (
            <div className="text-[11px] text-label-tertiary truncate">{connector.popularity}</div>
          )}
        </div>
      </div>
      <p className="text-xs text-label-secondary mt-2 line-clamp-2 leading-relaxed">{connector.description}</p>
      {status === "connected" && gmailEmail && (
        <div className="mt-1.5 text-[11px] text-label-tertiary truncate">{gmailEmail}</div>
      )}
    </button>
  );
}

function ConnectorDetailPanel({
  connector,
  gmailStatus,
  gmailSettings,
  connectError,
  onClose,
  onUpdated,
}: {
  connector: ConnectorDefinition;
  gmailStatus: GmailStatus | null;
  gmailSettings: GmailSettings | null;
  connectError: string | null;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [closing, setClosing] = useState(false);

  const handleClose = useCallback(() => {
    if (closing) return;
    setClosing(true);
    window.setTimeout(() => onClose(), 280);
  }, [closing, onClose]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") handleClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [handleClose]);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  return (
    <>
      <div
        className={classNames(
          "fixed inset-0 z-40 bg-black/25 backdrop-blur-[1px]",
          closing ? "opacity-0 transition-opacity duration-slow" : "animate-fade-in",
        )}
        onClick={handleClose}
        aria-hidden="true"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${connector.name} settings`}
        className={classNames(
          "fixed inset-y-0 right-0 z-50 flex flex-col bg-bg border-l border-separator/40 shadow-xl w-full max-w-lg",
          closing ? "animate-slide-out-right" : "animate-slide-in-right",
        )}
      >
        <div className="shrink-0 px-4 py-3 border-b border-separator/40 flex items-center gap-3">
          <ConnectorBrandIcon id={connector.id} className="w-8 h-8 shrink-0" />
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-semibold text-label truncate">{connector.name}</h2>
            <p className="text-xs text-label-secondary truncate">{connector.description}</p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            aria-label="Close panel"
            className="shrink-0 w-8 h-8 flex items-center justify-center rounded-md text-label-secondary hover:bg-bg-secondary transition-colors"
          >
            ⟩
          </button>
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4">
          {connector.id === "gmail" && (
            <GmailConnectorPanel
              embedded
              status={gmailStatus}
              settings={gmailSettings}
              connectError={connectError}
              returnTo="settings"
              onUpdated={onUpdated}
            />
          )}

          {connector.id !== "gmail" && (
            <div className="rounded-lg border border-dashed border-separator/50 p-6 text-center">
              <p className="text-sm text-label-secondary">
                {connector.name} integration is on the roadmap. Configure Gmail today; other connectors will appear
                here as they ship.
              </p>
              <Link to="/tasks" className="text-sm text-accent hover:underline mt-3 inline-block">
                Go to Task Manager →
              </Link>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
