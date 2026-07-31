# Phase 5 — step map

Phases 0–4 are complete: database, auth, catalog/cart/wishlist, checkout/
payments/orders, order management/admin. Phase 5 is three steps.

**Ordering principle.** Deployment comes second, not last. It is the only item
that changes *how everything after it is built* — env config, secrets,
migrations, asset hosting — so anything shipped before it has to be re-tested
after it. Hardening comes first because deploying the current configuration
would expose known problems (`allow_origins=["*"]`, no login rate limit, a weak
admin password). Recommendations come last because they are the only step that
needs no new infrastructure, which makes them the safe thing to cut if time runs
out.

**Cut from this phase** (deferred, not cancelled): email infrastructure with
verification / forgot-password / OAuth; order notifications; reviews and
ratings. See "What the cuts cost you" at the end — one consequence needs
handling inside step 1.

---

## Step 1 — Pre-deploy hardening

Code and config only, no infrastructure. Every item is something that is wrong
right now, not a precaution.

1. **CORS allowlist.** `server.py:182` is `allow_origins=["*"]`. Drive it from
   an env var; localhost stays allowed in dev.
2. **Rate-limit `/auth/login` and `/auth/register`.** There is none today.
   Registration is public by design, which makes both endpoints reachable by
   anyone once deployed.
3. **Set a strong admin password directly via script.** The sole admin
   (`yvedansh89@gmail.com`) currently has a trivial password. Extend
   `promote_admin.py`, or add a sibling script, to set a password hash from the
   command line — same reasoning as promotion itself: it must not be reachable
   over the network.

   > **Self-service password reset stays unavailable this phase.** It was going
   > to arrive with the email provider in the cut step 3. Until that ships,
   > changing any password requires shell access to the machine running the
   > database, and users who forget theirs cannot recover the account
   > themselves. This script is the whole password-management story for now.
4. **Env-driven URLs.** `IMAGE_BASE_URL` and `VITE_API_URL` currently default to
   `http://localhost:8000`. Both must come from the environment in production.
5. **Rotate `JWT_SECRET` for production.** Rotating invalidates every issued
   access and refresh token, so it has to happen before there are real users,
   not after.
6. **Document the admin bootstrap.** A fresh database has **no admin at all**;
   `promote_admin.py` needs shell access. This is deliberate, and it means the
   admin handover must be repeated against the production database.
7. **Fix the README.** It still describes the Phase 0 frontend ("HTML, CSS,
   JavaScript"), has corrupt `u p d a t e` text at the end, and documents no
   backend setup whatsoever.

---

## Step 2 — Deploy

### Prerequisite: a GitHub remote

`git remote -v` is currently empty; every commit exists on one disk. This is now
a **hard prerequisite, not a backup measure** — deploy platforms build from a Git
remote, so there is no deployment without one. Both setup commands are
interactive and must be run by hand:

```
winget install GitHub.cli
gh auth login
```

### What actually ships

`product_metadata.json` and `product_index_baseline_backup.faiss` are **not**
runtime dependencies — metadata has been served from Postgres since `f235ba3`,
and the backup index is a backup. Real payload is 1.33 GB:

| Asset | Size | Notes |
| --- | --- | --- |
| `ai/models/clip_finetuned.pt` | 605 MB | gitignored; must reach the box out of band |
| `ai/models/product_index.faiss` | 91 MB | gitignored |
| `backend/images/` | 637 MB, 44,441 files | gitignored; static, cacheable |

### The binding constraint is RAM, not disk

Measured on this machine: loading CLIP peaks at **~1.75 GB RSS**, settling to
~514 MB once warm. Every free PaaS tier is 512 MB, so the app cannot boot on one
*regardless of how the assets are stored*. Instance size is the decision;
storage strategy follows from it.

### Chosen approach: VPS with persistent disk

Rejected alternatives, and why:

- **Object storage + fetch on startup.** Solves disk, not RAM, and still needs a
  paid instance. Adds a ~700 MB download to every cold boot, which on a tier
  that spins down when idle makes the first search after a quiet period take
  minutes.
- **Reducing the catalogue to a subset.** The only option that costs something
  real — the full 44,419-product index is the substance of the project — and it
  does not help, because the 605 MB of CLIP weights are fixed no matter how many
  products exist. It would also require a re-index, a re-seed, and a
  `faiss_index` renumber, all of which `verify_alignment.py` would rightly fail
  until done correctly.

With a persistent disk, no object storage is needed at all: nginx serves the
images off local disk, so there is no egress bill and no fetch-on-boot.

Candidates: Hetzner CX22 (4 GB RAM, 40 GB disk, ~€4/mo) as the plan. Oracle
Cloud Always Free (ARM Ampere, 4 vCPU / 24 GB) would run this at zero cost and
ARM64 torch wheels exist, but capacity and signup are unreliable — treat it as a
bonus, not the plan. Prices need confirming; they are not from a live source.

### Remaining work in this step

- Managed or same-box Postgres, then `alembic upgrade head`
- Asset delivery to the box (rsync/scp, or a bucket fetched once at provision)
- Repeat the admin handover against the production database
- Frontend static build served by the same nginx
- TLS, a process manager, and a deploy path from the Git remote

---

## Step 3 — Recommendations

Deliberately last: it needs no new infrastructure, so it is the safe cut if
step 2 overruns.

The pieces already exist. Product embeddings are in the FAISS index, and
`recently_viewed` has been populated since Phase 2 step 6.
`RecommendationCarousel.jsx` exists as a shell.

- **"Similar items"** on the product modal — a FAISS query using the product's
  own vector, excluding itself.
- **"Because you viewed"** on the dashboard — driven by `recently_viewed`.
- Admin-created products have no CLIP vector (`faiss_index >= index.ntotal`) and
  can never appear in vector-based results. `admin.py` already exposes
  `image_searchable` for exactly this distinction; recommendations must respect
  it rather than assuming every product is reachable.
- No router and no charting library, per `AGENTS.md`.

---

## What the cuts cost you

- **No password reset for anyone but you.** Step 1's script covers the admin via
  shell access. A regular user who forgets their password has no route back into
  their account until the email provider ships.
- **No email verification.** Registration is open and unverified, so accounts can
  be created against addresses the registrant does not own.
- **No order emails.** The lifecycle events exist and are recorded; nothing is
  sent to the customer.
- **No reviews.** Product pages stay catalogue-only.

None of these block deployment. All of them are the first candidates for Phase 6.
