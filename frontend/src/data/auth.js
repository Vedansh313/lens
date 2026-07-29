// Real authentication against the Lens backend (Phase 1).
// Replaces the former hardcoded user list. Tokens live in localStorage; the
// backend issues a short-lived access token + a longer refresh token.

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const ACCESS_KEY = "lens-access-token";
const REFRESH_KEY = "lens-refresh-token";

// Dispatched when a refresh token we *had* is rejected — i.e. the session died
// mid-use rather than the user never having been signed in. App listens for it
// and drops the session, so an expired refresh token sends the user to the
// login screen instead of leaving a signed-in-looking UI where every call 401s.
export const AUTH_EXPIRED_EVENT = "lens-auth-expired";

export function getAccessToken() {
  return localStorage.getItem(ACCESS_KEY);
}

function setTokens({ access_token, refresh_token }) {
  if (access_token) localStorage.setItem(ACCESS_KEY, access_token);
  if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
}

function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

// Pull a human-readable message out of a FastAPI error body. `detail` is a
// string for our raised HTTPExceptions and a list for 422 validation errors.
async function errorMessage(res, fallback) {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* non-JSON body */
  }
  return fallback;
}

// Exchange the stored refresh token for a fresh access token. Returns true on
// success. Used transparently by getCurrentUser and by api.js's authed fetch
// wrapper when the access token expires mid-session.
//
// On a *rejected* refresh token the session is unrecoverable, so tokens are
// dropped and AUTH_EXPIRED_EVENT is fired. Absence of a refresh token is not
// an expiry — there was no session to lose — so it returns false quietly.
// A network failure also stays quiet: a transient outage must not sign the
// user out (same reasoning as App's mount-time revalidation).
export async function refreshAccessToken() {
  const refresh_token = localStorage.getItem(REFRESH_KEY);
  if (!refresh_token) return false;
  let res;
  try {
    res = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    });
  } catch {
    return false;
  }
  if (!res.ok) {
    clearTokens();
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    return false;
  }
  setTokens(await res.json());
  return true;
}

// POST /auth/login, store tokens, return the user profile.
// Throws an Error (with the server's message) on failure so the login form can
// display it.
export async function login(email, password) {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
  });
  if (!res.ok) {
    throw new Error(await errorMessage(res, "Invalid email or password."));
  }
  setTokens(await res.json());
  const user = await getCurrentUser();
  if (!user) throw new Error("Signed in, but the session could not be established.");
  return user;
}

// GET /auth/me for the current access token, refreshing once on a 401.
// Returns the user object, or null if there is no valid session. Network errors
// propagate (so callers can distinguish "logged out" from "server unreachable").
export async function getCurrentUser() {
  let token = getAccessToken();
  if (!token) return null;

  let res = await fetch(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 401) {
    if (!(await refreshAccessToken())) {
      clearTokens();
      return null;
    }
    res = await fetch(`${API_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${getAccessToken()}` },
    });
  }
  if (!res.ok) return null;
  return res.json();
}

// Best-effort server acknowledge, then drop the tokens locally. Logout is
// stateless server-side, so clearing the tokens is what actually ends the
// session on this device.
export async function logout() {
  const token = getAccessToken();
  if (token) {
    try {
      await fetch(`${API_URL}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {
      /* offline is fine — we still clear tokens below */
    }
  }
  clearTokens();
}
