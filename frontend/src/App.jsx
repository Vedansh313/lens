import { useEffect } from "react";
import Dashboard from "@/components/Dashboard";
import LoginPage from "@/components/LoginPage";
import { SITE_NAME, SITE_TAGLINE } from "@/config/site";
import { authenticate } from "@/data/auth";
import { useLocalStorage } from "@/hooks/useLocalStorage";

export default function App() {
  const [session, setSession] = useLocalStorage("lens-session", null);
  const [theme, setTheme] = useLocalStorage("lens-theme", "light");

  useEffect(() => {
    document.body.dataset.theme = theme;
    document.title = `${SITE_NAME} — ${SITE_TAGLINE}`;
  }, [theme]);

  const handleLogin = (email, password) => {
    const user = authenticate(email, password);
    if (!user) return null;
    setSession(user);
    return user;
  };

  const handleLogout = () => {
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
