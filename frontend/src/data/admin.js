// Admin API client (Phase 4, step 10). Covers the /admin surface built in
// steps 5-9: orders, products, inventory, users and analytics.
//
// Separate from api.js so the storefront client does not carry calls it never
// makes, but it reuses that module's getJSON/sendJSON — those hold the auth
// header and the refresh-on-401 retry, and a second copy would drift.
//
// Every route here 403s for a non-admin. The UI never shows the admin area to
// one (App gates on session.is_admin), but the gate that matters is the
// server's; this module assumes nothing about who is calling.

import { getJSON, sendJSON } from "@/data/api";

// --- Analytics (step 9) ----------------------------------------------------
// `window` is {start, end} as YYYY-MM-DD, or omitted for the server's default
// last-30-days.
export function analyticsOverview(window) {
  return getJSON("/admin/analytics/overview", window);
}

export function analyticsRevenue(window, bucket = "day") {
  return getJSON("/admin/analytics/revenue", { ...window, bucket });
}

export function analyticsOrders(window) {
  return getJSON("/admin/analytics/orders", window);
}

export function analyticsProducts(window, metric = "revenue", limit = 10) {
  return getJSON("/admin/analytics/products", { ...window, metric, limit });
}

export function analyticsFulfilment(window) {
  return getJSON("/admin/analytics/fulfilment", window);
}

export function analyticsCustomers(window) {
  return getJSON("/admin/analytics/customers", window);
}

// --- Orders (step 5) -------------------------------------------------------
export function adminListOrders(params) {
  return getJSON("/admin/orders", params);
}

export function adminSetOrderStatus(orderId, toStatus, note) {
  return sendJSON("POST", `/admin/orders/${orderId}/status`, {
    to_status: toStatus,
    note: note || undefined,
  });
}

// --- Products (step 6) -----------------------------------------------------
export function adminListProducts(params) {
  return getJSON("/admin/products", params);
}

export function adminCreateProduct(product) {
  return sendJSON("POST", "/admin/products", product);
}

export function adminUpdateProduct(productId, changes) {
  return sendJSON("PATCH", `/admin/products/${productId}`, changes);
}

// Soft delete: clears is_active, the row survives. Reversible by patching
// is_active back to true — the UI offers exactly that rather than pretending
// the product is gone.
export function adminDeactivateProduct(productId) {
  return sendJSON("DELETE", `/admin/products/${productId}`);
}

// --- Inventory (step 7) ----------------------------------------------------
export function inventoryList(params) {
  return getJSON("/admin/inventory", params);
}

export function inventorySummary(threshold) {
  return getJSON("/admin/inventory/summary", { threshold });
}

export function inventoryHistory(productId, limit = 50) {
  return getJSON(`/admin/inventory/${productId}/history`, { limit });
}

// `reason` is required by the server — the point of this route over a plain
// product PATCH is that stock changes are explained in the ledger.
export function inventoryAdjust(productId, { delta, setTo, reason }) {
  return sendJSON("POST", `/admin/inventory/${productId}/adjust`, {
    ...(delta !== undefined ? { delta } : { set_to: setTo }),
    reason,
  });
}

export function inventoryBulkAdjust(reason, lines) {
  return sendJSON("POST", "/admin/inventory/bulk-adjust", { reason, lines });
}

// --- Users (step 8) --------------------------------------------------------
export function adminListUsers(params) {
  return getJSON("/admin/users", params);
}

export function adminUsersSummary() {
  return getJSON("/admin/users/summary");
}

export function adminGetUser(userId) {
  return getJSON(`/admin/users/${userId}`);
}

// Enable/disable only. There is deliberately no promote/demote call here
// because there is no such endpoint — granting admin rights stays in
// promote_admin.py, off the network. See backend/users.py.
export function adminSetUserActive(userId, isActive, reason) {
  return sendJSON("POST", `/admin/users/${userId}/active`, {
    is_active: isActive,
    reason: reason || undefined,
  });
}
