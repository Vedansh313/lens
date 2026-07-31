import { useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import { SITE_NAME } from "@/config/site";

// One page, two modes. A separate RegisterPage would need App-level view state
// to route between them, and AGENTS.md rules out a router — the two forms share
// every field but one, so a mode flag is less machinery than the alternative.
const COPY = {
  signin: {
    windowTitle: "Sign in",
    kicker: "Welcome back",
    heading: ["Sign in to your", "discovery dashboard."],
    subtitle: "Use your account to access visual search, saved looks, and catalog tools.",
    submit: "Sign in",
    pending: "Signing in…",
    switchPrompt: "New to " + SITE_NAME + "?",
    switchAction: "Create an account",
  },
  register: {
    windowTitle: "Create account",
    kicker: "Get started",
    heading: ["Create your", "discovery account."],
    subtitle: "Your searches, saved looks, cart, and orders stay with the account.",
    submit: "Create account",
    pending: "Creating account…",
    switchPrompt: "Already have an account?",
    switchAction: "Sign in",
  },
};

export default function LoginPage({ onLogin, onRegister, theme, onToggleTheme }) {
  const [mode, setMode] = useState("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  // Per-field messages from the server, keyed by field name. Separate from
  // `error` so a 422 about the password does not also blank the email box.
  const [fieldErrors, setFieldErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const isRegister = mode === "register";
  const copy = COPY[mode];

  useEffect(() => {
    document.body.classList.add("login-active");
    return () => document.body.classList.remove("login-active");
  }, []);

  // Values survive the switch on purpose: the commonest reason to flip modes is
  // a 409 telling you the email is already registered, and retyping it to sign
  // in is busywork. Errors do not survive — they describe the other form.
  const switchMode = () => {
    setMode(isRegister ? "signin" : "register");
    setError("");
    setFieldErrors({});
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setFieldErrors({});
    setSubmitting(true);

    try {
      if (isRegister) {
        await onRegister({ email, password, name });
      } else {
        await onLogin(email, password);
      }
      // On success App swaps this page out for the Dashboard.
    } catch (err) {
      setFieldErrors(err?.fields || {});
      setError(err?.message || (isRegister ? "Could not create the account." : "Invalid email or password."));
    } finally {
      setSubmitting(false);
    }
  };

  // A field-level message replaces the form-level banner rather than duplicating
  // it — showing "Enter a valid email address." twice reads as two problems.
  const showBanner = error && Object.keys(fieldErrors).length === 0;

  return (
    <div className="login-shell">
      <div className="login-window">
        <header className="login-titlebar">
          <div className="window-controls" aria-hidden="true">
            <span className="dot dot-close" />
            <span className="dot dot-min" />
            <span className="dot dot-max" />
          </div>
          <span className="window-title">
            {SITE_NAME} — {copy.windowTitle}
          </span>
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
              <p className="hero-kicker">{copy.kicker}</p>
              <h1>
                {copy.heading[0]}
                <br />
                <em>{copy.heading[1]}</em>
              </h1>
              <p className="login-subtitle">{copy.subtitle}</p>

              <div className="login-fields">
                {isRegister && (
                  <label>
                    Name
                    <input
                      type="text"
                      autoComplete="name"
                      placeholder="Your name"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      aria-invalid={Boolean(fieldErrors.name)}
                      required
                    />
                    {fieldErrors.name && (
                      <span className="field-error" role="alert">{fieldErrors.name}</span>
                    )}
                  </label>
                )}
                <label>
                  Email
                  <input
                    type="email"
                    autoComplete="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    aria-invalid={Boolean(fieldErrors.email)}
                    required
                  />
                  {fieldErrors.email && (
                    <span className="field-error" role="alert">{fieldErrors.email}</span>
                  )}
                </label>
                <label>
                  Password
                  <input
                    type="password"
                    autoComplete={isRegister ? "new-password" : "current-password"}
                    placeholder={isRegister ? "At least 8 characters" : "Enter password"}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    aria-invalid={Boolean(fieldErrors.password)}
                    required
                  />
                  {fieldErrors.password ? (
                    <span className="field-error" role="alert">{fieldErrors.password}</span>
                  ) : (
                    isRegister && <span className="field-hint">At least 8 characters.</span>
                  )}
                </label>
              </div>

              {showBanner ? <p className="login-error" role="alert">{error}</p> : null}

              <button type="submit" className="login-submit" disabled={submitting}>
                {submitting ? copy.pending : copy.submit}
              </button>

              <p className="login-switch">
                {copy.switchPrompt}{" "}
                <button type="button" className="login-switch-btn" onClick={switchMode}>
                  {copy.switchAction}
                </button>
              </p>

            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
