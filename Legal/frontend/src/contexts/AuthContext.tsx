import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";

import { api } from "@/lib/api";
import {
  applyTokenResponse,
  clearSessionMeta,
  getSessionMeta,
  markActivity,
  setAuthMessage,
  wasRecentlyActive,
} from "@/lib/session";
import type { User } from "@/types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/** How often we check whether to slide the idle window. */
const TICK_MS = 30_000;
/** Refresh when less than this fraction of the idle window remains. */
const REFRESH_WHEN_REMAINING_FRACTION = 0.45;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const refreshInFlight = useRef<Promise<void> | null>(null);

  // Session lives in an httpOnly cookie — invisible to JS by design, so
  // there's no client-side signal to gate on. Always ask the server; a
  // missing/expired cookie just comes back as a normal 401.
  const refresh = useCallback(async () => {
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      setUser(null);
    }
  }, []);

  const slideSession = useCallback(async () => {
    if (refreshInFlight.current) return refreshInFlight.current;

    const run = (async () => {
      try {
        const res = await api.refreshSession();
        applyTokenResponse(res);
      } catch {
        // 401 handler in api.ts clears session state + redirects when appropriate.
      } finally {
        refreshInFlight.current = null;
      }
    })();
    refreshInFlight.current = run;
    return run;
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  // Track user activity → sliding idle window.
  useEffect(() => {
    if (!user) return;

    const onActivity = () => markActivity();
    const events: Array<keyof WindowEventMap> = [
      "pointerdown",
      "keydown",
      "scroll",
      "touchstart",
    ];
    for (const ev of events) {
      window.addEventListener(ev, onActivity, { passive: true });
    }
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") markActivity();
    });
    markActivity();

    const tick = window.setInterval(() => {
      const meta = getSessionMeta();
      const idleMs = meta?.idleTimeoutMs ?? 60 * 60 * 1000;

      // Client-side idle sign-out (matches server idle window). Only the
      // server can actually clear the httpOnly cookie, so this also fires
      // a best-effort logout call — not just a local UI reset.
      if (!wasRecentlyActive(idleMs)) {
        setAuthMessage(
          "Your session expired due to inactivity. Please sign in again.",
        );
        void api.logout().catch(() => {});
        clearSessionMeta();
        setUser(null);
        if (!window.location.pathname.startsWith("/login")) {
          window.location.assign("/login?reason=session");
        }
        return;
      }

      const expiresAt = meta?.expiresAtMs ?? 0;
      const remaining = expiresAt - Date.now();
      const threshold = idleMs * REFRESH_WHEN_REMAINING_FRACTION;
      if (remaining > 0 && remaining <= threshold) {
        void slideSession();
      } else if (!meta) {
        // Legacy session without meta — refresh once to adopt sliding policy.
        void slideSession();
      }
    }, TICK_MS);

    return () => {
      for (const ev of events) {
        window.removeEventListener(ev, onActivity);
      }
      window.clearInterval(tick);
    };
  }, [user, slideSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api.login(email, password);
      applyTokenResponse(res);
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // Best-effort — still clear local state even if the call fails.
    }
    clearSessionMeta();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, login, logout, refresh }),
    [user, loading, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
