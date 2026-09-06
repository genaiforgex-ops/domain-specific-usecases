import { useEffect, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { LawGenieMark } from "@/components/Icons";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { applyTokenResponse, consumeAuthMessage } from "@/lib/session";

// Stable per page-load, but distinct across separate loads (reloads, new
// tabs). Lets us tell "duplicate effect run within this same load" (React
// StrictMode double-invoke — must dedupe) apart from "marker left over from
// a previous, now-dead load whose exchange request got interrupted" (must
// retry, not silently give up).
const PAGE_LOAD_ID = typeof crypto !== "undefined" && crypto.randomUUID
  ? crypto.randomUUID()
  : `${Date.now()}_${Math.random()}`;

export function LoginPage() {
  const { user, login, loading } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Runtime, not build-time: fetched from the backend so one build artifact
  // is safely deployable to dev/uat/prod, and the button always matches what
  // the backend will actually accept (adding an env to _KEYCLOAK_SSO_ENVS on
  // the backend is the only change needed — nothing to rebuild here).
  const [ssoEnabled, setSsoEnabled] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.getConfig()
      .then((res) => setSsoEnabled(res.sso_enabled === true))
      .catch(() => setSsoEnabled(false));
  }, []);

  useEffect(() => {
    // ── 1. Handle Keycloak OIDC Authorization Code Callback ──
    // Not gated on the fetched ssoEnabled state here — an incoming code
    // should always be handed to the backend, which is the actual
    // enforcement point and 404s cleanly if SSO isn't active in this env.
    const code = searchParams.get("code");
    if (code) {
      const codeKey = `kc_code_${code}`;
      const existingMarker = sessionStorage.getItem(codeKey);
      if (existingMarker === PAGE_LOAD_ID) {
        // Duplicate effect run within this same page load (e.g. React
        // StrictMode double-invoke) — already being processed, skip.
        return;
      }
      // existingMarker from a *previous* page load means that attempt got
      // interrupted (e.g. a competing hard redirect aborted the request) —
      // safe and necessary to retry here rather than silently giving up.
      sessionStorage.setItem(codeKey, PAGE_LOAD_ID);

      const redirectUri = window.location.origin + window.location.pathname;
      window.history.replaceState({}, document.title, window.location.pathname);

      setSubmitting(true);
      setInfo("Authenticating via Jio SSO…");

      const authPromise = code.startsWith("sso_code_")
        ? api.exchangeSSOCode(code)
        : api.keycloakCallback(code, redirectUri);

      authPromise
        .then((res) => {
          // Session cookie was set by the response — nothing to store client-side.
          applyTokenResponse(res);
          window.location.replace("/");
        })
        .catch((err) => {
          setError(`SSO Login failed: ${err.message}`);
          setSubmitting(false);
        });
      return;
    }

    const ssoError = searchParams.get("error");
    if (ssoError) {
      setError(`SSO Login failed: ${ssoError}`);
      window.history.replaceState({}, document.title, window.location.pathname);
    }

    // ── 2. Handle Stored Auth Session Messages ──
    const stored = consumeAuthMessage();
    if (stored) {
      setInfo(stored);
      return;
    }
    if (searchParams.get("reason") === "session") {
      setInfo("Your session expired due to inactivity. Please sign in again.");
    }
  }, [searchParams]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center surface-ink atelier-grain text-white/70">
        Loading…
      </div>
    );
  }
  if (user) return <Navigate to="/" replace />;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const handleJioSSO = () => {
    window.location.href = "/api/auth/keycloak";
  };

  return (
    <div className="min-h-screen flex relative overflow-hidden">
      <div className="absolute top-4 right-4 z-20 animate-fade-in">
        <ThemeToggle />
      </div>

      {/* Full-bleed ink brand plane */}
      <div className="hidden lg:flex lg:w-[48%] flex-col justify-between p-12 xl:p-16 surface-ink atelier-grain relative">
        <div className="absolute inset-0 pointer-events-none atelier-orb" aria-hidden />
        <div>
          <div
            className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-white/10 ring-1 ring-white/20 text-white mb-8 animate-scale-in"
            style={{ animationDelay: "80ms" }}
          >
            <LawGenieMark className="w-8 h-8" />
          </div>
          <p
            className="text-caption uppercase tracking-[0.22em] text-white/50 mb-6 animate-slide-up"
            style={{ animationDelay: "120ms" }}
          >
            JFPSL Legal AI
          </p>
          <h1
            className="font-display text-[3.25rem] xl:text-[3.75rem] leading-[1.05] tracking-tight text-white max-w-md animate-slide-up"
            style={{ animationDelay: "200ms" }}
          >
            LegalOS
          </h1>
          <p
            className="mt-6 text-lg text-white/70 leading-relaxed max-w-sm animate-slide-up"
            style={{ animationDelay: "280ms" }}
          >
            Review contracts faster with AI you can trust — playbook-aligned, audit-ready.
          </p>
        </div>
        <p
          className="text-caption text-white/40 animate-fade-in"
          style={{ animationDelay: "450ms" }}
        >
          Internal use · Jio Finance Platform Ltd.
        </p>
      </div>

      {/* Paper sign-in */}
      <div className="flex-1 flex items-center justify-center p-6 sm:p-10 bg-bg-secondary">
        <div
          className="w-full max-w-[420px] animate-slide-up"
          style={{ animationDelay: "160ms" }}
        >
          <div className="lg:hidden mb-10 text-center">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-accent/10 text-accent mb-4">
              <LawGenieMark className="w-7 h-7" />
            </div>
            <h1 className="font-display text-4xl text-label tracking-tight">LegalOS</h1>
            <p className="mt-2 text-subheadline text-label-secondary">JFPSL Legal AI</p>
          </div>

          <div className="surface-paper rounded-xl border border-separator/40 shadow-atelier px-7 py-8 sm:px-8 sm:py-9 animate-scale-in">
            <h2 className="font-display text-2xl text-label tracking-tight">Welcome back</h2>
            <p className="text-subheadline text-label-secondary mt-1.5">
              Sign in to your workspace
            </p>

            <form className="mt-7 space-y-4" onSubmit={onSubmit}>
              <Input
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
              <Input
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
              {info && !error && (
                <div
                  className="rounded-md bg-warning/10 border border-warning/25 px-4 py-3 text-subheadline text-label"
                  role="status"
                >
                  {info}
                </div>
              )}
              {error && (
                <div
                  className="rounded-md bg-error/10 border border-error/20 px-4 py-3 text-subheadline text-error"
                  role="alert"
                >
                  {error}
                </div>
              )}
              <Button type="submit" className="w-full mt-1" disabled={submitting}>
                {submitting ? "Signing in…" : "Sign in"}
              </Button>
            </form>

            {/* SSO Divider + Button — shown only when the backend reports SSO active for this env */}
            {ssoEnabled && (
              <>
                <div className="relative my-5 flex items-center justify-center">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-separator/40"></div>
                  </div>
                  <span className="relative surface-paper px-3 text-[10px] uppercase tracking-widest font-bold text-label-tertiary">
                    Or authenticate via
                  </span>
                </div>

                <Button
                  type="button"
                  variant="secondary"
                  className="w-full py-2.5 text-accent border border-accent/30 hover:bg-accent/10 transition-all font-semibold"
                  onClick={handleJioSSO}
                  disabled={submitting}
                >
                  Login with Jio SSO
                </Button>
              </>
            )}

            <p className="mt-7 text-center text-caption text-label-tertiary">
              Invite-only · Contact your LegalOS administrator
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
