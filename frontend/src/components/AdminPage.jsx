import { useState } from "react";
import AdminInventory from "@/components/admin/AdminInventory";
import AdminOrders from "@/components/admin/AdminOrders";
import AdminOverview from "@/components/admin/AdminOverview";
import AdminProducts from "@/components/admin/AdminProducts";
import AdminUsers from "@/components/admin/AdminUsers";
import ThemeToggle from "@/components/ThemeToggle";
import { SITE_NAME } from "@/config/site";

// Tab switching is a piece of state and a lookup, not a router: AGENTS.md rules
// out frameworks beyond React, and App.jsx already routes top-level views the
// same way. The trade is no deep-linking — /admin/orders is not a URL, so a
// refresh lands back on Overview.
const TABS = [
  { id: "overview", label: "Overview", Component: AdminOverview },
  { id: "orders", label: "Orders", Component: AdminOrders },
  { id: "inventory", label: "Inventory", Component: AdminInventory },
  { id: "products", label: "Products", Component: AdminProducts },
  { id: "users", label: "Users", Component: AdminUsers },
];

export default function AdminPage({ user, onBack, theme, onToggleTheme }) {
  const [tab, setTab] = useState("overview");
  const active = TABS.find((t) => t.id === tab) ?? TABS[0];
  const Panel = active.Component;

  return (
    <div className="lens-app">
      <header className="top-nav">
        <div className="brand">
          <span className="brand-icon">?</span>
          {SITE_NAME}
          <span className="admin-badge">Admin</span>
        </div>
        <div className="nav-actions">
          <span className="user-greeting">{user?.name}</span>
          <button type="button" className="cart-btn" onClick={onBack}>
            ← Back to store
          </button>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </header>

      <div className="admin-page">
        {/* role=tablist so the panel switcher is navigable and announced as
            tabs, which is what it behaves like even without a router. */}
        <nav className="admin-tabs" role="tablist" aria-label="Admin sections">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              id={`admin-tab-${t.id}`}
              aria-selected={t.id === tab}
              aria-controls={`admin-panel-${t.id}`}
              className={`admin-tab${t.id === tab ? " active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>

        {/* Keyed on the tab id so switching tabs unmounts the old panel
            instead of leaving its stale rows on screen while the new one
            fetches. Each panel owns its own loading state. */}
        <section
          key={active.id}
          role="tabpanel"
          id={`admin-panel-${active.id}`}
          aria-labelledby={`admin-tab-${active.id}`}
          className="admin-panel"
        >
          <Panel currentUser={user} />
        </section>
      </div>
    </div>
  );
}
