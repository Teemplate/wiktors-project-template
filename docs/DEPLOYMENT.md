# Deployment

Production is a Docker Compose stack on the **Raspberry Pi 5**, behind one
shared Caddy and a Cloudflare Tunnel.

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
2. **Caddy blocks are written `http://`**, not `https://`:
   ```
   http://<app>.example.com {
       reverse_proxy <app>-frontend:5173
   }
   ```
   Cloudflare terminates TLS at its edge, and Caddy has no public port on which
   to complete an ACME challenge. Writing `https://` breaks it.
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

## Manual deploy

From the **primary checkout**, on `main`, never from a worktree:

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
5. Verify an `/api/*` route.

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

## Automating it

The manual command depends on a human remembering `-p`, the right context, the
right branch and the primary checkout. Two better options, both proven here:

**Pick one of the two, not both** — they would fight over the same containers.
The pull-based agent below is the recommended default; delete
`.github/workflows/deploy.yml` if you use it, or delete `deploy/` if you use the
runner.

### Self-hosted runner (what `.github/workflows/deploy.yml` expects)

Install a GitHub Actions runner **on the Pi**, labelled with the app name. The
router has no inbound ports, so nothing can SSH in; the runner long-polls
GitHub outbound and pulls the job. The image then builds natively on arm64 with
no context shipped over the network, and the workflow **gates on `/api/health`**
so a container that starts and dies is not reported as a success. Secrets stay
on the Pi — the workflow symlinks `/mnt/ssd/apps/<app>/.env` into the checkout
rather than using GitHub secrets.

### Pull-based, signed-tag deploys — **shipped in this template, and recommended**

`deploy/app-deploy` is a complete agent; `deploy/install-agent.sh` installs it.
A systemd user timer on the Pi polls GitHub every 60s. Staging tracks
`origin/develop`; **production deploys the newest `v*` tag merged into
`origin/main`, and only if `git verify-tag` passes.** Nothing is ever
`docker compose`d by hand, and an unsigned tag is refused (proven: an unsigned
release was rejected and production stayed on the previous tag).

**Why this beats the runner.** Nothing on the internet can start a deploy —
there is no inbound path and no credential anywhere that reaches the Pi. It
also removes the entire class of "deployed from a worktree / wrong `-p` /
uncommitted code" mistakes, because a human never runs the deploy at all.

Set up, on the Pi:

```bash
# 1. Edit deploy/app-deploy: APP, DOMAIN, STAGING_DOMAIN, DATA_ROUTE
# 2. On the Pi:
mkdir -p /mnt/ssd/apps/<app>/{env,state,backups}
install -m 600 /dev/stdin /mnt/ssd/apps/<app>/env/app.env   # paste the real .env
git clone <read-only deploy key URL> /mnt/ssd/apps/<app>/src
cd /mnt/ssd/apps/<app>/src && ./deploy/install-agent.sh prod
```

What each step of the agent is for — none of it is decoration:

| Step | Why |
|---|---|
| `flock` | one deploy at a time; two builds on a 4-core Pi that is also serving the site is how both time out |
| disk check | refuses to build under 5 GB free, rather than filling the SSD and taking every app down |
| **tag `:rollback` *before* the build** | `compose build` overwrites `:latest`, so capturing "previous" afterwards captures the **new** image and rollback silently becomes a no-op |
| build before touching containers | a build failure then costs nothing: old version still serving |
| `pg_dump` + size sanity check | never run migrations without a backup, and a 200-byte dump is not a backup |
| `migrate` one-shot service | a bad revision aborts with the old containers still up |
| health: `/api/health` **and** a data route | health answers `ok` while every data route is broken |
| health: the frontend's `/api` proxy | if the SPA fallback swallows `/api/*` the site looks fine and is entirely broken |
| edge check accepts 200/301/302/401 | behind Access or basic_auth those *are* success; only a dead origin gives 502 |
| rollback **verifies itself** | a rollback that silently does nothing is worse than none — it leaves broken code live under a green log line |
| rollback does **not** restore the DB | a `pg_restore` racing live traffic is worse than a human reading the dump; that call is not the agent's to make |

Pair it with age-encrypted nightly backups whose **private key is not on the
Pi** — see [BACKUPS.md](./BACKUPS.md).

Whichever you choose, **write it down in the project's `AGENTS.md`/`CLAUDE.md`** — which
model is in use, the compose project name, the data path and the redeploy
command. That block is the first thing anyone should read before touching
production, and it is the part that cannot be reconstructed from the code.

---

## Static-site variants

This template is the compose/Pi archetype. Two lighter ones are in use here.

### GitHub Pages

Push to `main` → Actions builds → `upload-pages-artifact` → `deploy-pages`.
Configure Pages as `build_type: workflow` and set the custom domain with:

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

Next.js on Pages needs `output: "export"`, `images.unoptimized` and
`trailingSlash`, publishing `out/`. No `basePath` — a custom domain serves at
the root. Hash-based routing needs no SPA 404 fallback; path-based routing does.

### Cloudflare Workers

`wrangler.jsonc` binds the built directory as static assets with
`custom_domain` routes. `npm run deploy` ships it. **Add a CI workflow with a
Cloudflare API token** rather than deploying from a laptop — a hand-run deploy
puts code live with nothing having checked the build first.
