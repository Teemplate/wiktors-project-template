# Deployment

Where a project runs is its **target** (`blocks.json`, [BLOCKS.md](./BLOCKS.md)):

- **`pi-compose`** — a Docker Compose stack on the **Raspberry Pi 5**, behind
  one shared Caddy and a Cloudflare Tunnel. Most of this document.
- **`pages`** — a `web`-only static site on GitHub Pages. See
  [GitHub Pages](#github-pages); nothing else here applies to it.

The Pi needs Docker Compose **2.20 or newer**: the root compose files are
`include:` lists of each block's fragments.

> This document assumes that server already exists. To build it from scratch —
> OS, Docker, the `web` network, the tunnel, Caddy, SSH and signing keys — see
> **[INFRASTRUCTURE.md](./INFRASTRUCTURE.md)** first.

## The house pattern

The Pi (LAN `<pi-lan-ip>`) runs **one shared Caddy** plus a **cloudflared**
connector. **No inbound ports are open on the house router** — all public
traffic arrives through the tunnel. Three rules follow, and each is load-bearing:

1. **Apps publish no ports and run no Caddy of their own.** They join the
   external Docker network `web` so the shared Caddy can reach them by container
   name.
2. **Caddy blocks are written `http://`**, not `https://`, and point at the
   project's public block — `web` if it has one, else `api`:
   ```
   http://<app>.example.com {
       reverse_proxy <app>-frontend:5173    # or <app>-backend:8000 without web
   }
   ```
   Cloudflare terminates TLS at its edge, and Caddy has no public port on which
   to complete an ACME challenge. Writing `https://` breaks it. A `worker`-only
   project serves nothing and needs no Caddy block or DNS record.
3. **Persistent data bind-mounts from `/mnt/ssd/apps/<app>/`**, never baked into
   an image — so a code-only redeploy never touches data.

## Pi access

**Try `pi-deploy` first, fall back to `pi-remote`.**

| host | route | works |
|---|---|---|
| `pi-deploy` | LAN `<pi-lan-ip>` | home network only |
| `pi-remote` | `cloudflared` → `ssh.example.com` | anywhere |

Off the LAN, `pi-deploy` fails immediately (`Network is unreachable`, or a
connection timeout). **That is the wrong route, not a dead Pi — always try
`pi-remote` before concluding the Pi is down.** `pi-remote` needs a live
Cloudflare Access session; if it prints a login URL and times out, ask the user
to authenticate rather than giving up. Either way the first call after an idle
period takes **60–90s** to negotiate SSH; that is normal, not a hang.

For a docker context over the tunnel:
`docker context create pi-remote --docker host=ssh://pi-remote`

## Manual deploy — the first one only

Before the deploy agent is installed (§ The deploy agent), and only then. From
the **primary checkout**, on `main`, never from a worktree:

```bash
docker --context pi-deploy compose -f compose.deploy.yml -p <app> up -d --build
```

- **`-p <app>` is not optional.** A different project name builds a second image
  set and then collides on `container_name`.
- **`.env` is read on *this* machine**, by the compose CLI, for both `env_file:`
  and `${VAR}` interpolation. It is never copied to the Pi, so nothing secret
  lands there — and editing `.env` here then redeploying is enough to change
  production config.
- The build context ships over SSH and builds **natively on arm64**. Expect a
  few minutes; the frontend build is the long pole (~8 min on one app here).

## First deploy — order matters

1. Production `.env` onto the Pi: `/mnt/ssd/apps/<app>/.env`.
2. **DNS record first**, and confirm it resolves.
3. **Caddy block** in `/srv/caddy/Caddyfile`, then reload Caddy.
4. Deploy.
5. Verify an `/api/*` route (or, without the api block, the page).

> Doing DNS and Caddy *after* the first deploy makes the deploy's edge health
> check fail even though the build and containers are fine — it just cannot
> reach the public URL yet.

## Health checks — check the right thing

**Check an `/api/*` route, not just a page.** A page returns 200 even when the
container cannot reach its backend at all — a real outage of exactly this shape
went unnoticed for days: every `/api` route 502'd while pages stayed 200.

```bash
curl -s -o /dev/null -w '%{http_code}' https://<app>.example.com/api/health
```

**Every container reports its own health, too.** Each one carries a Docker
healthcheck, so `docker ps` and the Pi's status views say `healthy` or
`unhealthy` instead of a bare "Up":

| container | healthcheck | where it is defined |
|---|---|---|
| `frontend` (web) | nginx's own `/healthz` → `ok` | `frontend/Dockerfile` (prod stage) + `nginx/default.conf.template` |
| `backend` (api) | `/api/health` → 200 | `backend/Dockerfile` (and `api.deploy.yml`) |
| `worker` | the heartbeat (`app.worker --check`) | `worker.*.yml`, overriding the image's |
| `db` (postgres) | `pg_isready` | `postgres.*.yml` |
| `migrate` | none: a one-shot, `healthcheck: disable: true` | `postgres.*.yml` |

`python3 scripts/check_healthchecks.py` fails the merge if a service has
none, and `deploy/app-deploy` fails the deploy if any long-running container is
not `healthy` within ~3 minutes. A new service needs a healthcheck before
either will let it through.

Record in `AGENTS.md`/`CLAUDE.md` every status code that is *correctly* not 200 — a 307 to
`/login`, a 401 from a basic_auth gate, a 403 on a gated endpoint — so a future
session does not read a correct response as an outage.

## Rollback

Note the image digests **before** deploying, so there is something to go back to:

```bash
docker --context pi-remote images --no-trunc --format '{{.Repository}} {{.ID}}' | grep <app>
```

For a database-backed app, take a pre-deploy dump whenever a migration will run:

```bash
docker --context pi-remote exec <app>-db pg_dump -U <user> <db> > predeploy-$(date +%Y%m%d-%H%M%S).dump
```

## The deploy agent — how every deploy happens

The manual command depends on a human remembering `-p`, the right context, the
right branch and the primary checkout. So after the first deploy, nobody runs
it: **the session that ships the work runs `./scripts/deploy.sh`**, which runs
the project's deploy agent on the Pi over SSH.

```bash
./scripts/deploy.sh staging    # after merging to develop and pushing it
./scripts/release.sh v1.2.0    # tags, pushes, then runs ./scripts/deploy.sh prod
```

`deploy/app-deploy` is that agent, installed on the Pi as
`~/.local/bin/<app>-deploy`. The caller chooses **when**; the agent chooses
**what**: staging builds `origin/develop`, and **production builds the newest
`v*` tag merged into `origin/main`, only if `git verify-tag` passes** (proven:
an unsigned release was rejected and production stayed on the previous tag).
It fetches with a read-only deploy key and builds from its own checkout on the
Pi, so it cannot ship a worktree, a dirty tree or an unpushed commit. `deploy.sh`
exits with the agent's code — 0 live and healthy (or already current), 1 failed
and rolled back, 2 not set up, 3 another deploy running — so the session sees the
real result instead of assuming one.

**Nothing polls.** Earlier versions of this template ran the agent from a
systemd timer every 60s. That is gone: a deploy is part of finishing the work,
so the session that did the work does it and reads the outcome, and there is no
background service on the Pi to keep alive. GitHub still holds no credential
that reaches the Pi; only SSH access to the Pi can start a deploy, and GitHub
Actions never deploys anything.

Set up, on the Pi:

```bash
# 1. Edit deploy/app-deploy: APP, DOMAIN, STAGING_DOMAIN, DATA_ROUTE.
#    BLOCKS is written by scripts/blocks.py; re-run install-agent.sh after
#    adding or removing a block, or changing deploy/app-deploy, so the
#    installed copy learns it.
# 2. On the Pi:
mkdir -p /mnt/ssd/apps/<app>/{env,state,backups}
install -m 600 /dev/stdin /mnt/ssd/apps/<app>/env/app.env   # paste the real .env
git clone --single-branch --branch main <read-only deploy key URL> /mnt/ssd/apps/<app>/src
git -C /mnt/ssd/apps/<app>/src config --add remote.origin.fetch \
  '+refs/heads/develop:refs/remotes/origin/develop'   # staging tracks develop
cd /mnt/ssd/apps/<app>/src && ./deploy/install-agent.sh prod
# 3. Back on the dev machine, from the primary checkout:
./scripts/deploy.sh prod
```

`install-agent.sh` installs the script only. On a Pi set up by an older
template it also disables and deletes the old `<app>-deploy@.timer`.

### Running CI on the Pi (optional)

A GitHub Actions runner **on the Pi** can run CI, which then costs no Actions
minutes ([DEVELOPING.md § Actions minutes](DEVELOPING.md#actions-minutes)). The
router has no inbound ports; the runner long-polls GitHub outbound. Register it
as a systemd **user** unit with linger enabled; the Pi has no passwordless sudo,
so the runner's `svc.sh install` cannot run over SSH. It runs CI only — deploys
stay with `scripts/deploy.sh`.

**Production hosts fetch only `main`** (and `develop`, for staging). A deploy host needs `main` (prod's signed tag) and `develop` (staging) —
nothing else. The clone above is limited to those two, and `app-deploy` fetches
them by explicit refspec on every run, so `feature/*` and especially
`experimental/*` branches (research that can carry large data and never
deploys; see `DEVELOPING.md` § 2) never land on the Pi. A host cloned the old
way keeps stale refs until you narrow it once:

```bash
git config --replace-all remote.origin.fetch '+refs/heads/main:refs/remotes/origin/main'
git config --add remote.origin.fetch '+refs/heads/develop:refs/remotes/origin/develop'
git for-each-ref --format='%(refname)' refs/remotes/origin \
  | grep -vE '^refs/remotes/origin/(main|develop|HEAD)$' | xargs -r -n1 git update-ref -d
git gc --prune=now
```

What each step of the agent is for — none of it is decoration:

| Step | Why |
|---|---|
| `flock` | one deploy at a time; two builds on a 4-core Pi that is also serving the site is how both time out |
| disk check | refuses to build under 5 GB free, rather than filling the SSD and taking every app down |
| **tag `:rollback` *before* the build** | `compose build` overwrites `:latest`, so capturing "previous" afterwards captures the **new** image and rollback silently becomes a no-op |
| build before touching containers | a build failure then costs nothing: old version still serving |
| `pg_dump` + size sanity check (`postgres`) | never run migrations without a backup, and a 200-byte dump is not a backup |
| `migrate` one-shot service | a bad revision aborts with the old containers still up |
| health: `/api/health` **and** a data route (`api`) | health answers `ok` while every data route is broken |
| health: the frontend's `/api` proxy (`web`+`api`) | if the SPA fallback swallows `/api/*` the site looks fine and is entirely broken |
| health: the worker's heartbeat (`worker`) | a worker has no port; a stuck one is running but not ticking, and only the heartbeat shows it |
| every container `healthy` | a container nobody can watch is a failure waiting to be found; one with no healthcheck fails here by name |
| only the blocks in its own `BLOCKS=` | the installed agent decides what to check; a merge cannot quietly change that |
| edge check accepts 200/301/302/401 | behind Access or basic_auth those *are* success; only a dead origin gives 502 |
| rollback **verifies itself** | a rollback that silently does nothing is worse than none — it leaves broken code live under a green log line |
| rollback does **not** restore the DB | a `pg_restore` racing live traffic is worse than a human reading the dump; that call is not the agent's to make |

Pair it with age-encrypted nightly backups whose **private key is not on the
Pi** — see [BACKUPS.md](./BACKUPS.md).

**Write it down in the project's `AGENTS.md`/`CLAUDE.md`** — the compose
project name, the data path, whether there is a staging stack, and the deploy
command. That block is the first thing anyone should read before touching
production, and it is the part that cannot be reconstructed from the code.

---

## Why a session runs the release

`./scripts/release.sh` is run by agent sessions themselves, under the standing
authorization in AGENTS.md / CLAUDE.md § Shipping.

That guide used to say the opposite: that a session "cannot run this, and
cannot `git push origin main`", because of a blanket harness rule quoted as
*"never push to main/master, force-push, or merge"*. **That was wrong, and it
was wrong in an expensive way** — it was copied into several projects, where it
stranded sessions holding finished, tested commits they believed they were
forbidden to ship.

Two things were being confused. It is true that **nothing in this file grants a
permission**: project instructions override an agent's default behaviour, not
its permission layer. But that layer is *configurable*, and the lever is one
entry — `Bash(./scripts/release.sh:*)` in `.claude/settings.json`, or the
matching `prefix_rule` in `.codex/rules/shipping.rules` (and its twin for
`./scripts/deploy.sh`) — not an immovable property of the harness. Once those
rules are present a session cuts and deploys the release; without it, it cannot, and no amount of prose here changes that
either way.

## GitHub Pages

The **`pages` target**: `./scripts/init-project.sh <app> --blocks web --target pages`.
`.github/workflows/pages.yml` typechecks, tests and builds `frontend/`, then
publishes `frontend/dist` on every push to `main` — so a release cut by
`./scripts/release.sh` *is* the deploy. It stays skipped until Pages is enabled
for the repository, once:

```bash
gh api -X POST repos/<owner>/<repo>/pages -f build_type=workflow
```

With a custom domain the site is served at the root. Without one it lives under
`/<repo>/`: set the repository variable `PAGES_BASE_PATH=/<repo>/` so Vite
builds its asset URLs for that path. `index.html` is copied to `404.html`, so a
deep link to a client-side route loads the app.

Set the custom domain with:

```bash
gh api -X PUT repos/<owner>/<repo>/pages -f cname=<domain>
```

DNS on Cloudflare must be **grey cloud (proxied = false)**: proxying blocks the
Let's Encrypt HTTP-01 challenge, so GitHub can never issue a certificate. Grey
cloud also lets GitHub serve its own cert, which is the actual fix for the 526s
a proxied-without-cert setup returns.

> **The certificate gotcha — costs 10–25 minutes every time it is forgotten.**
> **Create the DNS record first.** If the custom domain is set before DNS
> resolves, GitHub's verification fails and the cert **silently never issues**
> (`https_certificate` absent, `status: null`). Re-PUTting the same cname is a
> no-op and does not retrigger the check. **The fix is to clear it
> (`-f cname=""`) and re-add** — the cert appears within seconds.
> `https_enforced=true` is rejected until the cert exists, so it must be a
> separate, later call.

When the site later needs an API, move it onto the Pi:
`python3 scripts/blocks.py add api --from <template checkout> --target pi-compose`.

## Cloudflare Workers — documented, not scaffolded

`wrangler.jsonc` binds the built directory as static assets with
`custom_domain` routes. `npm run deploy` ships it. **Add a CI workflow with a
Cloudflare API token** rather than deploying from a laptop — a hand-run deploy
puts code live with nothing having checked the build first.
