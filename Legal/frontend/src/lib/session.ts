/**
 * Sliding idle session helpers.
 *
 * Industry pattern: extend the JWT while the user is active; sign out after
 * idle timeout or absolute max lifetime (enforced by the backend).
 */

const LAST_ACTIVITY_KEY = "legalos.last_activity";
const AUTH_MESSAGE_KEY = "legalos.auth_message";
const SESSION_META_KEY = "legalos.session_meta";

export type SessionMeta = {
  /** Idle window length in ms (from server). */
  idleTimeoutMs: number;
  /** Absolute max session length in ms from login (from server). */
  absoluteTimeoutMs: number;
  /** When this access token was received (ms epoch). */
  issuedAtMs: number;
  /** When this access token's idle deadline hits (ms epoch). */
  expiresAtMs: number;
};

export function markActivity(): void {
  try {
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()));
  } catch {
    /* ignore quota / private mode */
  }
}

export function lastActivityMs(): number {
  try {
    const raw = localStorage.getItem(LAST_ACTIVITY_KEY);
    const n = raw ? Number(raw) : 0;
    return Number.isFinite(n) ? n : 0;
  } catch {
    return 0;
  }
}

export function wasRecentlyActive(withinMs: number): boolean {
  const last = lastActivityMs();
  if (!last) return false;
  return Date.now() - last < withinMs;
}

export function saveSessionMeta(meta: SessionMeta): void {
  try {
    localStorage.setItem(SESSION_META_KEY, JSON.stringify(meta));
  } catch {
    /* ignore */
  }
}

export function getSessionMeta(): SessionMeta | null {
  try {
    const raw = localStorage.getItem(SESSION_META_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as SessionMeta;
  } catch {
    return null;
  }
}

export function clearSessionMeta(): void {
  try {
    localStorage.removeItem(SESSION_META_KEY);
    localStorage.removeItem(LAST_ACTIVITY_KEY);
  } catch {
    /* ignore */
  }
}

export function setAuthMessage(message: string): void {
  try {
    sessionStorage.setItem(AUTH_MESSAGE_KEY, message);
  } catch {
    /* ignore */
  }
}

export function consumeAuthMessage(): string | null {
  try {
    const msg = sessionStorage.getItem(AUTH_MESSAGE_KEY);
    if (msg) sessionStorage.removeItem(AUTH_MESSAGE_KEY);
    return msg;
  } catch {
    return null;
  }
}

/** Apply token response fields after login / refresh. */
export function applyTokenResponse(res: {
  expires_in: number;
  idle_timeout_seconds?: number;
  absolute_timeout_seconds?: number;
}): void {
  const now = Date.now();
  const idleSec = res.idle_timeout_seconds ?? res.expires_in;
  const absSec = res.absolute_timeout_seconds ?? 12 * 3600;
  saveSessionMeta({
    idleTimeoutMs: idleSec * 1000,
    absoluteTimeoutMs: absSec * 1000,
    issuedAtMs: now,
    expiresAtMs: now + res.expires_in * 1000,
  });
  markActivity();
}
