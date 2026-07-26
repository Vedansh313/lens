import { useEffect } from "react";
import Dashboard from "@/components/Dashboard";
import LoginPage from "@/components/LoginPage";
import { SITE_NAME, SITE_TAGLINE } from "@/config/site";
import { login as apiLogin, logout as apiLogout, getCurrentUser } from "@/data/auth";
import { useLocalStorage } from "@/hooks/useLocalStorage";

export default function App() {
  const [session, setSession] = useLocalStorage("lens-session", null);
  const [theme, setTheme] = useLocalStorage("lens-theme", "light");

  useEffect(() => {
    document.body.dataset.theme = theme;
    document.title = `${SITE_NAME} — ${SITE_TAGLINE}`;
  }, [theme]);

  // On load, revalidate a stored session against the API: refresh the profile
  // if the token is still good, drop the session if it isn't. Network errors
  // are swallowed so a transient outage doesn't sign the user out.
  useEffect(() => {
    if (!session) return;
    getCurrentUser()
      .then((user) => setSession(user ?? null))
      .catch(() => {});
    // Run once on mount only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Async: awaits the real API. Throws on failure so LoginPage can surface the
  // server's message.
  const handleLogin = async (email, password) => {
    const user = await apiLogin(email, password);
    setSession(user);
    return user;
  };

  const handleLogout = async () => {
    await apiLogout();
    setSession(null);
  };

  if (!session) {
    return (
      <LoginPage
        onLogin={handleLogin}
        theme={theme}
        onToggleTheme={() => setTheme((prev) => (prev === "dark" ? "light" : "dark"))}
      />
    );
  }

  return (
    <Dashboard
      user={session}
      theme={theme}
      onToggleTheme={() => setTheme((prev) => (prev === "dark" ? "light" : "dark"))}
      onLogout={handleLogout}
    />
  );
}
