import { useCallback, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { classNames } from "@/lib/utils";

const ACCEPT = ".pdf,.docx,.doc,.txt,.md";
const ACCEPT_MIME = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "text/plain",
  "text/markdown",
];
const MAX_BYTES = 50 * 1024 * 1024;

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function extLabel(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i + 1).toUpperCase() : "FILE";
}

function extColor(ext: string): string {
  const e = ext.toLowerCase();
  if (e === "pdf") return "bg-red-100 text-error border-error/20";
  if (e === "docx" || e === "doc") return "bg-blue-100 text-blue-700 border-accent/20";
  return "bg-bg-secondary text-label-secondary border-separator/40";
}

export function UploadZone({
  file,
  onFile,
  label,
  hint,
  disabled,
  compact,
}: {
  file: File | null;
  onFile: (f: File | null) => void;
  label?: string;
  hint?: string;
  disabled?: boolean;
  compact?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validate = (f: File): string | null => {
    if (f.size > MAX_BYTES) return `File exceeds ${humanSize(MAX_BYTES)} limit`;
    if (f.size === 0) return "File is empty";
    const lower = f.name.toLowerCase();
    const okExt = [".pdf", ".docx", ".doc", ".txt", ".md"].some((x) => lower.endsWith(x));
    const okMime = !f.type || ACCEPT_MIME.includes(f.type);
    if (!okExt && !okMime) return "Unsupported file type — use PDF, DOCX, or TXT";
    return null;
  };

  const accept = useCallback(
    (f: File) => {
      const err = validate(f);
      if (err) {
        setError(err);
        onFile(null);
        return;
      }
      setError(null);
      onFile(f);
    },
    [onFile],
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (disabled) return;
    const f = e.dataTransfer.files?.[0];
    if (f) accept(f);
  };

  if (file && !compact) {
    return (
      <div className="border border-separator/40 rounded-lg p-4 bg-bg-secondary">
        <div className="flex items-center gap-4">
          <div
            className={classNames(
              "w-14 h-16 rounded border flex flex-col items-center justify-center text-xs font-bold",
              extColor(extLabel(file.name)),
            )}
          >
            <span>{extLabel(file.name)}</span>
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-medium text-sm text-label truncate">{file.name}</div>
            <div className="text-xs text-label-secondary mt-1">
              {humanSize(file.size)} · ready to upload
            </div>
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={disabled}
            onClick={() => {
              onFile(null);
              if (inputRef.current) inputRef.current.value = "";
            }}
          >
            Replace
          </Button>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) accept(f);
          }}
        />
      </div>
    );
  }

  return (
    <div>
      <label
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={classNames(
          "flex flex-col items-center justify-center text-center border-2 border-dashed rounded-lg cursor-pointer transition min-h-tap",
          compact ? "py-6 px-4" : "py-10 px-6",
          dragOver
            ? "border-accent bg-accent/10"
            : "border-separator/60 bg-bg-secondary hover:bg-bg hover:border-accent/40",
          disabled && "opacity-50 cursor-not-allowed",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          disabled={disabled}
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) accept(f);
          }}
        />
        <svg
          className={classNames(
            "text-label-tertiary mb-2",
            compact ? "w-8 h-8" : "w-10 h-10",
          )}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M7 16a4 4 0 01-.88-7.9 5 5 0 019.9-1.1A4.5 4.5 0 0117 16M9 13l3-3m0 0l3 3m-3-3v9"
          />
        </svg>
        {file && compact ? (
          <div className="text-sm">
            <span className="font-medium text-label">{file.name}</span>
            <span className="text-label-secondary ml-2">· {humanSize(file.size)}</span>
          </div>
        ) : (
          <>
            <div className={classNames("font-medium text-label-secondary", compact ? "text-sm" : "text-base")}>
              {label || "Drop your contract here, or click to browse"}
            </div>
            <div className="text-xs text-label-secondary mt-1">
              {hint || `PDF, DOCX, or TXT · up to ${humanSize(MAX_BYTES)}`}
            </div>
          </>
        )}
      </label>
      {error && <p className="text-footnote text-error mt-2" role="alert">{error}</p>}
    </div>
  );
}
