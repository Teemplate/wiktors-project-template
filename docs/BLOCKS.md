# Blocks — what a project is made of

Not every project needs a website, an API and a database. This template is a
set of **blocks** that fit together, plus a **target** that says where the
result runs. A new project takes only the blocks it uses; a block can be added
later without hand-editing every cross-cutting file.

```bash
./scripts/init-project.sh my-site --blocks web --target pages      # static site
./scripts/init-project.sh my-api  --blocks api,postgres            # API, no website
./scripts/init-project.sh my-bot  --blocks worker                  # scraper / bot
./scripts/init-project.sh my-app                                   # web,api,postgres
```

| block | what it is | lives in | needs |
|---|---|---|---|
| `web` | React 18 + Vite + TypeScript, served by nginx | `frontend/` | — |
| `api` | FastAPI service under `/api` | `backend/` | — |
| `worker` | Python loop with no port, e.g. a scraper or bot | `backend/app/worker.py` | — |
| `postgres` | Postgres 16, Alembic migrations, a seed | `backend/` + `db`/`migrate` services | `api` or `worker` |

| target | runs | allows |
|---|---|---|
| `pi-compose` | Docker Compose on the Pi, behind the shared Caddy + Cloudflare Tunnel; `deploy/` agent or self-hosted runner | every block |
| `pages` | GitHub Pages, `.github/workflows/pages.yml` on every push to `main` | `web` only |

`api`, `worker` and `postgres` are one Python package and one image: `backend/`
exists whenever any of them does, and each service sets its own `command:`.

## The contract

This is what makes blocks compatible. A block that keeps these promises can be
swapped for another implementation — a different frontend framework, a Go API —
without touching the others, the deploy agent or CI.

**`api`**
- Listens on port **8000** in its container; everything it serves is under `/api/`.
- `GET /api/health` returns 200 and `{"ok": true, …}` **without touching the
  database**, so it answers the moment the process is up. It reports
  `placeholder_secret` so a dev `SECRET_KEY` in production is visible.
- Names one **data route** for deploy checks: `/api/items` with `postgres`,
  `/api/hello` without. It is `DATA_ROUTE` in `deploy/app-deploy`; change it to
  a real route of yours once you have one.
- Compose service `backend`; container `<stack>-backend` in production.

**`web`**
- Calls only relative `/api/…` URLs. `VITE_API_BASE` stays empty.
- Serves on port **5173** in its container, with an SPA fallback: unknown paths
  return `index.html`, hashed `/assets/` return a real 404.
- Proxies `/api/` to `${BACKEND_HOST}:8000` **only when the project has `api`**
  (`frontend/nginx/snippets/api-proxy.conf.template`). Without it there is no
  `/api` at all, rather than a proxy to nothing.
- Compose service `frontend` (`web` in the e2e stack); container
  `<stack>-frontend` in production.

**`worker`**
- Has no port. Health is a heartbeat file: every completed tick touches it, and
  `python -m app.worker --check` (the Docker healthcheck) fails once it is older
  than three intervals. A stuck worker goes unhealthy; a crashing one restarts.
- Compose service `worker`, same image as the api.

**`postgres`**
- Provides `DATABASE_URL`. Owns `backend/migrations/`, `app/db.py`,
  `app/models.py` and `app/seed.py`.
- Brings a one-shot **`migrate`** service that applies migrations and exits;
  every Python service that uses the database waits for it to exit zero.
- Seeds with `docker compose run --rm migrate python -m app.seed`.
- In production, data bind-mounts from `/mnt/ssd/apps/<stack>/postgres-data`
  and `deploy/app-deploy` takes a `pg_dump` before migrating.

**Every block**
- Public block — the one Caddy points at — is `web` if present, else `api`. It
  alone joins the shared `web` network. A `worker`-only project has none, and
  the deploy agent skips its edge check.
- Owns its compose fragments, its tests and its section of CI; see below.

## How it is wired

**`blocks.json`** is the manifest: the catalogue of blocks and targets, which
ones this project selected, and which files each block owns. A file is kept
only if every rule that matches it is satisfied — so
`frontend/src/features/items/` belongs to `web` (via `frontend/`) *and* to
`web+api+postgres`, and leaves with any of the three.

**Code wires itself by discovery**, so removing a block is deleting files, never
editing them:
- FastAPI includes every `router` in `backend/app/routes/`. `items.py` needs
  `postgres`, `hello.py` only `api`.
- React mounts every `frontend/src/features/*/index.tsx`. `items/` needs
  `api+postgres`, `hello/` needs `api`. Tests sit next to their feature.

**Compose files are generated.** Each block keeps fragments next to its code —
`<dir>/compose/<block>.<env>.yml` for `dev`, `deploy` and `e2e` — plus *glue*
that only applies when another block is present (`api.deploy.with-postgres.yml`
waits for `migrate`; `web.deploy.with-api.yml` sets `BACKEND_HOST`) and a
`.public.yml` for the public block. The root `docker-compose.yml`,
`compose.deploy.yml` and `compose.e2e.yml` are `include:` lists written by
`scripts/blocks.py sync`; edit the fragments, never the root files. Staging is
`compose.deploy.yml` with `STACK=<app>-staging`, which namespaces every
container, image and data directory. `include:` needs Docker Compose ≥ 2.20.

**Text files carry marked sections.** In the files `blocks.json` lists under
`marked`, a section between `# block:<when>` and `# /block` (or
`<!-- block:<when> -->` … `<!-- /block -->` in Markdown) is removed with its
block. `<when>` is names joined by `+` (all) or `|` (any), and a target name
counts too: `block:pi-compose`, `block:api|worker`.

**Scripts read the blocks instead of assuming them.** CI's `detect` job gates
every other job; `scripts/e2e.sh` seeds only with `postgres`, checks the proxy
only with `web+api`, runs browser tests only with `web`; `deploy/app-deploy`
checks only the containers that exist and backs up only a database it has. The
deploy agent holds its own `BLOCKS=` line rather than reading the checkout, so
a merge cannot change how it deploys.

## Changing a project's blocks

```bash
python3 scripts/blocks.py status                       # what this project has
python3 scripts/blocks.py set --blocks web,api         # drop worker and postgres
python3 scripts/blocks.py add worker --from <template checkout>
python3 scripts/blocks.py check                        # CI runs this
```

- **`set`** only removes: files, marked sections, compose includes, and the
  block's line in `deploy/app-deploy`. `--dry-run` shows the list first.
- **`add`** copies the block's files (and any glue it now needs) in from a
  template checkout, rewrites the template's placeholders to this project's
  name, regenerates compose, and adopts the template's `blocks.json` rules.
  Files already here are never overwritten. A marked file you have not edited
  is regenerated; one you have edited is listed, with the sections to merge
  by hand.
- After either, reinstall the deploy agent on the Pi
  (`./deploy/install-agent.sh prod`) so the installed copy learns the new
  `BLOCKS=`, and update the Caddy block if the public block changed.

The target changes the same way, with `--target`. `set` can switch only to a
target whose files are already here; otherwise `add` brings them, e.g.
`add api --from … --target pi-compose` moves a Pages site onto the Pi when it
gains an API. Delete the old target's workflow yourself.

## Adding a new kind of block

1. Put its code in its own directory, or in `backend/` if it is Python.
2. Give it compose fragments for each environment, and glue for each block it
   interacts with.
3. Add it to `blocks.json`: the catalogue entry (summary, checks, requirements),
   a `files` rule for everything it owns, and the targets that allow it; add
   it to `COMPOSE_ORDER`/`FRAGMENT_DIR` in `scripts/blocks.py`.
4. Mark any shared text it needs (`.env.example`, CLAUDE.md checks).
5. Teach the three consumers: a `detect` output and a CI job, a stage in
   `scripts/e2e.sh`, a health check in `deploy/app-deploy`.
6. Add a preset to `scripts/check_preset.py` and run
   `python3 scripts/check_preset.py <preset> --unit --e2e`.
