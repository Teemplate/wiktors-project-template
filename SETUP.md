# Setting this template up as a real project

## The fast path

Steps 1–5 below are scripted. From a fresh copy of the template:

```bash
git clone --depth 1 https://github.com/inspizzz/wiktors-project-template.git my-app
cd my-app
./scripts/init-project.sh my-app
```

That strips the template's `.git`, replaces every placeholder, starts your own
history with `main` + `develop`, writes a `.env` with a real `SECRET_KEY`, and
— **after asking you to confirm** — creates the private GitHub repo, pushes both
branches and sets `develop` as the default.

```
--no-remote   do everything locally, leave GitHub alone
--org NAME    create the repo under this user/org (default: whoever `gh` is logged in as)
--dry-run     show what would happen, change nothing
--yes         skip the confirmation (scripting)
```

> **`--yes` still creates the GitHub repo**, it just stops asking first. Deleting
> a repo needs the `delete_repo` scope, which a normal `gh auth login` does not
> grant — so an unwanted one has to be removed by hand in the browser. Use
> `--yes --no-remote` for anything you are only trying out.

It refuses to run inside the template itself, on an already-initialised project,
or with a name that is not a valid compose project *and* DNS label.

**Then continue from step 6** — the Pi, DNS and Caddy are deliberately not
scripted, because they touch shared infrastructure.

The rest of this document is what the script does, and why, in case you want to
do it by hand or something goes wrong.

---

Work through this once. Each step is small; none can be skipped without losing
something that has already gone wrong on a real deployment.

## 1. Get a copy and give it a name

```bash
git clone --depth 1 https://github.com/inspizzz/wiktors-project-template.git <app>
cd <app>
rm -rf .git          # step 2 starts a fresh history; see below
```

**Strip `.git` — this is not optional, whichever way you copied it.** Keeping it
inherits the template's history and, worse, its **remote**: your first
`git push` would go straight into the template repository. A local copy has the
same problem, so strip it there too:

```bash
cp -r ~/Documents/deployed-projects/project-template <app> && rm -rf <app>/.git
```

Confirm before step 2: `git -C . remote -v` must print nothing.

Replace the name everywhere:

```bash
grep -rl 'project-template\|CHANGEME' . --exclude-dir=node_modules --exclude-dir=.git
# then edit: .env.example, README.md, AGENTS.md, CLAUDE.md, frontend/package.json,
#            deploy/app-deploy (APP, DOMAIN, STAGING_DOMAIN, DATA_ROUTE),
#            .github/workflows/deploy.yml (runs-on label + APP_NAME),
#            .codex/rules/shipping.rules and .claude/settings.json (deploy command)
# AGENTS.md and CLAUDE.md must stay byte-identical -- edit one, cp over the other.
```

## 2. Version control — **first**, before any code

You stripped the template's `.git` in step 1. This starts your own history in
its place — nothing is inherited, and there is no remote yet, so a stray `push`
cannot go anywhere unexpected.

Do not skip it. Projects do reach production without it -- one with no
repository at all, one with zero commits -- and then have no history, no
rollback and no review path when something breaks.

```bash
git init
git add -A
git commit -m "chore: initial commit from project-template"

# Gitflow needs develop to exist from the start.
git branch develop
git switch develop
```

## 3. Create the remote and push **both** branches

A repo with no remote is one disk failure from gone.

**You do not need to visit github.com.** `gh` creates the repository from this
directory and wires up `origin` in one command — but it is a command *you* run;
nothing here creates a repo behind your back.

```bash
gh repo create <your-org>/<app> --private --source=. --remote=origin
git push -u origin main develop
```

`--source=.` makes the new repo from this existing local one, and `--remote=origin`
adds the remote — so no `git remote add` is needed. The push sends **both**
branches; `gh repo create` does not push on its own unless you add `--push`.

SSH keys are not registered for these repos — push over **HTTPS**, which the
global `gh` credential helper authenticates automatically.

Then set `develop` as the default branch so PRs and auto-created agent branches
target it:

```bash
gh repo edit <your-org>/<app> --default-branch develop
```

(If you keep `main` as the default, leave `scripts/hooks/session-start.sh` in
place — that is exactly the case it exists for. Both agents run it: Claude Code
through `.claude/settings.json`, Codex through `.codex/config.toml`.)

## 4. Local environment

```bash
cp .env.example .env
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env

# Check the default host ports are free BEFORE starting — a machine that already
# runs something on these ports will fail with "address already in use", and compose
# leaves the half-started stack behind when it does.
ss -ltn | grep -E ':5432|:8000|:5173'      # anything listed is taken
# If so, set DEV_DB_PORT / DEV_API_PORT / DEV_WEB_PORT in .env first.

docker compose up --build
```

Verify — and check the **body**, not just that something answered. If another
app already holds the port, `curl` cheerfully returns *its* response and the
check passes while your stack is not running at all:

```bash
curl -s localhost:${DEV_API_PORT:-8000}/api/health   # -> {"ok":true,"app":...}
curl -s localhost:${DEV_API_PORT:-8000}/api/items    # -> [] until you seed
```

Then seed it, so the app has something to show:

```bash
docker compose exec backend python -m app.seed
```

`http://localhost:5173` should now list three items. The schema migrated itself
on start — the backend container runs `alembic upgrade head` before uvicorn.

## 5. Run the checks the way CI will

```bash
cd backend  && pip install -r requirements-dev.txt && pytest
cd ../frontend && npm install && npm run typecheck && npm test && npm run build
cd .. && docker compose -f compose.deploy.yml config --quiet
```

Then the full stack, once, to prove the whole path works end to end:

```bash
./scripts/e2e.sh
```

It builds both images, migrates a throwaway Postgres, seeds it, and drives the
real browser against the real nginx `/api` proxy. **If this passes on a fresh
clone, the app genuinely works** — that is a much stronger statement than any
of the checks above, and it is the one that catches a missing migration or a
broken proxy.

Commit `frontend/package-lock.json` — CI uses `npm ci`, which requires it.

## 5a. Make the seed yours

`backend/app/seed.py` is the keystone the rest of this leans on: `scripts/e2e.sh`
runs it and **refuses to start the browser tests if it produced no rows**, and it
is what turns a fresh clone into a usable app instead of an empty database.

Replace `SEED_ITEMS` with data that makes *this* app usable — enough rows to tell
"the list renders" from "the list renders the wrong thing" (keep it ≥ 3). Keep it
idempotent, deterministic, and free of anything real: it runs in CI.

## 6. First deploy to the Pi

> **This step assumes the server already exists**: an always-on Linux box with
> Docker, a `web` network, a shared Caddy and a Cloudflare Tunnel, reachable as
> `pi-deploy` / `pi-remote`. If any of that is missing, do
> **[docs/INFRASTRUCTURE.md](./docs/INFRASTRUCTURE.md)** first — it is a one-time
> setup, and every step below fails without it.

Full detail and the gotchas are in **[docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)**.
In order — the order matters:

1. **Put the production `.env` on the Pi** (it never lives in the repo):
   `ssh pi-remote 'mkdir -p /mnt/ssd/apps/<app>' && scp .env pi-remote:/mnt/ssd/apps/<app>/.env`
2. **Create the DNS record** in Cloudflare: `CNAME <app> -> <tunnel>`, and make
   sure it resolves before anything else.
3. **Add the Caddy block** on the Pi in `/srv/caddy/Caddyfile`:
   ```
   http://<app>.example.com {
       reverse_proxy <app>-frontend:5173
   }
   ```
   then reload Caddy. The `http://` is deliberate — see DEPLOYMENT.md.
4. **Deploy:**
   ```bash
   docker --context pi-deploy compose -f compose.deploy.yml -p <app> up -d --build
   ```
   Use `pi-remote` instead when off the home LAN.
5. **Verify** `https://<app>.example.com` — and check the *right* thing: an
   `/api/*` route, not just a page. Pages return 200 even when the container
   cannot reach its backend at all.

> **Do DNS and the Caddy block BEFORE the first deploy.** Otherwise the deploy's
> edge health check fails even though the build and containers are fine — it
> simply cannot reach the public URL yet.

## 7. Write down how it deploys

Six months from now — or for anyone else picking this up — the *how* is the part
nobody can reconstruct. Fill in the Deployment section of this project's
`AGENTS.md` — then `cp AGENTS.md CLAUDE.md` — with the concrete facts:

```markdown
Deployed <date>. Live at https://<app>.example.com.
Compose project `<app>`; data at `/mnt/ssd/apps/<app>/`.
Deploy model: pull-based agent (deploy/) — production needs a **signed** `v*` tag.
Manual redeploy: docker --context pi-remote compose -f compose.deploy.yml -p <app> up -d --build
Status codes that are correctly not 200: <none yet>
```

That block is the first thing anyone should read before touching production.

## 8. Automate the deploy — pick ONE

Both are shipped. Running both would have them fight over the same containers,
so choose and delete the other.

**A. Pull-based signed-tag agent (recommended).** `deploy/app-deploy` +
`deploy/install-agent.sh`. A systemd user timer on the Pi polls GitHub every
60s; production only deploys a **signed** `v*` tag merged into `main`, and the
agent backs up, health-gates and rolls itself back. Nothing on the internet can
trigger it, and a human never runs a deploy command — which removes the whole
class of "deployed from a worktree / wrong `-p` / uncommitted code" mistakes.
Set it up per DEPLOYMENT.md, then `rm .github/workflows/deploy.yml`.

**B. Self-hosted runner.** `.github/workflows/deploy.yml` on a Pi-hosted GitHub
Actions runner, health-gated on `/api/health`. Simpler to reason about; needs a
runner registered and a GitHub-side credential. If you choose this, `rm -rf deploy/`.

Until either is set up, the workflow simply never runs and step 6's manual
command is the deploy.

## 9. Optional extras, when the app earns them

- **Staging** (`compose.staging.yml`): a second stack on `develop`. Worth it when
  a bad deploy would be destructive or hard to notice; it costs memory, disk and
  build time on a 4-core Pi, so it is not the default.
- **Backups** ([docs/BACKUPS.md](./docs/BACKUPS.md)): the deploy agent already
  takes a pre-deploy `pg_dump`. Add encrypted nightlies *and a verified restore*
  once the data would be missed.

## Checklist

- [ ] Template `.git` **stripped**, `git init`, first commit, `develop` created
- [ ] Private remote created, `main` **and** `develop` pushed
- [ ] Real `SECRET_KEY` generated (not the `dev-only-` placeholder)
- [ ] `.env` on the Pi at `/mnt/ssd/apps/<app>/.env` (mode 600)
- [ ] Tests, typecheck, unit tests and `compose config` all pass locally
- [ ] **`./scripts/e2e.sh` passes on a fresh clone**
- [ ] `seed.py` replaced with data that makes this app usable
- [ ] `package-lock.json` committed
- [ ] DNS record created **and resolving**
- [ ] Caddy block added and Caddy reloaded
- [ ] Deployed; an `/api/*` route verified, not just a page
- [ ] **One** deploy model chosen; the other deleted
- [ ] Deployment facts written into this project's `AGENTS.md`, copied to `CLAUDE.md`
- [ ] Deploy command reviewed in `.claude/settings.json` **and** `.codex/rules/shipping.rules`
- [ ] Using Codex? The checkout is marked `trust_level = "trusted"` in `~/.codex/config.toml`
- [ ] Placeholders replaced (`grep -r CHANGEME`)
