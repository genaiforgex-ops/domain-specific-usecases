import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "@/contexts/AuthContext";
import { hasPermission } from "@/lib/auth";
import type { Permission } from "@/types";

export function ProtectedRoute({
  children,
  permissions,
}: {
  children: ReactNode;
  permissions?: Permission[];
}) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return <div className="p-10 text-label-secondary">Loading…</div>;
  }
  if (!user) return <Navigate to={`/login${location.search}`} replace />;
  if (permissions && permissions.length > 0 && !hasPermission(user, ...permissions)) {
    return (
      <div className="p-10 text-center text-label-secondary">
        <h2 className="text-lg font-semibold mb-2">Access denied</h2>
        <p className="text-sm">
          Your role ({user.role}) does not have permission to view this module.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
