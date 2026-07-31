# Deploying Lens

Target: a Hetzner CX22 (2 vCPU, 4 GB RAM, 40 GB disk, ~EUR 3.79/mo) running
Ubuntu 24.04, with PostgreSQL and nginx on the same box. Full 44,419-product
catalogue, no subset.

**Why 4 GB and not 2.** Loading the fine-tuned CLIP weights peaks at ~1.75 GB
RSS, measured. A 2 GB instance gets OOM-killed at exactly that moment, and the
failure looks like a restart loop rather than an out-of-memory error. Free tiers
(512 MB) cannot start this application at all, whatever you do with the assets.

**How code and data get there.** Code comes from GitHub. The ~1.33 GB of model
artifacts and product images are gitignored and always will be, so they are
copied from a machine that already has them. Nothing in this document modifies
your local checkout.

Replace throughout: `SERVER_IP`, `your-domain.example`, `YOUR_DB_PASSWORD`.

---

## Phase A - Local preparation (read-only)

**1.** Confirm the local checkout is clean and pushed.

```bash
git status --porcelain     # must print nothing
git log --oneline -1       # must match origin/master
```

**2.** Tar the images, writing the archive **outside the repository**.

```bash
tar cf ~/Desktop/lens-images.tar -C backend images
```

Use `tar cf`, not `tar czf`. JPEGs are already compressed, so gzip costs several
minutes of CPU on both ends for roughly 1% saved. The problem being solved here
is per-file transfer overhead across 44,441 files, which plain tar fixes on its
own.

**3.** Do not archive the model files. Two large files transfer fine
individually; per-file overhead only matters at thousands of files.

---

## Phase B - Provision the server

**4.** Create the CX22 with Ubuntu 24.04 (ships Python 3.12, matching local).
Attach your SSH key at creation time.

**5.** Create a non-root user and enable the firewall.

```bash
adduser lens && usermod -aG sudo lens
rsync --archive --chown=lens:lens ~/.ssh /home/lens
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
```

**6.** Add swap. This is what stops a transient spike during model load from
becoming an OOM kill.

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

**7.** Install system packages.

```bash
apt update && apt install -y python3.12 python3.12-venv python3-pip \
  postgresql postgresql-contrib nginx certbot python3-certbot-nginx git
```

---

## Phase C - Database

**8.** Create a dedicated role that owns the database - not the postgres
superuser.

```bash
sudo -u postgres psql -c "CREATE ROLE lens LOGIN PASSWORD 'YOUR_DB_PASSWORD';"
sudo -u postgres psql -c "CREATE DATABASE lens OWNER lens;"
```

---

## Phase D - Code and Python environment

**9.** As the `lens` user, clone from the remote.

```bash
cd ~ && git clone https://github.com/Vedansh313/lens.git && cd lens
python3.12 -m venv .venv
```

**10.** Install CPU-only torch **before** the requirements file. This is the
step that most often wrecks a first deploy: `requirements.txt` lists plain
`torch`, and the default PyPI wheel pulls the CUDA build - roughly 2.5 GB of
NVIDIA libraries that cannot be used on a CPU instance, and a long download to
discover it.

```bash
.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r backend/requirements.txt
```

Installing CPU torch first means pip already considers the dependency satisfied
when it reads `requirements.txt`.

**11.** Verify. If the version does not end in `+cpu`, stop and fix it before
continuing.

```bash
.venv/bin/python -c "import torch; print(torch.__version__)"
```

---

## Phase E - Model artifacts and images

**12.** From the local machine:

```bash
scp ai/models/clip_finetuned.pt ai/models/product_index.faiss \
    ai/models/product_metadata.json lens@SERVER_IP:~/lens/ai/models/
scp ~/Desktop/lens-images.tar lens@SERVER_IP:~/
```

`product_metadata.json` is not needed at runtime - product metadata is served
from PostgreSQL - but `verify_alignment.py` compares the database against it.

**13.** On the server:

```bash
tar xf ~/lens-images.tar -C ~/lens/backend && rm ~/lens-images.tar
ls ~/lens/backend/images/*.jpg | wc -l      # expect 44441
```

---

## Phase F - Configuration

**14.** Write `~/lens/backend/.env`. It is gitignored, so it must be created
here rather than cloned.

```ini
DATABASE_URL=postgresql+psycopg://lens:YOUR_DB_PASSWORD@localhost:5432/lens

JWT_SECRET=GENERATE_A_FRESH_ONE
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

CORS_ALLOW_ORIGINS=https://your-domain.example
IMAGE_BASE_URL=https://your-domain.example
LENS_ENV=production
TRUST_PROXY_HEADER=true
```

Generate a fresh secret - do not reuse the local one:

```bash
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Notes on three of these:

* `LENS_ENV=production` makes the server refuse to boot if `IMAGE_BASE_URL`
  still points at localhost. That value is embedded in every JSON response, so a
  wrong one means every product image 404s in the browser while the server logs
  look perfectly healthy.
* `TRUST_PROXY_HEADER=true` is correct **only because nginx sits in front**. With
  it unset behind a proxy, every visitor appears to come from 127.0.0.1 and
  shares one rate-limit bucket, so a single attacker locks out everyone. Set it
  on a directly-exposed server and anyone can forge the header to evade limits
  entirely.
* `CORS_ALLOW_ORIGINS` must list the real frontend origin. Any origin here can
  drive the API with a token the browser already holds.

---

## Phase G - Migrate, seed, verify

Run from `~/lens/backend`.

**15.** `../.venv/bin/alembic upgrade head`

**16.** `../.venv/bin/python seed.py` - 44,419 products.

**17.** `../.venv/bin/python verify_alignment.py`

This must end with `ALIGNMENT VERIFIED`. **Do not continue if it does not.** A
broken FAISS-to-database alignment makes search results subtly wrong rather than
obviously broken, which is the failure mode you will not notice in a smoke test.

**18.** `../.venv/bin/python verify_images.py`

---

## Phase H - Service

**19.** Write `/etc/systemd/system/lens.service`:

```ini
[Unit]
Description=Lens API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=lens
WorkingDirectory=/home/lens/lens/backend
ExecStart=/home/lens/lens/.venv/bin/python -m uvicorn server:app \
          --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=15
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
```

**`--workers 1` is required, not a preference.** `backend/ratelimit.py` keeps its
counters in process memory, so running N workers silently multiplies every auth
rate limit by N.

There is deliberately no `EnvironmentFile`. The application calls `load_dotenv`
on `backend/.env` itself, resolved relative to `__file__`, so it works regardless
of working directory. Pointing systemd at the same file would make it re-parse a
comment-heavy file under different quoting rules for no benefit.

**20.** Start it and watch the load.

```bash
systemctl daemon-reload && systemctl enable --now lens
journalctl -u lens -f        # wait for "[lens] loaded 44419 vectors"
```

### About TimeoutStartSec

`TimeoutStartSec=300` is in the unit above because it is harmless and becomes
correct if the service ever moves to `Type=notify`. **With `Type=simple` it does
not gate anything**: systemd marks the unit active as soon as the process is
forked and never waits for readiness. Two real consequences of the ~45 second
model load:

* nginx returns 502 for roughly 45 seconds after every restart, because uvicorn
  has not bound the port yet. Expected, not a fault.
* If the process is OOM-killed during load, systemd restarts it straight back
  into the same condition. `RestartSec=15` plus systemd's default start-rate
  limiting stops the thrashing; the swap file from step 6 is what prevents the
  kill.

If `journalctl` shows repeated kills that never reach
`[lens] loaded 44419 vectors`, the problem is memory, not time.

---

## Phase I - Frontend and nginx

**21.** Install Node and build. The API URL is inlined at build time, so `.env`
must exist before `npm run build`, and changing the URL later means rebuilding.

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
cd ~/lens/frontend && npm ci
echo 'VITE_API_URL=https://your-domain.example' > .env
npm run build
```

**22.** Write `/etc/nginx/sites-available/lens` and symlink it into
`sites-enabled`, removing the `default` site.

```nginx
server {
    listen 80;
    server_name your-domain.example;

    root /home/lens/lens/frontend/dist;
    index index.html;

    # Visual search uploads. nginx defaults to 1 MB, which would reject the
    # 10 MB uploads the UI advertises - as a 413 the frontend reports as a
    # generic failure.
    client_max_body_size 12M;

    # Product images straight off disk. 44,441 static files have no business
    # occupying the single uvicorn worker.
    location /images/ {
        alias /home/lens/lens/backend/images/;
        access_log off;
        expires 30d;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    location ~ ^/(api|auth|products|categories|autocomplete|cart|wishlist|recently-viewed|checkout|orders|addresses|admin|docs|openapi\.json)(/|$) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # CLIP inference on CPU, plus a cold start after restart.
        proxy_read_timeout 120s;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

`X-Forwarded-For` here is what makes `TRUST_PROXY_HEADER=true` in step 14 correct
rather than dangerous.

```bash
nginx -t && systemctl reload nginx
```

**23.** TLS:

```bash
certbot --nginx -d your-domain.example
```

Let's Encrypt will not issue a certificate for a bare IP address, so a domain is
required for HTTPS. Without one, set `IMAGE_BASE_URL` and `CORS_ALLOW_ORIGINS` to
`http://SERVER_IP`. Authentication uses Bearer tokens rather than cookies, so
plain HTTP does function - it is simply not something to put in front of anyone.

---

## Phase J - Admin bootstrap

A freshly migrated database has **no administrator**. Admin status is a column in
PostgreSQL, carried by no commit, so this must be done once per environment. See
the Admin bootstrap section of `README.md` for the reasoning.

**24.** Register through the live site's **Create an account** form, so the
password is chosen by whoever owns the account.

**25.** Grant and confirm:

```bash
cd ~/lens/backend
../.venv/bin/python promote_admin.py you@example.com
../.venv/bin/python promote_admin.py --list
```

**26.** Set a strong password. Use `--generate` here: `--prompt` requires a TTY
and will hang in any non-interactive context.

```bash
../.venv/bin/python set_password.py you@example.com --generate
```

---

## Phase K - Smoke test

**27.** Health checks.

The backend's status endpoint is `GET /`, but publicly that path belongs to the
SPA - `location /` serves `index.html`. That is intentional, and it means the
status JSON is only reachable on the box itself:

```bash
# On the server, bypassing nginx - expect {"status":"running","products":44419,...}
curl http://127.0.0.1:8000/

# Publicly, through nginx - expect the facets JSON
curl https://your-domain.example/categories
```

A browser hitting `https://your-domain.example/` should get the application, not
JSON. Seeing the status object there would mean nginx is proxying the SPA route
to uvicorn.

**28.** In a browser:

* text search returns sensible results
* image upload returns a visually similar set - this also proves
  `client_max_body_size`
* a product image renders, proving `IMAGE_BASE_URL` and the nginx alias
* sign in, add to cart, complete a checkout
* the admin dashboard loads all five tabs
* signed out, `/admin/orders` returns 401; as a non-admin, 403

---

## Operating notes

* **Restarts take ~45 seconds** because CLIP loads at import. Expect 502s during
  that window.
* **Never raise `--workers` above 1** without moving rate-limit state out of
  process memory.
* **Rebuild the frontend** after any change to `VITE_API_URL`; it is compiled in,
  not read at runtime.
* **Rotating `JWT_SECRET`** signs out every user on every device immediately.
  It is the only revocation mechanism, since tokens are stateless.
* **Changing a password does not end existing sessions** - see
  `backend/set_password.py`.
