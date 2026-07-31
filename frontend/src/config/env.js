// Resolves the backend API base URL, in one place.
//
// api.js and auth.js both used to carry their own copy of this expression, so a
// deployment could configure one and miss the other and only find out when a
// specific screen failed.
//
// Vite inlines VITE_* at build time, so this is decided when the bundle is
// built, not when it runs. A production bundle built without VITE_API_URL would
// otherwise silently point every request at the visitor's own machine — which
// looks exactly like "the backend is down" from the browser, and perfectly
// healthy from the server, so it is the kind of mistake that survives a long
// time. Failing here makes it a loud error at startup instead.
const configured = import.meta.env.VITE_API_URL;

if (import.meta.env.PROD && !configured) {
  throw new Error(
    "VITE_API_URL is not set. A production build must be given the public API " +
      "origin at build time — see frontend/.env.example."
  );
}

export const API_URL = configured ?? "http://localhost:8000";
