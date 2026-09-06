import { FormEvent, useState } from "react";
import { useAuth } from "../app/AuthContext";
import { Button, FormField, Input } from "../components/ui";

/** GenAIForge Risk — marketing showcase sign-in. */
export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-hero">
        <div className="login-hero__brand">
          <span className="login-hero__mark" aria-hidden>
            G
          </span>
          <span>GenAIForge</span>
        </div>
        <h1>Risk intelligence that demonstrates production AI.</h1>
        <p>
          Showcase outsourcing classification, vendor due diligence, and enterprise risk
          scoring — built to show clients how GenAIForge ships governed AI workflows.
        </p>
        <ul className="login-hero__features">
          <li>Human-in-the-loop on every AI decision</li>
          <li>Immutable audit trail with evidence links</li>
          <li>Regulator-aligned outsourcing workflows</li>
        </ul>
      </div>

      <div className="login-form-wrap">
        <div className="login-card">
          <h2>Sign in</h2>
          <p>Enter your demo account email and password to continue.</p>
          <form className="form-grid" onSubmit={handleLogin}>
            <FormField label="Email">
              <Input
                type="email"
                value={email}
                autoComplete="username"
                placeholder="demo@genaiforge.local"
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </FormField>
            <FormField label="Password">
              <Input
                type="password"
                value={password}
                autoComplete="current-password"
                placeholder="••••••••"
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </FormField>
            {error && (
              <p className="login-error" role="alert">
                {error}
              </p>
            )}
            <Button variant="primary" size="lg" type="submit" disabled={loading}>
              {loading ? "Signing in…" : "Enter GenAIForge Risk"}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
