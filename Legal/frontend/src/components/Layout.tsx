import { useEffect, useState, type ComponentType, type SVGProps } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { Icon, LawGenieMark } from "@/components/Icons";
import { GlassBar } from "@/components/ui/GlassBar";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useAuth } from "@/contexts/AuthContext";
import { hasPermission, roleLabel } from "@/lib/auth";
import { classNames } from "@/lib/utils";
import type { Permission } from "@/types";

const NAV_COLLAPSED_KEY = "legalos-nav-collapsed";

type IconCmp = ComponentType<SVGProps<SVGSVGElement>>;

interface NavItem {
  to: string;
  label: string;
  icon: IconCmp;
  permissions?: Permission[];
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: Icon.Sparkles },
  { to: "/tasks", label: "Task Manager", icon: Icon.Inbox, permissions: ["task_management"] },
  { to: "/build-studio", label: "Build Studio", icon: Icon.Rocket, permissions: ["build_requests"] },
  {
    to: "/document-comparison",
    label: "Doc Comparison",
    icon: Icon.Compare,
    permissions: ["document_comparison"],
  },
  { to: "/jiolegal", label: "LawGenie", icon: LawGenieMark, permissions: ["legal_bot_use"] },
  { to: "/msa-automation", label: "MSA Automation", icon: Icon.Workflow, permissions: ["msa_automation", "msa_shared_view"] },
  {
    to: "/contract-templates",
    label: "Template Library",
    icon: Icon.Documents,
    permissions: ["msa_automation", "playbook_management"],
  },
  {
    to: "/playbook",
    label: "Playbook",
    icon: Icon.Flag,
    permissions: ["playbook_management", "contract_review"],
  },
  {
    to: "/legal-news",
    label: "Legal News",
    icon: Icon.Radar,
    permissions: ["legal_news_full", "legal_news_digest"],
  },
  {
    to: "/regulatory-corpus",
    label: "Regulatory Corpus",
    icon: Icon.Shield,
    permissions: ["playbook_management"],
  },
  { to: "/settings", label: "Settings", icon: Icon.Settings },
  { to: "/audit", label: "Audit Log", icon: Icon.Activity, permissions: ["audit_log_all", "audit_log_own"] },
  { to: "/metrics", label: "Metrics", icon: Icon.BarChart, permissions: ["audit_log_all"] },
  { to: "/users", label: "Users", icon: Icon.Users, permissions: ["user_management"] },
];

function pageTitle(pathname: string): string {
  const item = NAV.find((n) => (n.to === "/" ? pathname === "/" : pathname.startsWith(n.to)));
  return item?.label ?? "LegalOS";
}

function readNavCollapsed(): boolean {
  try {
    return localStorage.getItem(NAV_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function UserMenu({
  fullName,
  role,
  initials,
  onSignOut,
}: {
  fullName: string;
  role: string;
  initials: string;
  onSignOut: () => void;
}) {
  return (
    <div className="flex items-center gap-2 pl-3 border-l border-separator/40">
      <div
        className="flex items-center gap-2.5 min-h-tap px-2 py-1 rounded-md"
        title={`${fullName} · ${role}`}
      >
        <div
          className="w-8 h-8 rounded-full bg-ink text-white text-caption font-semibold flex items-center justify-center shrink-0"
          aria-hidden
        >
          {initials}
        </div>
        <div className="hidden lg:block min-w-0 max-w-[160px]">
          <div className="text-subheadline text-label font-medium truncate leading-tight">{fullName}</div>
          <div className="text-caption text-label-tertiary truncate leading-tight">{role}</div>
        </div>
      </div>
      <ThemeToggle />
      <button
        type="button"
        onClick={onSignOut}
        className="min-h-tap inline-flex items-center px-3 py-2 rounded-md text-subheadline font-medium text-label-secondary hover:text-accent hover:bg-bg-secondary transition-colors"
      >
        Sign out
      </button>
    </div>
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [navCollapsed, setNavCollapsed] = useState(readNavCollapsed);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(NAV_COLLAPSED_KEY, navCollapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [navCollapsed]);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  if (!user) return null;

  const isLawGenie = location.pathname.startsWith("/jiolegal");
  const isMsaAutomation = location.pathname.startsWith("/msa-automation");
  // LawGenie + MSA workspaces: use full main width (no max-w-7xl gutters).
  const isFullBleed = isLawGenie || isMsaAutomation;

  const initials = user.full_name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const visibleNav = NAV.filter((n) => !n.permissions || hasPermission(user, ...n.permissions));

  function signOut() {
    logout();
    navigate("/login", { replace: true });
  }

  function toggleNav() {
    if (window.matchMedia("(max-width: 1023px)").matches) {
      setMobileNavOpen((v) => !v);
    } else {
      setNavCollapsed((v) => !v);
    }
  }

  const sidebarContent = (
    <>
      <div
        className={classNames(
          "border-b border-white/10 flex items-center shrink-0",
          navCollapsed ? "px-2 py-5 justify-center" : "px-5 py-5 justify-between gap-2",
        )}
      >
        <div className={classNames("flex items-center gap-3 min-w-0", navCollapsed && "justify-center")}>
          <div className="w-9 h-9 rounded-md bg-white/10 ring-1 ring-white/15 flex items-center justify-center shrink-0">
            <Icon.Shield className="w-5 h-5 text-white" aria-hidden />
          </div>
          {!navCollapsed && (
            <div className="min-w-0">
              <div className="font-display text-xl text-white leading-tight tracking-tight">LegalOS</div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-white/45 mt-0.5">
                JFPSL Legal AI
              </div>
            </div>
          )}
        </div>
        {!navCollapsed && (
          <button
            type="button"
            onClick={() => setNavCollapsed(true)}
            title="Collapse sidebar"
            aria-label="Collapse sidebar"
            className="hidden lg:flex w-8 h-8 items-center justify-center rounded-md text-white/45 hover:bg-white/10 hover:text-white transition-colors shrink-0"
          >
            ⟨
          </button>
        )}
      </div>

      <nav className="flex-1 px-2 py-4 space-y-0.5 overflow-y-auto scrollbar-thin" aria-label="Main">
        {visibleNav.map((item) => {
          const I = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              title={navCollapsed ? item.label : undefined}
              className={({ isActive }) =>
                classNames(
                  "flex items-center min-h-tap rounded-md text-subheadline font-medium",
                  "transition-all duration-fast ease-standard",
                  navCollapsed ? "justify-center px-2" : "gap-3 px-3",
                  isActive
                    ? "bg-white/15 text-white font-semibold shadow-[inset_3px_0_0_0_#9aaff0]"
                    : "text-white/75 hover:bg-white/10 hover:text-white",
                )
              }
            >
              <I className="w-5 h-5 shrink-0" aria-hidden />
              {!navCollapsed && <span className="truncate">{item.label}</span>}
            </NavLink>
          );
        })}
      </nav>

      {navCollapsed && (
        <div className="hidden lg:block px-2 py-3 border-t border-white/10">
          <button
            type="button"
            onClick={() => setNavCollapsed(false)}
            title="Expand sidebar"
            aria-label="Expand sidebar"
            className="w-full flex items-center justify-center min-h-tap rounded-md text-white/45 hover:bg-white/10 hover:text-white transition-colors"
          >
            ⟩
          </button>
        </div>
      )}
    </>
  );

  return (
    <div className="min-h-screen flex bg-bg-secondary">
      {mobileNavOpen && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-ink/50 animate-fade-in"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        className={classNames(
          "flex-shrink-0 flex flex-col surface-ink",
          "transition-[width,transform] duration-slow ease-decelerate overflow-hidden",
          "lg:relative lg:translate-x-0",
          navCollapsed ? "lg:w-[4.5rem]" : "lg:w-64",
          mobileNavOpen
            ? "fixed inset-y-0 left-0 z-50 w-64 translate-x-0 shadow-atelier"
            : "fixed inset-y-0 left-0 z-50 w-64 -translate-x-full lg:translate-x-0",
        )}
      >
        {sidebarContent}
      </aside>

      <div className="flex-1 flex flex-col min-w-0 lg:ml-0">
        <GlassBar
          as="header"
          className="flex-shrink-0 min-h-tap px-4 md:px-8 flex items-center justify-between gap-4 border-b border-separator/40 rounded-none bg-paper"
        >
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={toggleNav}
              title={navCollapsed ? "Show navigation" : "Hide navigation"}
              aria-label={navCollapsed ? "Show navigation" : "Hide navigation"}
              className="shrink-0 w-9 h-9 flex items-center justify-center rounded-md text-label-secondary hover:bg-bg-secondary hover:text-label transition-colors"
            >
              <span className="text-lg leading-none">{navCollapsed ? "☰" : "⟨"}</span>
            </button>
            <h2 className="font-display text-xl text-label truncate min-w-0 tracking-tight">
              {pageTitle(location.pathname)}
            </h2>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {!isLawGenie && !isMsaAutomation && (
              <span className="text-footnote text-label-tertiary hidden xl:block mr-1 tracking-wide">
                Corpus-bounded AI · Audit-logged
              </span>
            )}
            <UserMenu
              fullName={user.full_name}
              role={roleLabel(user.role)}
              initials={initials}
              onSignOut={signOut}
            />
          </div>
        </GlassBar>
        <main className="flex-1 overflow-y-auto bg-bg-secondary">
          <div
            className={classNames(
              "mx-auto",
              isFullBleed ? "h-full max-w-none px-0" : "max-w-7xl px-6 md:px-8 py-6",
            )}
          >
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
