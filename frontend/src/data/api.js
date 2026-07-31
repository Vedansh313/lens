// Central API client for the Lens backend (Phase 2).
// All catalog/search/cart/engagement calls go through here so auth headers and
// the base URL live in one place.

import { API_URL } from "@/config/env";
import { refreshAccessToken } from "@/data/auth";

function authHeaders() {
  const token = localStorage.getItem("lens-access-token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// fetch that transparently refreshes the access token once on a 401 and retries,
// so short-lived access tokens expiring mid-session don't break authed calls
// (cart, wishlist, recently-viewed). The retry re-applies the fresh auth header.
async function authedFetch(url, options = {}) {
  let res = await fetch(url, options);
  if (res.status === 401 && (await refreshAccessToken())) {
    res = await fetch(url, { ...options, headers: { ...options.headers, ...authHeaders() } });
  }
  return res;
}

function buildUrl(path, params) {
  const url = new URL(`${API_URL}${path}`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, value);
      }
    }
  }
  return url;
}

// Exported for @/data/admin, which is a separate module so the storefront
// client does not grow an admin surface it never calls. Both share the auth
// header + token-refresh behaviour above; there must not be a second copy of it.
export async function getJSON(path, params) {
  const res = await authedFetch(buildUrl(path, params), {
    headers: { "ngrok-skip-browser-warning": "true", ...authHeaders() },
  });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return res.json();
}

export async function sendJSON(method, path, body) {
  const res = await authedFetch(`${API_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "ngrok-skip-browser-warning": "true",
      ...authHeaders(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    // Surface the server's message (e.g. "Payment was declined", coupon/stock
    // errors) so callers can show it, not a bare status code.
    let detail;
    try {
      const parsed = await res.json();
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail || `${method} ${path} -> ${res.status}`);
  }
  return res.json();
}

// Normalize a backend product (catalog OR search shape) into the shape the
// existing UI components read. `match`/`score` are only present on search hits.
// `brand` is derived from the name for display only — there is no brand field
// in the dataset (the brand FACET was intentionally dropped).
export function mapProduct(p) {
  return {
    id: p.id,
    name: p.name,
    brand: (p.name || "").split(" ")[0],
    category: p.category,
    subCategory: p.subCategory,
    color: p.colour,
    gender: p.gender,
    price: p.price,
    available: p.inStock,
    image: p.image_url,
    match: p.match,
    score: p.score,
    quantity: p.quantity,
    subtotal: p.subtotal,
  };
}

// ---- Catalog -------------------------------------------------------------
export function fetchProducts(params) {
  return getJSON("/products", params);
}

export function fetchProduct(id) {
  return getJSON(`/products/${id}`);
}

export function fetchCategories() {
  return getJSON("/categories");
}

export async function fetchAutocomplete(q, limit = 8) {
  if (!q || q.trim().length < 2) return { suggestions: [] };
  return getJSON("/autocomplete", { q: q.trim(), limit });
}

// ---- Hybrid search (image + text + metadata + catalog filters) -----------
export async function hybridSearch({ query, imageFile, filters = {}, alpha = 0.7, topK = 48 }) {
  const form = new FormData();
  if (imageFile) form.append("image", imageFile);
  if (query) form.append("query", query);
  form.append("alpha", String(alpha));
  form.append("top_k", String(topK));
  const map = {
    category: filters.category,
    colour: filters.colour,
    gender: filters.gender,
    min_price: filters.minPrice,
    max_price: filters.maxPrice,
    in_stock: filters.inStock,
  };
  for (const [key, value] of Object.entries(map)) {
    if (value !== undefined && value !== null && value !== "") form.append(key, String(value));
  }
  const res = await authedFetch(`${API_URL}/api/v1/hybrid-search`, {
    method: "POST",
    body: form,
    headers: { "ngrok-skip-browser-warning": "true", ...authHeaders() },
  });
  if (!res.ok) throw new Error(`hybrid-search -> ${res.status}`);
  return res.json();
}

// ---- Cart (auth) — every call returns the full updated cart ---------------
export function getCart() {
  return getJSON("/cart");
}
export function addToCart(productId, quantity = 1) {
  return sendJSON("POST", "/cart", { product_id: productId, quantity });
}
export function updateCartItem(productId, quantity) {
  return sendJSON("PATCH", `/cart/${productId}`, { quantity });
}
export function removeCartItem(productId) {
  return sendJSON("DELETE", `/cart/${productId}`);
}
export function clearCart() {
  return sendJSON("DELETE", "/cart");
}

// ---- Wishlist + recently viewed (auth) ------------------------------------
export function getWishlist() {
  return getJSON("/wishlist");
}
export function addWishlist(productId) {
  return sendJSON("POST", "/wishlist", { product_id: productId });
}
export function removeWishlist(productId) {
  return sendJSON("DELETE", `/wishlist/${productId}`);
}
export function getRecentlyViewed(limit = 12) {
  return getJSON("/recently-viewed", { limit });
}
export function recordView(productId) {
  return sendJSON("POST", "/recently-viewed", { product_id: productId });
}

// ---- Checkout / orders / payments (auth) ----------------------------------
export function getAddresses() {
  return getJSON("/addresses");
}
export function createAddress(address) {
  return sendJSON("POST", "/addresses", address);
}
export function getQuote(couponCode) {
  return getJSON("/checkout/quote", couponCode ? { coupon_code: couponCode } : undefined);
}
export function createOrder(payload) {
  return sendJSON("POST", "/checkout", payload);
}
export function payOrder(orderId, payload) {
  return sendJSON("POST", `/orders/${orderId}/pay`, payload);
}
export function getInvoice(orderId) {
  return getJSON(`/orders/${orderId}/invoice`);
}

// ---- Order history (auth) -------------------------------------------------
// listOrders returns { orders: [...] } — summary rows, newest first.
// getOrder returns the full order (items, shipping_address, totals, payments).
export function listOrders() {
  return getJSON("/orders");
}
export function getOrder(orderId) {
  return getJSON(`/orders/${orderId}`);
}

// Lifecycle actions. Both return the full updated order (same shape as
// getOrder), so the caller can drop the response straight into its detail
// cache. The server rejects an illegal move with a 409 whose message is
// surfaced by sendJSON.
export function cancelOrder(orderId, reason) {
  return sendJSON("POST", `/orders/${orderId}/cancel`, { reason: reason || null });
}
export function requestReturn(orderId, reason) {
  return sendJSON("POST", `/orders/${orderId}/return`, { reason: reason || null });
}
