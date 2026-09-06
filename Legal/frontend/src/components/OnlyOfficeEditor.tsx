import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

import { classNames } from "@/lib/utils";

type OnlyOfficeInstance = {
  destroyEditor: () => void;
  resizeEditor?: () => void;
  createConnector?: () => {
    executeMethod: (name: string, args: unknown[], callback?: () => void) => void;
  };
};

declare global {
  interface Window {
    DocsAPI?: {
      DocEditor: new (
        id: string,
        config: {
          documentServerUrl?: string;
          token: string;
          events?: Record<string, (...args: unknown[]) => void>;
        },
      ) => OnlyOfficeInstance;
    };
    __onlyofficeScriptPromise?: Promise<void>;
  }
}

const MIN_EDITOR_HEIGHT = 400;

function loadOnlyOfficeApi(documentServerUrl: string): Promise<void> {
  if (window.DocsAPI) return Promise.resolve();
  if (window.__onlyofficeScriptPromise) return window.__onlyofficeScriptPromise;

  const base = documentServerUrl.replace(/\/$/, "");
  window.__onlyofficeScriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(
      `script[data-onlyoffice-api="${base}"]`,
    ) as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("ONLYOFFICE script failed")), {
        once: true,
      });
      return;
    }

    const script = document.createElement("script");
    script.dataset.onlyofficeApi = base;
    script.src = `${base}/web-apps/apps/api/documents/api.js`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () =>
      reject(new Error("ONLYOFFICE Document Server failed to load. Is the server running?"));
    document.body.appendChild(script);
  });

  return window.__onlyofficeScriptPromise;
}

export function OnlyOfficeEditor({
  documentServerUrl,
  token,
  config,
  mode = "edit",
  onReady,
  onError,
  onDocumentStateChange,
  className,
  /** Fit document to container width (reduces gray side gutters). */
  fitToWidth = false,
}: {
  documentServerUrl: string;
  token: string;
  config?: Record<string, unknown>;
  mode?: "edit" | "view";
  onReady?: () => void;
  onError?: (message: string) => void;
  onDocumentStateChange?: (modified: boolean) => void;
  className?: string;
  fitToWidth?: boolean;
}) {
  const reactId = useId().replace(/:/g, "");
  const containerId = `onlyoffice-${reactId}`;
  const shellRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<OnlyOfficeInstance | null>(null);
  const configRef = useRef(config);
  const onReadyRef = useRef(onReady);
  const onErrorRef = useRef(onError);
  const onDocumentStateChangeRef = useRef(onDocumentStateChange);
  const fitToWidthRef = useRef(fitToWidth);
  const [readyToInit, setReadyToInit] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  configRef.current = config;
  onReadyRef.current = onReady;
  onErrorRef.current = onError;
  onDocumentStateChangeRef.current = onDocumentStateChange;
  fitToWidthRef.current = fitToWidth;

  useLayoutEffect(() => {
    const el = shellRef.current;
    if (!el) return;

    const measure = () => {
      // Measure the *available* parent box, not our own fixed height
      // (that old loop locked the editor at ~600px and left gray dead space).
      const parent = el.parentElement;
      const available = parent
        ? Math.round(parent.getBoundingClientRect().height)
        : Math.round(el.getBoundingClientRect().height);
      setReadyToInit(available >= 200);
      editorRef.current?.resizeEditor?.();
    };

    measure();
    const ro = new ResizeObserver(measure);
    if (el.parentElement) ro.observe(el.parentElement);
    ro.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  useEffect(() => {
    if (!token || !readyToInit) return;

    let cancelled = false;
    const base = documentServerUrl.replace(/\/$/, "");

    function initEditor() {
      if (cancelled || !window.DocsAPI) return;
      try {
        editorRef.current?.destroyEditor?.();

        // Keep signed config intact — JWT covers the whole payload.
        const raw = { ...(configRef.current || {}) } as Record<string, unknown>;

        const applyFitToWidth = () => {
          if (!fitToWidthRef.current) return;
          try {
            // -2 = fit to width (shrinks gray side gutters around the page)
            editorRef.current?.createConnector?.().executeMethod("SetZoom", [-2]);
          } catch {
            /* connector not available on older Document Server builds */
          }
        };

        editorRef.current = new window.DocsAPI!.DocEditor(containerId, {
          documentServerUrl: base,
          ...raw,
          token,
          events: {
            onDocumentReady: () => {
              onReadyRef.current?.();
              applyFitToWidth();
              window.setTimeout(() => {
                editorRef.current?.resizeEditor?.();
                applyFitToWidth();
              }, 100);
              window.setTimeout(() => editorRef.current?.resizeEditor?.(), 400);
            },
            onDocumentStateChange: (event: unknown) => {
              const modified = (event as { data?: boolean })?.data;
              if (typeof modified === "boolean") onDocumentStateChangeRef.current?.(modified);
            },
            onError: (event: unknown) => {
              const data = (event as { data?: string })?.data;
              onErrorRef.current?.(data || "Editor error");
            },
          },
        });
        window.setTimeout(() => editorRef.current?.resizeEditor?.(), 250);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to start ONLYOFFICE editor";
        setLoadError(msg);
        onError?.(msg);
      }
    }

    loadOnlyOfficeApi(documentServerUrl)
      .then(() => {
        if (!cancelled) initEditor();
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : "Failed to load ONLYOFFICE";
        setLoadError(msg);
        onError?.(msg);
      });

    return () => {
      cancelled = true;
      editorRef.current?.destroyEditor?.();
      editorRef.current = null;
    };
  }, [containerId, documentServerUrl, token, readyToInit, mode]);

  if (!token) {
    return (
      <div className="text-sm text-label-secondary p-6 text-center">Loading editor configuration…</div>
    );
  }

  if (loadError) {
    return (
      <div className="rounded-lg border border-error/20 bg-red-50 p-4 text-sm text-error">
        {loadError}
      </div>
    );
  }

  return (
    <div
      ref={shellRef}
      className={classNames(
        "w-full h-full min-h-0 bg-bg overflow-hidden",
        className,
      )}
      style={{ height: "100%", minHeight: MIN_EDITOR_HEIGHT }}
    >
      <div id={containerId} className="w-full h-full" style={{ height: "100%", width: "100%" }} />
    </div>
  );
}
