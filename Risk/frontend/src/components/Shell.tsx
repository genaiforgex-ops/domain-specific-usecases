import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth, useIsAdmin } from "../app/AuthContext";
import { useEffectiveAdmin, useViewMode } from "../app/ViewModeContext";
import { CommandPalette } from "./CommandPalette";
import { ErrorBoundary } from "./ErrorBoundary";
import {
  IconHome,
  IconQueue,
  IconShield,
  IconBuilding,
  IconChart,
  IconAudit,
  IconSettings,
  IconRobot,
  IconSearch,
  IconChevron,
  IconSun,
  IconMoon,
  IconSparkle,
} from "./ui/Icons";

type NavItem = {
  to: string;
  label: string;
  icon: (p: { size?: number; className?: string }) => JSX.Element;
  short?: string;
  /** Exact-match only. */
  end?: boolean;
  adminOnly?: boolean;
  /** Path prefixes where this item must NOT light up, despite matching. */
  notWhen?: string[];
};

const ADMIN_WORKSPACE: NavItem[] = [
  { to: "/", label: "Dashboard", icon: IconHome, end: true },
  { to: "/queue", label: "My Queue", icon: IconQueue },
  { to: "/my-forms", label: "My Forms", icon: IconQueue },
];

const USER_WORKSPACE: NavItem[] = [
  { to: "/", label: "Dashboard", icon: IconHome, end: true },
  { to: "/my-forms", label: "My Forms", icon: IconQueue },
];

const MODULES: NavItem[] = [
  { to: "/m1", label: "Outsourcing Classification", short: "M1", icon: IconShield },
  { to: "/m2", label: "Vendor Due Diligence", short: "M2", icon: IconBuilding },
  { to: "/m3", label: "Risk Scoring", short: "M3", icon: IconChart },
];

const ADMIN_GOVERNANCE: NavItem[] = [
  { to: "/admin", label: "Administration", icon: IconSettings, end: true, adminOnly: true },
  { to: "/admin/users", label: "User Management", icon: IconQueue, adminOnly: true },
  // "/admin/forms" is a prefix of "/admin/forms/assignments", so NavLink counts
  // both as active on the assignments page. `end` would fix that but would also
  // stop the template *editor* (/admin/forms/:id/edit) highlighting this item,
  // so exclude the one sibling route instead.
  {
    to: "/admin/forms",
    label: "Form Templates",
    icon: IconSparkle,
    adminOnly: true,
    notWhen: ["/admin/forms/assignments"],
  },
  { to: "/admin/forms/assignments", label: "Form Assignments", icon: IconQueue, adminOnly: true },
  { to: "/admin/library", label: "Regulation Library", icon: IconSparkle },
  { to: "/m1/agents", label: "M1 Agents", icon: IconRobot },
  { to: "/metrics", label: "Metrics", icon: IconChart, adminOnly: true },
  { to: "/audit", label: "Audit Log", icon: IconAudit, adminOnly: true },
];

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  user: "User",
};

function initTheme(): "light" | "dark" {
  const stored = localStorage.getItem("theme") as "light" | "dark" | null;
  if (stored) return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function Shell() {
  const { user, logout } = useAuth();
  const isAdmin = useIsAdmin();
  const effectiveIsAdmin = useEffectiveAdmin();
  const { viewMode, setViewMode, canToggleView } = useViewMode();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(initTheme);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => setTheme((t) => (t === "dark" ? "light" : "dark"));

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const initials = user?.display_name
    ?.split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase() ?? "?";

  const primaryRole = canToggleView
    ? `Viewing as ${viewMode === "admin" ? "Admin" : "User"}`
    : user?.roles.length
      ? user.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")
      : "";
  const workspaceNav = effectiveIsAdmin ? ADMIN_WORKSPACE : USER_WORKSPACE;
  const governanceNav = effectiveIsAdmin ? ADMIN_GOVERNANCE.filter((item) => !item.adminOnly || isAdmin) : [];

  return (
    <div className={`shell ${collapsed ? "shell--collapsed" : ""}`}>
      <a href="#main" className="skip-link">Skip to main content</a>

      <nav id="nav" className="shell__nav" aria-label="Main navigation">
        <div className="shell__brand">
          <span className="shell__logo" aria-hidden="true">G</span>
          {!collapsed && <span>GenAIForge</span>}
        </div>

        {/* Only the link groups scroll; the brand and the collapse toggle stay
            put. Without this the nav was a fixed 100vh with no overflow, so on
            a short window the lower items were simply unreachable. */}
        <div className="shell__nav-scroll">
        <section className="shell__section">
          {!collapsed && <h2 className="shell__section-title">Workspace</h2>}
          {workspaceNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? "active" : "")}
              aria-current={location.pathname === item.to ? "page" : undefined}
            >
              <item.icon size={18} />
              {!collapsed && item.label}
            </NavLink>
          ))}
        </section>

        {effectiveIsAdmin && (
          <>
            <section className="shell__section">
              {!collapsed && <h2 className="shell__section-title">Risk Modules</h2>}
              {MODULES.map((m) => (
                <NavLink key={m.to} to={m.to} className={({ isActive }) => (isActive ? "active" : "")}>
                  <m.icon size={18} />
                  {!collapsed ? m.label : m.short}
                </NavLink>
              ))}
            </section>

            <section className="shell__section">
              {!collapsed && <h2 className="shell__section-title">Governance</h2>}
              {governanceNav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    isActive && !item.notWhen?.some((p) => location.pathname.startsWith(p))
                      ? "active"
                      : ""
                  }
                >
                  <item.icon size={18} />
                  {!collapsed && item.label}
                </NavLink>
              ))}
            </section>
          </>
        )}
        </div>

        <button
          type="button"
          className="shell__collapse"
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <IconChevron direction={collapsed ? "right" : "left"} size={16} />
        </button>
      </nav>

      <div className="shell__main-wrap">
        <header className="shell__topbar" role="banner">
          <button type="button" className="shell__search-btn" onClick={() => setPaletteOpen(true)}>
            <IconSearch size={18} />
            <span>Search vendors, projects, classifications…</span>
            <kbd>Ctrl K</kbd>
          </button>

          <button
            type="button"
            className="shell__theme-toggle"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
          </button>

          {canToggleView && (
            <div className="shell__view-toggle" role="group" aria-label="Switch view mode">
              <button
                type="button"
                className={viewMode === "admin" ? "active" : ""}
                onClick={() => setViewMode("admin")}
                aria-pressed={viewMode === "admin"}
              >
                Admin
              </button>
              <button
                type="button"
                className={viewMode === "user" ? "active" : ""}
                onClick={() => setViewMode("user")}
                aria-pressed={viewMode === "user"}
              >
                User
              </button>
            </div>
          )}

          <div className="shell__user">
            <div className="shell__user-info">
              <span className="shell__user-name">{user?.display_name}</span>
              <span className="shell__user-role">{primaryRole}</span>
            </div>
            <span className="shell__avatar" aria-hidden="true">{initials}</span>
            <button
              type="button"
              className="shell__signout"
              onClick={logout}
              aria-label="Sign out"
            >
              Sign out
            </button>
          </div>
        </header>

        <main id="main" className="shell__content" role="main">
          <ErrorBoundary key={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>

      {paletteOpen && (
        <CommandPalette onClose={() => setPaletteOpen(false)} onNavigate={navigate} />
      )}
    </div>
  );
}
