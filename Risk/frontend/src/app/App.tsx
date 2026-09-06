import { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "../components/Shell";
import { useAuth } from "./AuthContext";
import { useEffectiveAdmin } from "./ViewModeContext";
import { AuthGate } from "./AuthGate";
import { HomePage } from "../modules/HomePage";
import { M1Page } from "../modules/m1/M1Page";
import { M1AgentsPage } from "../modules/m1/M1AgentsPage";
import { M2Page } from "../modules/m2/M2Page";
import { M3Page } from "../modules/m3/M3Page";
import { AdminPage } from "../modules/AdminPage";
import { UserManagementPage } from "../modules/UserManagementPage";
import { MetricsPage } from "../modules/MetricsPage";
import { LibraryPage } from "../modules/LibraryPage";
import { AuditPage } from "../modules/AuditPage";
import { QueuePage } from "../modules/QueuePage";
import { FormTemplatesPage } from "../modules/forms/FormTemplatesPage";
import { FormBuilderPage } from "../modules/forms/FormBuilderPage";
import { FormAssignmentsPage } from "../modules/forms/FormAssignmentsPage";
import { MyFormsPage } from "../modules/forms/MyFormsPage";
import { FormFillPage } from "../modules/forms/FormFillPage";

function AdminRoute({ children }: { children: ReactNode }) {
  const effectiveIsAdmin = useEffectiveAdmin();
  return effectiveIsAdmin ? <>{children}</> : <Navigate to="/my-forms" replace />;
}

export default function App() {
  const { user, loading } = useAuth();
  const effectiveIsAdmin = useEffectiveAdmin();

  if (loading) {
    return <div className="empty-state">Loading GenAIForge Risk…</div>;
  }

  if (!user) {
    return <AuthGate />;
  }

  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<HomePage />} />
        <Route path="my-forms" element={<MyFormsPage />} />
        <Route path="my-forms/:assignmentId" element={<FormFillPage />} />
        <Route path="m1" element={<M1Page />} />
        {effectiveIsAdmin && (
          <>
            <Route path="queue" element={<QueuePage />} />
            <Route path="m1/agents" element={<M1AgentsPage />} />
            <Route path="m2" element={<M2Page />} />
            <Route path="m3" element={<M3Page />} />
            <Route path="admin" element={<AdminRoute><AdminPage /></AdminRoute>} />
            <Route path="admin/users" element={<AdminRoute><UserManagementPage /></AdminRoute>} />
            <Route path="admin/forms" element={<AdminRoute><FormTemplatesPage /></AdminRoute>} />
            <Route path="admin/forms/:templateId/edit" element={<AdminRoute><FormBuilderPage /></AdminRoute>} />
            <Route path="admin/forms/assignments" element={<AdminRoute><FormAssignmentsPage /></AdminRoute>} />
            <Route path="metrics" element={<AdminRoute><MetricsPage /></AdminRoute>} />
            <Route path="admin/library" element={<LibraryPage />} />
            <Route path="audit" element={<AdminRoute><AuditPage /></AdminRoute>} />
          </>
        )}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
