import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { DiffView } from "@/components/DiffView";
import { Icon } from "@/components/Icons";
import { Button } from "@/components/ui/Button";
import { classNames, lineDiffBlocks } from "@/lib/utils";
import type { DocumentVersion } from "@/types";

function htmlToPlainText(html: string): string {
  const div = document.createElement("div");
  div.innerHTML = html;
  return (div.innerText || div.textContent || "").replace(/\u00a0/g, " ");
}

function plainToHtml(text: string): string {
  return text
    .split("\n")
    .map((line) => (line.trim() ? `<p>${escapeHtml(line)}</p>` : "<p><br></p>"))
    .join("");
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function MSADocumentEditor({
  version,
  initialText,
  canSave,
  disabled,
  onSave,
}: {
  version: DocumentVersion;
  initialText: string;
  canSave: boolean;
  disabled?: boolean;
  onSave: (editedText: string, richHtml: string) => Promise<void>;
}) {
  const editorRef = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<"rich" | "plain">("rich");
  const [plainText, setPlainText] = useState(initialText);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    setPlainText(initialText);
    setDirty(false);
    if (editorRef.current) {
      editorRef.current.innerHTML = plainToHtml(initialText);
    }
  }, [initialText, version.id]);

  useEffect(() => {
    if (mode === "rich" && editorRef.current && !dirty) {
      editorRef.current.innerHTML = plainToHtml(plainText);
    }
  }, [mode, plainText, dirty]);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullscreen(false);
    };
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [fullscreen]);

  const exec = useCallback((command: string, value?: string) => {
    document.execCommand(command, false, value);
    editorRef.current?.focus();
    setDirty(true);
  }, []);

  function currentRichHtml(): string {
    return editorRef.current?.innerHTML || plainToHtml(plainText);
  }

  function currentPlainText(): string {
    if (mode === "plain") return plainText;
    return htmlToPlainText(currentRichHtml());
  }

  async function handleSave() {
    setBusy(true);
    setError(null);
    try {
      const text = currentPlainText();
      const html = mode === "rich" ? currentRichHtml() : plainToHtml(plainText);
      await onSave(text, html);
      setDirty(false);
      setShowPreview(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  if (disabled) {
    return (
      <div className="rounded-2xl border border-separator/40 bg-bg p-6 text-sm text-label-secondary">
        This negotiation is locked.
      </div>
    );
  }

  const toolbar = (
    <div className="flex flex-wrap items-center gap-1 px-3 py-2 border-b border-separator/40 bg-bg">
      <ToolbarBtn label="B" title="Bold" onClick={() => exec("bold")} className="font-bold" />
      <ToolbarBtn label="I" title="Italic" onClick={() => exec("italic")} className="italic" />
      <ToolbarBtn label="U" title="Underline" onClick={() => exec("underline")} className="underline" />
      <span className="w-px h-6 bg-separator/40 mx-1 self-center" />
      <ToolbarBtn label="H1" title="Heading 1" onClick={() => exec("formatBlock", "h2")} />
      <ToolbarBtn label="H2" title="Heading 2" onClick={() => exec("formatBlock", "h3")} />
      <ToolbarBtn label="¶" title="Paragraph" onClick={() => exec("formatBlock", "p")} />
      <span className="w-px h-6 bg-separator/40 mx-1 self-center" />
      <ToolbarBtn label="• List" title="Bullet list" onClick={() => exec("insertUnorderedList")} />
      <ToolbarBtn label="1. List" title="Numbered list" onClick={() => exec("insertOrderedList")} />
    </div>
  );

  const paper = (
    <div className="flex-1 min-h-0 overflow-auto bg-[#f0f2f5] px-4 py-6 sm:px-8">
      <div className="mx-auto max-w-3xl">
        {mode === "rich" ? (
          <div
            ref={editorRef}
            contentEditable
            suppressContentEditableWarning
            className={classNames(
              "min-h-[70vh] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.12),0_1px_2px_rgba(0,0,0,0.08)]",
              "rounded-sm px-10 sm:px-16 py-12 text-[15px] leading-[1.7] text-label",
              "focus:outline-none focus:ring-2 focus:ring-accent/15",
              "prose prose-sm max-w-none font-serif",
            )}
            onInput={() => setDirty(true)}
          />
        ) : (
          <textarea
            className="w-full min-h-[70vh] font-mono text-sm bg-white shadow-md rounded-sm px-6 py-8 focus:outline-none focus:ring-2 focus:ring-accent/15"
            value={plainText}
            onChange={(e) => {
              setPlainText(e.target.value);
              setDirty(true);
            }}
          />
        )}
      </div>
    </div>
  );

  const chrome = (
    <div className="flex items-center justify-between gap-2 flex-wrap px-4 py-3 border-b border-separator/40 bg-bg">
      <div className="min-w-0">
        <div className="text-sm font-semibold text-label truncate">
          Edit document
          <span className="ml-2 font-normal text-label-secondary">
            · v{version.version_number}
            {version.filename ? ` · ${version.filename}` : ""}
          </span>
        </div>
        <p className="text-xs text-label-tertiary mt-0.5">
          Google Docs–style page — edit on the paper, then save as a new version.
          {dirty && <span className="ml-2 text-amber-700 font-medium">Unsaved changes</span>}
        </p>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex gap-1 mr-1">
          <TabButton active={mode === "rich"} onClick={() => setMode("rich")}>
            Rich
          </TabButton>
          <TabButton active={mode === "plain"} onClick={() => setMode("plain")}>
            Plain
          </TabButton>
        </div>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setFullscreen((v) => !v)}
          title={fullscreen ? "Exit fullscreen (Esc)" : "Fullscreen"}
        >
          {fullscreen ? "Exit fullscreen" : "⛶ Fullscreen"}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={busy || !dirty || !canSave}
          onClick={() => setShowPreview((v) => !v)}
        >
          {showPreview ? "Hide preview" : "Preview changes"}
        </Button>
        {canSave && (
          <Button size="sm" disabled={busy || !dirty} onClick={handleSave}>
            <Icon.Check className="w-3.5 h-3.5 mr-1" />
            {busy ? "Saving…" : "Save as new version"}
          </Button>
        )}
      </div>
    </div>
  );

  const body = (
    <div className="flex flex-col flex-1 min-h-0 h-full w-full">
      {chrome}
      {mode === "rich" && toolbar}
      {paper}
      {error && <p className="px-4 py-2 text-sm text-error border-t border-separator/40 shrink-0">{error}</p>}
      {showPreview && (
        <div className="border-t border-separator/40 bg-bg p-4 max-h-72 overflow-auto shrink-0">
          <DiffView
            v1Label="Current"
            v2Label="Your edits"
            blocks={lineDiffBlocks(initialText, currentPlainText())}
            height={240}
          />
        </div>
      )}
    </div>
  );

  if (fullscreen) {
    return createPortal(
      <div className="fixed inset-0 z-[100] h-[100dvh] w-screen max-w-none flex flex-col bg-bg m-0 p-0 overflow-hidden">
        {body}
      </div>,
      document.body,
    );
  }

  return (
    <div className="rounded-2xl border border-separator/40 bg-bg shadow-card overflow-hidden flex flex-col min-h-[calc(100vh-11rem)]">
      {body}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={classNames(
        "text-xs px-2.5 py-1 rounded-md font-medium transition",
        active ? "bg-accent text-white" : "bg-bg-secondary text-label-secondary hover:bg-bg-accent",
      )}
    >
      {children}
    </button>
  );
}

function ToolbarBtn({
  label,
  title,
  onClick,
  className,
}: {
  label: string;
  title: string;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={classNames(
        "text-xs px-2 py-1 rounded border border-transparent hover:border-separator/50 hover:bg-bg-accent text-label-secondary",
        className,
      )}
    >
      {label}
    </button>
  );
}
