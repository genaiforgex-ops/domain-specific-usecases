import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { Icon } from "@/components/Icons";
import { OnlyOfficeEditor } from "@/components/OnlyOfficeEditor";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { classNames } from "@/lib/utils";
import { api } from "@/lib/api";
import type { DocumentVersion, OnlyOfficeConfig } from "@/types";

function isOfficeDoc(version: DocumentVersion): boolean {
  const name = (version.filename || "").toLowerCase();
  const mime = (version.mime_type || "").toLowerCase();
  return name.endsWith(".docx") || name.endsWith(".doc") || mime.includes("word") || mime.includes("docx");
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function MSAOnlyOfficePanel({
  trackerId,
  version,
  mode = "edit",
  canEdit,
  onSaved,
}: {
  trackerId: number;
  version: DocumentVersion;
  mode?: "edit" | "view";
  canEdit: boolean;
  onSaved?: () => void | Promise<void>;
}) {
  const [config, setConfig] = useState<OnlyOfficeConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [versionBaseline, setVersionBaseline] = useState<number | null>(null);
  const [fullscreen, setFullscreen] = useState(false);

  const handleDocumentStateChange = useCallback((modified: boolean) => {
    // With autosave on, OnlyOffice flips this back to false each time it flushes
    // edits to its cache. Keep the button enabled once any edit was made — only
    // reset after a successful save (or when the version reloads).
    if (modified) setDirty(true);
  }, []);

  const handleEditorError = useCallback((msg: string) => {
    setError(msg);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .getMSAOnlyOfficeConfig(trackerId, version.id, canEdit && mode === "edit" ? "edit" : "view")
      .then((c) => {
        if (!cancelled) setConfig(c);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "OnlyOffice unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, [trackerId, version.id, canEdit, mode]);

  useEffect(() => {
    if (mode !== "edit") return;
    setDirty(false);
    let cancelled = false;
    api.listMSAVersions(trackerId).then((versions) => {
      if (!cancelled) setVersionBaseline(versions.length);
    });
    return () => {
      cancelled = true;
    };
  }, [trackerId, version.id, mode]);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullscreen(false);
    };
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    window.setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [fullscreen]);

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      const baseline =
        versionBaseline ?? (await api.listMSAVersions(trackerId)).length;
      await api.saveMSAOnlyOfficeVersion(trackerId, version.id);

      let saved = false;
      for (let attempt = 0; attempt < 30; attempt++) {
        await sleep(1000);
        const versions = await api.listMSAVersions(trackerId);
        if (versions.length > baseline) {
          saved = true;
          break;
        }
      }
      if (!saved) {
        throw new Error(
          "Save timed out. Ensure ONLYOFFICE can reach the backend callback URL, then try again.",
        );
      }

      setDirty(false);
      setVersionBaseline((baseline) => (baseline !== null ? baseline + 1 : null));
      await onSaved?.();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (error) {
    return (
      <Card title="Document editor unavailable">
        <p className="text-sm text-error">{error}</p>
        <p className="text-xs text-label-secondary mt-2">
          Ensure ONLYOFFICE Document Server is running (docker compose service <code>onlyoffice</code>).
        </p>
      </Card>
    );
  }

  if (!config) {
    return (
      <Card title="Loading document editor">
        <p className="text-sm text-label-secondary py-8 text-center">Preparing ONLYOFFICE editor…</p>
      </Card>
    );
  }

  const chrome = (
    <div
      className={classNames(
        "flex items-center justify-between gap-2 flex-wrap flex-shrink-0",
        fullscreen
          ? "px-3 py-2 border-b border-separator/40 bg-bg z-10"
          : "px-4 py-3 border-b border-separator/40 bg-bg",
      )}
    >
      <div className="min-w-0">
        <div className="text-sm font-semibold text-label truncate">
          {mode === "view" ? "Document preview" : "Edit document"}
          <span className="ml-2 font-normal text-label-secondary">
            · v{version.version_number}
            {version.filename ? ` · ${version.filename}` : ""}
          </span>
          {dirty && (
            <span className="ml-2 text-xs text-amber-700 font-medium">Unsaved changes</span>
          )}
        </div>
        {!fullscreen && (
          <p className="text-xs text-label-tertiary mt-0.5">
            {mode === "edit"
              ? "Google Docs–style Word editing — fonts, tables, and track changes stay intact."
              : "High-fidelity DOCX preview with original formatting."}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setFullscreen((v) => !v)}
          title={fullscreen ? "Exit fullscreen (Esc)" : "Fullscreen"}
        >
          {fullscreen ? "Exit fullscreen" : "⛶ Fullscreen"}
        </Button>
        {mode === "edit" && canEdit && (
          <Button size="sm" disabled={saving || !dirty} onClick={handleSave}>
            <Icon.Check className="w-3.5 h-3.5 mr-1" />
            {saving ? "Saving…" : "Save as new version"}
          </Button>
        )}
      </div>
    </div>
  );

  const editor = (
    <OnlyOfficeEditor
      key={`${version.id}-${fullscreen ? "fs" : "inline"}`}
      documentServerUrl={config.document_server_url}
      token={config.token}
      config={config.config}
      mode={mode}
      fitToWidth={fullscreen}
      className="h-full w-full border-0 rounded-none"
      onDocumentStateChange={mode === "edit" ? handleDocumentStateChange : undefined}
      onError={handleEditorError}
    />
  );

  if (fullscreen) {
    return createPortal(
      <div className="fixed inset-0 z-[100] h-[100dvh] w-screen max-w-none m-0 p-0 overflow-hidden bg-bg flex flex-col">
        {chrome}
        {/* Editor sits below chrome so OnlyOffice toolbar is not covered */}
        <div className="relative flex-1 min-h-0 w-full">
          <div className="absolute inset-0 w-full h-full">{editor}</div>
        </div>
        {mode === "edit" && saveError && (
          <p className="flex-shrink-0 px-4 py-2 text-sm text-error bg-bg border-t border-separator/40">
            {saveError}
          </p>
        )}
      </div>,
      document.body,
    );
  }

  return (
    <div
      className={classNames(
        "rounded-2xl border border-separator/40 bg-bg shadow-card overflow-hidden flex flex-col",
        "min-h-[calc(100vh-11rem)]",
      )}
    >
      {chrome}
      <div className="flex-1 min-h-[70vh] relative">
        <div className="absolute inset-0">{editor}</div>
      </div>
      {mode === "edit" && saveError && (
        <p className="px-4 py-2 text-sm text-error border-t border-separator/40">{saveError}</p>
      )}
    </div>
  );
}

export { isOfficeDoc };
