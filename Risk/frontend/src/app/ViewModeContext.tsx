import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./AuthContext";

export type ViewMode = "admin" | "user";

const STORAGE_KEY = "genaiforge_view_mode";

const ADMIN_ONLY_PREFIXES = [
  "/queue",
  "/m2",
  "/m3",
  "/admin",
  "/metrics",
  "/audit",
  "/m1/agents",
];

interface ViewModeContextType {
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
  canToggleView: boolean;
  /** True when the UI should show admin nav and routes. */
  effectiveIsAdmin: boolean;
  /** True when the UI should emphasize the user/form-filler experience. */
  effectiveIsUser: boolean;
}

const ViewModeCtx = createContext<ViewModeContextType | null>(null);

function isAdminOnlyPath(path: string): boolean {
  return ADMIN_ONLY_PREFIXES.some((p) => path === p || path.startsWith(`${p}/`));
}

export function ViewModeProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const hasAdmin = !!user?.roles.includes("admin");
  const hasUser = !!user?.roles.includes("user");
  const canToggleView = hasAdmin && hasUser;

  const [viewMode, setViewModeState] = useState<ViewMode>(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as ViewMode | null;
    if (stored === "admin" || stored === "user") return stored;
    return hasAdmin ? "admin" : "user";
  });

  useEffect(() => {
    if (!user) return;
    if (!canToggleView) {
      setViewModeState(hasAdmin ? "admin" : "user");
      return;
    }
    const stored = localStorage.getItem(STORAGE_KEY) as ViewMode | null;
    if (stored === "admin" || stored === "user") {
      setViewModeState(stored);
    }
  }, [user, canToggleView, hasAdmin]);

  const setViewMode = (mode: ViewMode) => {
    setViewModeState(mode);
    if (canToggleView) {
      localStorage.setItem(STORAGE_KEY, mode);
    }
    if (mode === "user" && isAdminOnlyPath(location.pathname)) {
      navigate("/my-forms", { replace: true });
    }
    if (mode === "admin" && location.pathname === "/") {
      navigate("/", { replace: true });
    }
  };

  const effectiveIsAdmin = hasAdmin && (!hasUser || viewMode === "admin");
  const effectiveIsUser = hasUser && (!hasAdmin || viewMode === "user");

  const value = useMemo(
    () => ({
      viewMode: canToggleView ? viewMode : hasAdmin ? "admin" : "user",
      setViewMode,
      canToggleView,
      effectiveIsAdmin,
      effectiveIsUser,
    }),
    [viewMode, canToggleView, hasAdmin, effectiveIsAdmin, effectiveIsUser]
  );

  return <ViewModeCtx.Provider value={value}>{children}</ViewModeCtx.Provider>;
}

export function useViewMode(): ViewModeContextType {
  const ctx = useContext(ViewModeCtx);
  if (!ctx) throw new Error("useViewMode must be used within ViewModeProvider");
  return ctx;
}

/** Admin UI visibility — respects the admin/user view toggle when both roles exist. */
export function useEffectiveAdmin(): boolean {
  return useViewMode().effectiveIsAdmin;
}
