import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/globals.css";
import "./styles/lens.css";
// After lens.css: the admin panel reuses storefront classes (.chip, .pager,
// .order-status) and adds modifiers that must win over the base rules.
import "./styles/admin.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
