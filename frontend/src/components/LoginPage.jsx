import { useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import { SITE_NAME } from "@/config/site";

export default function LoginPage({ onLogin, theme, onToggleTheme }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    document.body.classList.add("login-active");
    return () => document.body.classList.remove("login-active");
  }, []);

  const handleSubmit = (event) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    const session = onLogin(email, password);
    setSubmitting(false);

    if (!session) {
      setError("Invalid email or password. Try the demo credentials below.");
    }
  };

  const fillDemo = () => {
    setEmail("demo@lens.app");
    setPassword("demo123");
    setError("");
  };

  return (
    <div className="login-shell">
      <div className="login-window">
        <header className="login-titlebar">
          <div className="window-controls" aria-hidden="true">
            <span className="dot dot-close" />
            <span className="dot dot-min" />
            <span className="dot dot-max" />
          </div>
          <span className="window-title">{SITE_NAME} — Sign in</span>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </header>

        <div className="login-layout">
          <aside className="login-brand-panel">
            <div className="brand">
              <span className="brand-icon">?</span>
              {SITE_NAME}
            </div>
            <p className="hero-kicker">Visual discovery</p>
            <h2>
              Your workspace,
              <br />
              <em>one sign-in away.</em>
            </h2>
            <p className="login-brand-copy">
              Access visual search, saved looks, and your full catalog from the desktop app.
            </p>
            <ul className="login-features">
              <li>AI image + text search</li>
              <li>Saved searches &amp; history</li>
              <li>Compare up to 4 products</li>
            </ul>
            <div className="login-preview" aria-hidden="true">
              <div className="preview-card preview-card-a" />
              <div className="preview-card preview-card-b" />
              <div className="preview-chip">94% match</div>
            </div>
          </aside>

          <section className="login-panel">
            <form className="login-form" onSubmit={handleSubmit}>
              <p className="hero-kicker">Welcome back</p>
              <h1>
                Sign in to your
                <br />
                <em>discovery dashboard.</em>
              </h1>
              <p className="login-subtitle">
                Use your account to access visual search, saved looks, and catalog tools.
              </p>

              <div className="login-fields">
                <label>
                  Email
                  <input
                    type="email"
                    autoComplete="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </label>
                <label>
                  Password
                  <input
                    type="password"
                    autoComplete="current-password"
                    placeholder="Enter password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                </label>
              </div>

              {error ? <p className="login-error" role="alert">{error}</p> : null}

              <button type="submit" className="login-submit" disabled={submitting}>
                {submitting ? "Signing in…" : "Sign in"}
              </button>

              <div className="login-demo">
                <p>Demo account</p>
                <p className="login-demo-creds">
                  <code>demo@lens.app</code>
                  <span aria-hidden="true"> · </span>
                  <code>demo123</code>
                </p>
                <button type="button" className="chip button-chip" onClick={fillDemo}>
                  Use demo credentials
                </button>
              </div>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
