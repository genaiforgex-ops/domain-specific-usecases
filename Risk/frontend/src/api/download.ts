import { FETCH_CREDENTIALS } from "./client";

// Binary endpoints don't go through `api.*`: request() only unwraps a blob when
// the response is application/pdf, and widening that check would make every
// caller's return type a lie. These two helpers do their own fetch instead,
// sharing the session cookie the same way.
//
// Two shapes, because the two use cases genuinely differ: a report PDF is meant
// to be previewed in a tab, an .xlsx is meant to land in the Downloads folder
// under a sensible name.

async function fetchBlob(path: string): Promise<Response> {
  const res = await fetch(`${import.meta.env.VITE_API_URL || ""}/api/v1${path}`, {
    credentials: FETCH_CREDENTIALS,
  });
  if (!res.ok) {
    // Error responses are JSON even on a binary endpoint.
    const detail = await res.json().then((b) => b?.detail).catch(() => null);
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res;
}

/** Filename the server asked for via Content-Disposition, if any. */
function filenameFromResponse(res: Response): string | null {
  const header = res.headers.get("content-disposition");
  const match = header?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return match ? decodeURIComponent(match[1]) : null;
}

/** Fetch and open in a new tab — for PDFs the user wants to read, not keep. */
export async function openBlobInTab(path: string): Promise<void> {
  const res = await fetchBlob(path);
  const url = URL.createObjectURL(await res.blob());
  window.open(url, "_blank");
  // The new tab needs the URL to stay alive long enough to load it, so this
  // can't be revoked inline — but it must be revoked, or every preview leaks
  // the whole file for the life of the session.
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Fetch and save to disk under `fallbackName`, or whatever the server named it. */
export async function downloadBlob(path: string, fallbackName: string): Promise<void> {
  const res = await fetchBlob(path);
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filenameFromResponse(res) ?? fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
