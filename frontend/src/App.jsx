import { useEffect, useState } from "react";
import CartPage from "@/components/CartPage";
import CheckoutPage from "@/components/CheckoutPage";
import ConfirmationPage from "@/components/ConfirmationPage";
import Dashboard from "@/components/Dashboard";
import LoginPage from "@/components/LoginPage";
import { SITE_NAME, SITE_TAGLINE } from "@/config/site";
import { login as apiLogin, logout as apiLogout, getCurrentUser } from "@/data/auth";
import { useCart } from "@/hooks/useCart";
import { useLocalStorage } from "@/hooks/useLocalStorage";

export default function App() {
  const [session, setSession] = useLocalStorage("lens-session", null);
  const [theme, setTheme] = useLocalStorage("lens-theme", "light");
  const [view, setView] = useState("catalog");
  const [confirmedOrder, setConfirmedOrder] = useState(null);
  const cart = useCart();

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

  // Load the cart when signed in; clear it (via a 401) on sign-out.
  useEffect(() => {
    cart.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

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
    setView("catalog");
  };

  const toggleTheme = () => setTheme((prev) => (prev === "dark" ? "light" : "dark"));

  if (!session) {
    return <LoginPage onLogin={handleLogin} theme={theme} onToggleTheme={toggleTheme} />;
  }

  if (view === "cart") {
    return (
      <CartPage
        cart={cart.cart}
        onSetQuantity={cart.setQuantity}
        onRemove={cart.remove}
        onClear={cart.clear}
        onBack={() => setView("catalog")}
        onCheckout={() => setView("checkout")}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    );
  }

  if (view === "checkout") {
    return (
      <CheckoutPage
        onBack={() => setView("cart")}
        onPlaced={(order) => {
          setConfirmedOrder(order);
          cart.refresh();
          setView("confirmation");
        }}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    );
  }

  if (view === "confirmation") {
    return (
      <ConfirmationPage
        order={confirmedOrder}
        onDone={() => {
          setConfirmedOrder(null);
          setView("catalog");
        }}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    );
  }

  return (
    <Dashboard
      user={session}
      theme={theme}
      onToggleTheme={toggleTheme}
      onLogout={handleLogout}
      cartCount={cart.cart.item_count}
      onAddToCart={cart.add}
      onOpenCart={() => setView("cart")}
    />
  );
}
