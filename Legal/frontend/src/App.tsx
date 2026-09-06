import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuditLogPage } from "./pages/AuditLog";
import { Dashboard } from "./pages/Dashboard";
import { DocumentComparisonPage } from "./pages/DocumentComparison";
import { LawGenieChatPage } from "./pages/LawGenieChat";
import { LegalNewsPage } from "./pages/LegalNews";
import { RegulatoryCorpusPage } from "./pages/RegulatoryCorpus";
import { AcceptInvitePage } from "./pages/AcceptInvite";
import { LoginPage } from "./pages/Login";
import { MetricsPanelPage } from "./pages/MetricsPanel";
import { BuildStudioPage } from "./pages/BuildStudio";
import { ContractTemplatesPage } from "./pages/ContractTemplates";
import { PlaybookManagementPage } from "./pages/PlaybookManagement";
import { MSAAutomationPage } from "./pages/MSAAutomation";
import { TaskManagerPage } from "./pages/TaskManager";
import { UserManagementPage } from "./pages/UserManagement";
import { SettingsPage } from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/accept-invite" element={<AcceptInvitePage />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route
          path="jiolegal"
          element={
            <ProtectedRoute permissions={["legal_bot_use"]}>
              <LawGenieChatPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="tasks"
          element={
            <ProtectedRoute permissions={["task_management"]}>
              <TaskManagerPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="build-studio/*"
          element={
            <ProtectedRoute permissions={["build_requests"]}>
              <BuildStudioPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="contract-review/*"
          element={<Navigate to="/jiolegal" replace />}
        />
        <Route
          path="document-comparison/*"
          element={
            <ProtectedRoute permissions={["document_comparison"]}>
              <DocumentComparisonPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="msa-automation/*"
          element={
            <ProtectedRoute permissions={["msa_automation"]}>
              <MSAAutomationPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="playbook"
          element={
            <ProtectedRoute permissions={["playbook_management", "contract_review"]}>
              <PlaybookManagementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="contract-templates"
          element={
            <ProtectedRoute permissions={["msa_automation", "playbook_management"]}>
              <ContractTemplatesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="legal-news/*"
          element={
            <ProtectedRoute permissions={["legal_news_full", "legal_news_digest"]}>
              <LegalNewsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="regulatory-corpus"
          element={
            <ProtectedRoute permissions={["playbook_management"]}>
              <RegulatoryCorpusPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="audit"
          element={
            <ProtectedRoute permissions={["audit_log_all", "audit_log_own"]}>
              <AuditLogPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="metrics"
          element={
            <ProtectedRoute permissions={["audit_log_all"]}>
              <MetricsPanelPage />
            </ProtectedRoute>
          }
        />
        <Route path="settings" element={<SettingsPage />} />
        <Route
          path="users"
          element={
            <ProtectedRoute permissions={["user_management"]}>
              <UserManagementPage />
            </ProtectedRoute>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
