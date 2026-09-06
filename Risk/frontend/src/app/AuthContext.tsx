import React, { createContext, useContext, useEffect, useState } from "react";
import { api, LoginResponse, User } from "../api/client";

export const SIGNED_OUT_KEY = "genaiforge_signed_out";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  ssoEnabled: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const me = await api.get<User>("/auth/me");
      sessionStorage.removeItem(SIGNED_OUT_KEY);
      setUser(me);
    } catch {
      setUser(null);
    }
  };

  const login = async (email: string, password: string) => {
    const res = await api.post<LoginResponse>("/auth/login", { email, password });
    sessionStorage.removeItem(SIGNED_OUT_KEY);
    setUser(res.user);
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // Already signed out or API unreachable
    }
    sessionStorage.clear();
    sessionStorage.setItem(SIGNED_OUT_KEY, "1");
    setUser(null);
  };

  useEffect(() => {
    refresh().finally(() => setLoading(false));
    const onUnauthorized = () => setUser(null);
    window.addEventListener("genaiforge:unauthorized", onUnauthorized);
    return () => window.removeEventListener("genaiforge:unauthorized", onUnauthorized);
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, loading, ssoEnabled: false, login, logout, refresh }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** Admin-only surfaces: Administration, User Management, Metrics, Audit Log. */
export function useIsAdmin(): boolean {
  const { user } = useAuth();
  return !!user?.roles.includes("admin");
}
