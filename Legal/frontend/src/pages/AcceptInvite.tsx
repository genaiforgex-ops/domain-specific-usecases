import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { LawGenieMark } from "@/components/Icons";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api } from "@/lib/api";
import { applyTokenResponse } from "@/lib/session";
import type { InviteTokenInfo } from "@/types";

export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";

  const [info, setInfo] = useState<InviteTokenInfo | null>(null);
  const [checking, setChecking] = useState(true);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) {
      setInfo({ valid: false, email: null, full_name: null, detail: "No invite token provided." });
      setChecking(false);
      return;
    }
    api
      .validateInvite(token)
      .then(setInfo)
      .catch((e) =>
        setInfo({ valid: false, email: null, full_name: null, detail: (e as Error).message }),
      )
      .finally(() => setChecking(false));
  }, [token]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.acceptInvite(token, password);
      // Session cookie was set by the response — nothing to store client-side.
      applyTokenResponse(res);
      window.location.href = "/";
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex relative animate-fade-in">
      <div className="absolute top-4 right-4 z-20">
        <ThemeToggle />
      </div>

      <div className="hidden lg:flex lg:w-[48%] flex-col justify-between p-12 xl:p-16 surface-ink atelier-grain relative">
        <div className="absolute inset-0 pointer-events-none atelier-orb" aria-hidden />
        <div>
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-white/10 ring-1 ring-white/20 text-white mb-8 animate-scale-in">
            <LawGenieMark className="w-8 h-8" />
          </div>
          <p className="text-caption uppercase tracking-[0.22em] text-white/50 mb-6 animate-slide-up">
            JFPSL Legal AI
          </p>
          <h1 className="font-display text-[3.25rem] xl:text-[3.75rem] leading-[1.05] tracking-tight text-white max-w-md animate-slide-up">
            LegalOS
          </h1>
          <p className="mt-6 text-lg text-white/70 leading-relaxed max-w-sm animate-slide-up">
            Activate your invite and join the JFPSL legal workspace.
          </p>
        </div>
        <p className="text-caption text-white/40">Internal use · Jio Finance Platform Ltd.</p>
      </div>

      <div className="flex-1 flex items-center justify-center p-6 sm:p-10 bg-bg-secondary">
        <div className="w-full max-w-[420px] animate-slide-up">
          <div className="lg:hidden mb-10 text-center">
            <h1 className="font-display text-4xl text-label tracking-tight">LegalOS</h1>
            <p className="mt-2 text-subheadline text-label-secondary">Accept your invite</p>
          </div>

          <div className="surface-paper rounded-xl border border-separator/40 shadow-atelier px-7 py-8 sm:px-8 sm:py-9">
            {checking ? (
              <p className="text-subheadline text-label-secondary py-6 text-center">
                Checking your invite…
              </p>
            ) : !info?.valid ? (
              <div className="py-2 text-center">
                <h2 className="font-display text-2xl text-label mb-2">Invite not valid</h2>
                <p className="text-subheadline text-label-secondary mb-6">
                  {info?.detail ??
                    "This invite link is invalid or has expired — ask an admin to resend it."}
                </p>
                <Link to="/login">
                  <Button variant="secondary" className="w-full">
                    Go to sign in
                  </Button>
                </Link>
              </div>
            ) : (
              <>
                <h2 className="font-display text-2xl text-label tracking-tight">Set your password</h2>
                <p className="text-subheadline text-label-secondary mt-1.5">
                  Welcome{info.full_name ? `, ${info.full_name.split(" ")[0]}` : ""}! Activate{" "}
                  {info.email ?? "your account"}.
                </p>
                <form className="mt-7 space-y-4" onSubmit={onSubmit}>
                  <Input
                    label="New password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                    placeholder="At least 8 characters"
                  />
                  <Input
                    label="Confirm password"
                    type="password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    required
                    autoComplete="new-password"
                  />
                  {error && (
                    <div
                      className="rounded-md bg-error/10 border border-error/20 px-4 py-3 text-subheadline text-error"
                      role="alert"
                    >
                      {error}
                    </div>
                  )}
                  <Button type="submit" className="w-full" disabled={submitting}>
                    {submitting ? "Activating…" : "Activate account"}
                  </Button>
                </form>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
