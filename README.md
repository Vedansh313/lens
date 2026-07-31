# Lens

An e-commerce store whose search is visual. Upload a photo — or describe
something in words, or both at once — and Lens ranks a 44,419-product catalogue
by semantic similarity using a fine-tuned CLIP model and a FAISS index, then
lets you buy what you found: cart, checkout, simulated payments, order
lifecycle, and an admin dashboard.

## Architecture

Three parts, deliberately separable:

| Directory | What it is |
| --- | --- |
| `ai/` | The search system: CLIP embedding, FAISS retrieval, two-stage re-ranking. No web or database concerns. |
| `backend/` | FastAPI. Owns the API, PostgreSQL schema, auth, catalogue, cart, checkout, orders, admin. Imports `ai/` for search. |
| `frontend/` | React SPA built with Vite. No router and no charting library — see `AGENTS.md`. |

Search results and catalogue rows are the same products: `products.faiss_index`
maps each database row to its position in the FAISS index, and that alignment is
an invariant the code asserts at startup. `backend/verify_alignment.py` proves it
independently.

## How search works

Two stages. The first is semantic and approximate; the second is symbolic and
corrective. Neither is sufficient alone.

**Stage 1 — retrieval.** The query becomes a 512-dimension CLIP embedding and
FAISS returns the `retrieve_n` nearest catalogue vectors (default 50) by inner
product on L2-normalised vectors, i.e. cosine similarity. The query embedding
comes from one of three places:

| Query | Embedding |
| --- | --- |
| Text | `model.encode_text` |
| Image | `model.encode_image` |
| Both | `alpha * image + (1 - alpha) * text`, renormalised (default `alpha=0.7`) |

Because all three produce a vector in the same space, image, text and combined
search share one retrieval path rather than being three features.

**Stage 2 — metadata re-ranking.** CLIP is good at "looks like this" and
unreliable at "is definitely red". So the query is also parsed against
vocabulary mined from the dataset itself — every distinct `articleType` and
`baseColour`, plus a small synonym table (`sneakers -> Casual Shoes`,
`trainers -> Sports Shoes`) — and candidates matching the parsed intent get an
additive boost before the final sort:

| Match | Boost |
| --- | --- |
| Article type | +0.15 |
| Colour | +0.10 |
| Gender | +0.05 |

The boosts are additive on a cosine score, and deliberately small: they reorder
within the retrieved set but cannot drag in something CLIP considered
irrelevant. Recall stays the retriever's job.

Implementation: `ai/search_system.py` (`build_search`), wired up in
`backend/server.py`. The catalogue-filtered variant used by the storefront is
`backend/hybrid.py`.

## Benchmarks

Two evaluations were run, on different query sets. They are not comparable to
each other, so they are reported separately.

**40 queries — effect of re-ranking** (`ai/results/final_results.json`)

| Stage | P@5 | P@10 | NDCG@5 | NDCG@10 |
| --- | --- | --- | --- | --- |
| Fine-tuned CLIP, retrieval only | 0.705 | 0.703 | 0.818 | 0.836 |
| **Fine-tuned + metadata re-rank** | **0.900** | 0.877 | 0.928 | 0.937 |

**8 queries — effect of fine-tuning** (`ai/results/model_comparison.json`)

| Model | P@5 | P@10 | NDCG@5 | NDCG@10 |
| --- | --- | --- | --- | --- |
| Baseline CLIP ViT-B/32 | 0.775 | 0.837 | 0.943 | 0.925 |
| Fine-tuned | 0.850 | 0.838 | 0.960 | 0.948 |

Fine-tuning: triplet margin loss over 3,000 metadata-mined triplets, fp32,
lr=1e-6, 2 epochs.

**The headline number is 0.900 P@5, and the honest reading is that re-ranking
earned more of it than fine-tuning did** (+0.195 P@5 from re-ranking on the
40-query set, against +0.075 from fine-tuning on the 8-query set). The cheap
symbolic layer outperformed the expensive learned one on this dataset.

Caveats, because they matter for how much weight these numbers carry:

- Relevance is **approximated from product metadata**, not human judgement. A
  result counts as relevant if its attributes match the parsed query, which is
  the same signal Stage 2 boosts on — so the re-ranking figure is measured on a
  criterion related to what it optimises.
- 40 and 8 queries are small. Treat these as directional.
- Some apparent failures are taxonomy artefacts rather than retrieval errors —
  a query for women's sandals cannot return five good hits when the catalogue
  holds four.
- Boosting improved mis-ranked queries while leaving genuinely sparse ones
  unchanged, which is the pattern you would want if the gain is real rather
  than metric-gaming.

## Tech stack

| Layer | Choice |
| --- | --- |
| Model | OpenAI CLIP ViT-B/32, fine-tuned (`clip-anytorch`, PyTorch) |
| Vector search | FAISS (`IndexFlatIP`, 44,419 x 512, exact) |
| API | FastAPI + Uvicorn, Pydantic schemas |
| Database | PostgreSQL 14+, SQLAlchemy 2.0, Alembic, psycopg 3 |
| Full-text | PostgreSQL `tsvector` + `pg_trgm` fuzzy matching |
| Auth | JWT (PyJWT) access + refresh tokens, bcrypt hashing |
| Frontend | React 19, Vite 6, hand-written CSS |
| Payments | Simulated UPI / card / wallet gateway |

`IndexFlatIP` is exhaustive rather than approximate: at 44k vectors an exact
scan is fast enough that an ANN index would trade recall for latency nobody
would notice.

Notable non-choices. The frontend's only runtime dependencies are `react` and
`react-dom` — no router, no charting library, no CSS framework (see
`AGENTS.md`), so tab state is `useState` and the admin revenue chart is a `div`
per bucket. The backend's rate limiter (`backend/ratelimit.py`) is stdlib plus
FastAPI, with no Redis: the deploy target is a single process, and that
constraint is documented in the module rather than discovered later.

## Prerequisites

- Python 3.12
- Node.js 20+ (developed on 24)
- PostgreSQL 14+
- ~2 GB RAM free for the backend process — loading CLIP peaks around 1.75 GB

## Setup

### 1. Model artifacts and images (not in git)

About 1.3 GB of binaries are gitignored and must be put in place by hand:

| Path | Size | What |
| --- | --- | --- |
| `ai/models/clip_finetuned.pt` | 605 MB | Fine-tuned CLIP weights |
| `ai/models/product_index.faiss` | 91 MB | 44,419 product vectors |
| `backend/images/*.jpg` | 637 MB | 44,441 product images, named `<product_id>.jpg` |

`ai/models/product_metadata.json` is **not** needed at runtime — product
metadata is served from PostgreSQL — but `verify_alignment.py` uses it to prove
the index and the database still agree.

Check the images landed correctly:

```bash
cd backend
python verify_images.py
```

### 2. Python environment

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
pip install -r backend/requirements.txt
```

### 3. Database

Create the database and a non-superuser role that owns it:

```sql
CREATE ROLE lens LOGIN PASSWORD 'your-password';
CREATE DATABASE lens OWNER lens;
```

Then configure and migrate:

```bash
cd backend
cp .env.example .env        # fill in DATABASE_URL and JWT_SECRET
alembic upgrade head
```

`.env.example` documents every variable the backend reads. Only `DATABASE_URL`
and `JWT_SECRET` are required; the rest have working local defaults.

### 4. Seed the catalogue

```bash
cd backend
python seed.py                  # 44,419 products, aligned to the FAISS index
python verify_alignment.py      # proves FAISS position <-> DB row <-> JSON row
```

`verify_alignment.py` should end with `ALIGNMENT VERIFIED`. If it does not, stop
— search results will be subtly wrong rather than obviously broken.

### 5. Frontend

```bash
cd frontend
npm install
cp .env.example .env
```

## Running

Two processes, in separate terminals:

```bash
# Terminal 1 — API on :8000
cd backend
python -m uvicorn server:app --reload --port 8000

# Terminal 2 — Vite dev server on :5173
cd frontend
npm run dev
```

Open <http://localhost:5173>. The first backend start loads CLIP and the FAISS
index, which takes a few seconds and a lot of memory.

Interactive API docs: <http://localhost:8000/docs>

## Creating your first account

Registration is open — use the **Create an account** form on the sign-in page.
A new account is an ordinary customer. Admin rights are granted separately, from
a shell; see below.

## Admin bootstrap

**A freshly migrated database has no admin at all.** Nothing in this repository
carries admin status: `is_admin` is a column in PostgreSQL, so cloning the code
and running the migrations gives you a store with zero administrators, and no
amount of deploying changes that. Every environment needs this done once,
by hand.

There is deliberately no API endpoint that grants admin rights. A self-serve
route to privilege escalation is the one thing that must not be reachable over
the network, however well guarded, so promotion requires shell access to the
machine running the database. The admin dashboard does not offer a
promote/demote control for the same reason — its absence is a decision, not an
oversight.

Run from `backend/`, with the virtualenv active:

```bash
# 1. Register normally first — through the app's own sign-up form, so the
#    password is chosen by whoever will own the account and never typed by
#    anyone else.

# 2. Grant admin rights
python promote_admin.py you@example.com

# 3. Confirm
python promote_admin.py --list
```

Then sign in: an **Admin** button appears in the header, and `/admin/*` routes
start returning 200 instead of 403.

### Handing over, or rotating an admin

Order matters. `promote_admin.py` refuses to revoke the last remaining admin —
that guard is what stops you locking everyone out — so always promote the
replacement first and *prove it works* before revoking anyone:

```bash
python promote_admin.py new-admin@example.com   # 1. promote
#                                                 2. sign in as them, open the
#                                                    dashboard, confirm it loads
python promote_admin.py old-admin@example.com --revoke   # 3. only then revoke
```

### Passwords

`set_password.py` is the only way to change a password in Phase 5 — self-service
reset needs an email provider, deferred to Phase 6.

```bash
python set_password.py you@example.com --generate   # prints a strong password once
python set_password.py you@example.com --prompt     # type one, not echoed
```

There is no `--password` flag: an argument would land in shell history and in
`ps` output for every user on the machine.

Note that changing a password does **not** sign out existing sessions. JWTs are
stateless and carry only a user id, so nothing about an issued token depends on
the password. Rotating `JWT_SECRET` is what ends every session everywhere — see
`backend/.env.example`.

## Frontend scripts

- `npm run dev` — Vite dev server with hot reload
- `npm run build` — production build into `dist/`
- `npm run preview` — serve the production build locally

A production build inlines `VITE_API_URL` at build time and refuses to build a
working bundle without it — a bundle that silently pointed at `localhost` would
fail for every visitor while looking healthy from the server.

## Verification scripts

Run from `backend/`:

| Script | Checks |
| --- | --- |
| `verify_alignment.py` | FAISS position ↔ DB row ↔ JSON row still agree |
| `verify_images.py` | Every product id has an image file |

## Project layout

```
ai/          CLIP + FAISS search system
backend/     FastAPI app, SQLAlchemy models, Alembic migrations
  alembic/   12 migrations
  images/    product images (gitignored)
frontend/    React SPA (Vite)
  src/components/   UI, incl. admin/ dashboard panels
  src/data/         API clients
PHASE5.md    current roadmap
AGENTS.md    constraints for anyone (human or agent) editing this repo
```
