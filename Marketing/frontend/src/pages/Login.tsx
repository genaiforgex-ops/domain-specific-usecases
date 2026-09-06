import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { AlertCircle, ShieldCheck, Sparkles, Workflow, Wand2 } from 'lucide-react';
import { useApp } from '../state/AppContext';
import { ApiError } from '../lib/api';
import { ThemeToggle } from '../components/ui/ThemeToggle';
import { Button } from '../components/ui/Button';
import { AmbientBackground } from '../components/layout/AmbientBackground';
import { APP_NAME, APP_TAGLINE } from '../lib/brand';

const HIGHLIGHTS = [
  { icon: Wand2, title: 'Generative campaigns', body: 'Draft copy and creative in one guided flow.' },
  { icon: Workflow, title: 'Staged review pipeline', body: 'From brief to launch with gates you control.' },
  { icon: ShieldCheck, title: 'Role-based access', body: 'Each seat sees only what their role ships.' },
];

export default function Login() {
  const { login } = useApp();
  const nav = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
      nav('/', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Sign-in failed. Check your email and password.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-2">
      <aside
        className="relative hidden lg:flex flex-col justify-between overflow-hidden p-12 text-white"
        style={{
          background:
            'radial-gradient(120% 80% at 10% 0%, rgba(184,149,108,0.35) 0%, transparent 55%), linear-gradient(155deg, #0B0C10 0%, #14161C 48%, #1A1520 100%)',
        }}
      >
        <span className="pointer-events-none absolute -top-24 -left-16 h-80 w-80 rounded-full bg-[#B8956C]/25 blur-3xl" aria-hidden />
        <span className="pointer-events-none absolute -bottom-28 -right-10 h-96 w-96 rounded-full bg-[#5B8A9A]/20 blur-3xl" aria-hidden />
        <span
          className="watermark watermark--float text-[14vw] bottom-6 -right-4 !text-white !opacity-[0.06] font-display"
          aria-hidden
        >
          GenAIForge
        </span>

        <div className="relative z-10 flex items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#B8956C]/25 ring-1 ring-inset ring-[#D4B896]/40 backdrop-blur">
            <Sparkles size={18} className="text-[#D4B896]" />
          </span>
          <span className="font-display text-callout font-semibold tracking-tight">{APP_NAME}</span>
        </div>

        <div className="relative z-10 max-w-md">
          <h2 className="font-display text-large-title font-bold leading-tight tracking-tight">
            Showcase production AI that ships campaigns.
          </h2>
          <p className="mt-4 text-body text-white/70">{APP_TAGLINE}</p>
        </div>

        <ul className="relative z-10 space-y-4">
          {HIGHLIGHTS.map(({ icon: Icon, title, body }) => (
            <li key={title} className="flex items-start gap-3.5">
              <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white/10 ring-1 ring-inset ring-white/15">
                <Icon size={17} className="text-[#D4B896]" />
              </span>
              <div>
                <p className="text-subheadline font-semibold">{title}</p>
                <p className="text-footnote text-white/65">{body}</p>
              </div>
            </li>
          ))}
        </ul>
      </aside>

      <main className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10 lg:min-h-0">
        <div className="absolute top-4 right-4 z-10">
          <ThemeToggle />
        </div>
        <div className="lg:hidden">
          <AmbientBackground />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', stiffness: 240, damping: 28 }}
          className="relative z-10 w-full max-w-sm"
        >
          <div className="mb-6 flex items-center justify-center gap-2.5 lg:hidden">
            <span
              className="grid h-9 w-9 place-items-center rounded-xl text-white"
              style={{ background: 'var(--color-accent)' }}
            >
              <Sparkles size={18} />
            </span>
            <span className="font-display text-callout font-semibold tracking-tight">{APP_NAME}</span>
          </div>

          <div className="mb-7 flex flex-col items-center text-center lg:items-start lg:text-left">
            <h1 className="font-display text-title-1 font-bold tracking-tight text-sheen">Welcome back</h1>
            <p className="mt-1.5 text-subheadline text-label-secondary">
              Sign in with your GenAIForge account.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-separator bg-bg-tertiary p-5 shadow-card">
            <label className="block space-y-1.5">
              <span className="text-caption font-medium text-label-secondary">Email</span>
              <input
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-separator bg-bg px-3 py-2.5 text-subheadline text-label outline-none focus-ring"
                placeholder="pl@genaiforge.in"
              />
            </label>
            <label className="block space-y-1.5">
              <span className="text-caption font-medium text-label-secondary">Password</span>
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-separator bg-bg px-3 py-2.5 text-subheadline text-label outline-none focus-ring"
                placeholder="••••••••"
              />
            </label>

            {error && (
              <p className="flex items-center gap-1.5 text-footnote text-error" role="alert">
                <AlertCircle size={14} className="shrink-0" /> {error}
              </p>
            )}

            <Button type="submit" size="lg" className="w-full font-medium" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </Button>

            <p className="flex items-center justify-center gap-1.5 pt-1 text-caption text-label-tertiary">
              <ShieldCheck size={13} /> Role-based access for demo seats
            </p>
          </form>
        </motion.div>
      </main>
    </div>
  );
}
