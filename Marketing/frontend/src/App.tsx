import { Routes, Route, Navigate } from 'react-router-dom';
import { useApp } from './state/AppContext';
import { ROLES, can } from './lib/roles';
import { AppShell } from './components/layout/AppShell';

import Login from './pages/Login';
import Home from './pages/shared/Home';
import Inbox from './pages/shared/Inbox';
import SearchPage from './pages/shared/Search';
import Audit from './pages/shared/Audit';
import ApprovalQueue from './pages/shared/Gate1Queue';

import MyBriefs from './pages/bc/MyBriefs';
import NewBriefPicker from './pages/bc/NewBriefPicker';
import NewBrief from './pages/bc/NewBrief';
import BriefDetail from './pages/briefs/BriefDetail';
import CopyQueue from './pages/st/CreativeQueue';
import MyAssets from './pages/ds/MyAssets';
import DesignWorkspace from './pages/ds/DesignWorkspace';
import PromptStudio from './pages/ds/PromptStudio';
import Dashboard from './pages/admin/Dashboard';
import Costing from './pages/admin/Costing';
import OversightBriefs from './pages/admin/OversightBriefs';
import Users from './pages/admin/Users';
import RoleDefaults from './pages/admin/RoleDefaults';

export default function App() {
  const { role, authReady } = useApp();

  // Avoid a login flash while a stored token is being validated.
  if (!authReady) {
    return (
      <div className="min-h-screen grid place-items-center bg-bg-secondary">
        <span className="h-7 w-7 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading" />
      </div>
    );
  }

  if (!role) {
    return (
      <Routes>
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to={ROLES[role].home} replace />} />

        {/* Role Home / Today — landing for every role */}
        <Route path="/home" element={<Home />} />

        {/* Product Lead — brief authoring */}
        <Route path="/briefs" element={<MyBriefs />} />
        <Route path="/briefs/new" element={<NewBriefPicker />} />
        <Route path="/briefs/new/:size" element={<NewBrief />} />
        <Route path="/briefs/:id/edit" element={<NewBrief />} />
        <Route path="/briefs/:id" element={<BriefDetail />} />

        {/* Copywriter */}
        <Route path="/copies" element={<CopyQueue />} />

        {/* Approval — adapts to ST / ML / PL lane */}
        <Route path="/approvals" element={<ApprovalQueue />} />

        {/* Admin */}
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/costing" element={<Costing />} />
        <Route path="/oversight" element={<OversightBriefs />} />
        <Route path="/users" element={<Users />} />
        <Route path="/assignees" element={<RoleDefaults />} />

        {/* Designer */}
        <Route path="/assets" element={<MyAssets />} />
        <Route path="/assets/:id" element={<DesignWorkspace />} />
        <Route path="/prompts" element={<PromptStudio />} />

        {/* Shared across all roles */}
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/search" element={<SearchPage />} />
        {/* Audit log — Admin only; other roles are redirected to their home. */}
        <Route
          path="/audit"
          element={can(role, 'audit.view') ? <Audit /> : <Navigate to={ROLES[role].home} replace />}
        />

        <Route path="*" element={<Navigate to={ROLES[role].home} replace />} />
      </Route>
    </Routes>
  );
}
