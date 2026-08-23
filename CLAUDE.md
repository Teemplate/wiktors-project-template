# <App name>

> Replace this file's placeholders as the project takes shape. User-facing
> overview lives in [README.md](./README.md); this file is operational notes and
> the rules a session must follow.

## Stack

Vite/React (TypeScript) frontend + FastAPI (async SQLAlchemy, Postgres) backend,
deployed as a Docker Compose stack on the **Raspberry Pi 5** behind the shared
Caddy and a Cloudflare Tunnel. Live at **https://CHANGEME.example.com**.

## Development workflow — read before writing code

**All development happens in a Claude worktree, on a Gitflow branch. This is not
optional.** The primary checkout is shared — the human and other Claude sessions
keep uncommitted WIP there — so writing code in it corrupts someone else's work.

1. **`EnterWorktree`** (or `Agent` with `isolation: "worktree"`) before the first
   edit. **Then immediately `git switch -c feature/<name> develop`** — the tool
   bases new worktrees on `origin/main`, which is *not* where work starts.
2. Implement, with the checks below green.
3. `ExitWorktree`, then `git merge --no-ff feature/<name>` into `develop`.

Branch roles are standard Gitflow: `main` = tagged releases only (never commit
directly), `develop` = integration, `feature/*` off `develop`,
`release/vX.Y.Z` off `develop` → `main` with a tag → merged back to `develop`,
`hotfix/*` off **`main`** → merged into **both**.

**Checks before every merge:**

```bash
cd backend  && pytest                # no database, no secrets needed
cd frontend && npm run typecheck     # never `next lint` — it prompts interactively
cd frontend && npm test              # vitest
```

**Also run `./scripts/e2e.sh`** when the change touches the API surface,
`nginx.conf`, a migration or `app/seed.py`. It stands up a disposable stack
(tmpfs Postgres, ports 5273/8273), migrates, seeds, and drives a real browser
through the real nginx `/api` proxy — then tears it all down. It refuses to run
the browser tests if the seed produced no rows, because against an empty list
every UI assertion passes vacuously.

**Schema changes go through Alembic**, never `create_all()`. Autogenerate,
review the file, and keep `app/seed.py` in step in the same commit. CI enforces
exactly one migration head, a clean up-and-down against an empty database, and
no `drop_table`/`drop_column` in `upgrade()` without a `destructive-ok` label.

A fresh worktree has **no** gitignored files — no `.env`, no `node_modules`, no
`.venv`. Symlink them or run the checks in the primary checkout.

**Never deploy from a worktree.** The build context is the *local directory* and
`.env` is read *locally*, so deploying from a worktree ships empty `${VAR}`
interpolation and code that is not on `develop`/`main` yet. A worktree isolates
code; production is a single shared resource.

Worktrees share refs, objects, tags, config **and the stash** — never use bare
`git stash`/`git stash pop`, because another session may pop your entry. Use a
WIP commit instead.

Full procedure: **[docs/DEVELOPING.md](./docs/DEVELOPING.md)**.

## Deployment

Push to `main` → the Pi's self-hosted runner rebuilds and restarts, **gated on
`/api/health`**. If that runner is not set up yet, deploy manually from the
primary checkout:

```bash
docker --context pi-deploy compose -f compose.deploy.yml -p CHANGEME up -d --build
```

- **`-p CHANGEME` is not optional.** A different project name builds a second
  image set and then collides on `container_name`.
- **Pi access — try `pi-deploy` first, fall back to `pi-remote`.** `pi-deploy`
  is the LAN address (`<pi-lan-ip>`) and works only from the home network; off
  it, the call fails instantly. **That is the wrong route, not a dead Pi** —
  always try `pi-remote` (a Cloudflare Tunnel to `ssh.example.com`) before
  concluding the Pi is unreachable. The first call after idle takes 60–90s to
  negotiate SSH; that is normal, not a hang.
- **`.env` is read locally** by the compose CLI on this machine and is never
  copied to the Pi. Editing it here and redeploying changes production config.
- **Persistent data**: `/mnt/ssd/apps/CHANGEME/postgres-data`, bind-mounted.
- **Public routing**: Cloudflare Tunnel → shared Caddy, whose block is
  `http://CHANGEME.example.com { reverse_proxy CHANGEME-frontend:5173 }`. The
  `http://` is deliberate: Cloudflare terminates TLS at its edge and Caddy has no
  public port on which to complete an ACME challenge.

Details and the first-deploy ordering: **[docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)**.
One-time server setup (tunnel, Caddy, SSH, signing): **[docs/INFRASTRUCTURE.md](./docs/INFRASTRUCTURE.md)**.

## Health checks — check the right thing

Verify an **`/api/*` route**, not just a page: pages return 200 even when the
container cannot reach the backend at all. Record here any status code that is
*correctly* not 200 — e.g. `/` returning 307 to `/login`, or 401 from a
basic_auth gate — so a future session does not read a correct response as an
outage.

## Secrets

`.env` is gitignored; `.env.example` is the tracked template and must list every
variable. A fresh clone with **no** `.env` must still typecheck, build and pass
tests — if something appears to need a credential to develop, that is the wrong
approach. `SECRET_KEY` must be a real value in production;
`/api/health` reports `placeholder_secret: true` if the dev default is still in
place, and the deploy workflow raises a warning on it.
