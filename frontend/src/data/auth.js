// Real authentication against the Lens backend (Phase 1).
// Replaces the former hardcoded user list. Tokens live in localStorage; the
// backend issues a short-lived access token + a longer refresh token.

import { API_URL } from "@/config/env";

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

// Pydantic's own wording is accurate but reads like a stack trace to whoever is
// filling in the form ("String should have at least 8 characters"). Restate the
// cases the register form can actually produce; anything unmapped falls back to
// the server's text rather than a generic message, so a rule added backend-side
// still surfaces something true.
const FIELD_MESSAGES = {
  email: { value_error: "Enter a valid email address." },
  password: {
    string_too_short: "Password must be at least 8 characters.",
    string_too_long: "Password must be at most 128 characters.",
  },
  name: {
    string_too_short: "Enter your name.",
    string_too_long: "Name must be at most 255 characters.",
  },
};

// Turn a 422 `detail` list into { field: message }, so each input can show its
// own problem instead of one banner the user has to map back onto a field.
function validationFields(detail) {
  const fields = {};
  for (const item of detail) {
    // loc is ["body", "<field>"]; anything shorter is not field-level.
    const field = Array.isArray(item.loc) ? item.loc[1] : null;
    if (!field || fields[field]) continue; // first error per field wins
    fields[field] = FIELD_MESSAGES[field]?.[item.type] || item.msg || "Invalid value.";
  }
  return fields;
}

function fieldError(message, fields) {
  const err = new Error(message);
  err.fields = fields;
  return err;
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

// POST /auth/register, then sign the new account straight in.
//
// Registering does not authenticate: the endpoint returns the profile, not
// tokens. Delegating to login() here means "create account" leaves the user
// signed in, and the one place that establishes a session stays login().
//
// Throws on failure. The thrown Error carries a `fields` map ({email, password,
// name} -> message) whenever the server blamed specific fields, so the form can
// mark the offending input; `message` is always set for a form-level fallback.
export async function register({ email, password, name }) {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: email.trim().toLowerCase(),
      password,
      name: name.trim(),
    }),
  });

  if (!res.ok) {
    let detail = null;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* non-JSON body */
    }

    // 409: the email is taken. Only one field can be at fault, so point at it.
    if (res.status === 409) {
      const message =
        typeof detail === "string" ? detail : "An account with this email already exists.";
      throw fieldError(message, { email: message });
    }
    // 422: pydantic rejected the payload before any row was attempted.
    if (Array.isArray(detail)) {
      const fields = validationFields(detail);
      const first = Object.values(fields)[0];
      throw fieldError(first || "Please check the details you entered.", fields);
    }
    throw new Error(
      typeof detail === "string" ? detail : "Could not create the account. Please try again."
    );
  }

  return login(email, password);
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
