# Project Template

A ready-to-clone scaffold for a **Docker Compose app deployed on the Raspberry
Pi 5** behind the shared Caddy + Cloudflare Tunnel. Vite/React frontend +
FastAPI/Postgres backend, with the CI, deploy automation, tests, docs and dev
workflow a production deployment actually needs — and with the traps that
bite it pre-fixed.

**This is a starting point, not a deployed app.**

```bash
git clone --depth 1 https://github.com/inspizzz/wiktors-project-template.git my-app
cd my-app && ./scripts/init-project.sh my-app
```

That is SETUP.md steps 1–5 in one command. See **[SETUP.md](./SETUP.md)** for
what it does, and for steps 6 onward (the Pi, DNS, Caddy) which stay manual.

> **No server yet?** The deploy steps assume a machine that already runs a
> shared Caddy behind a Cloudflare Tunnel. **[docs/INFRASTRUCTURE.md](./docs/INFRASTRUCTURE.md)**
> builds that from a bare Raspberry Pi — once per server, not once per app.
> Local development needs none of it.

> **Strip `.git` before you do anything else.** This template *is* a git
> repository now, with its own remote — a copy that keeps `.git` would push
> your new project straight into the template repo. SETUP.md step 1 covers it.

## What is in here, and why

| Path | Why it exists |
|---|---|
| `docker-compose.yml` | Local dev: overridable ports, hot reload, **migrates itself on start** |
| `compose.deploy.yml` | Production on the Pi: no ports, external `web` network, bind-mounted data, one-shot `migrate` service |
| `compose.e2e.yml` + `scripts/e2e.sh` | Disposable full stack: build → migrate → seed → Playwright → tear down |
| `compose.staging.yml` | Optional second environment tracking `develop` |
| `backend/app/seed.py` | **The keystone.** An empty database is not a runnable app |
| `backend/migrations/` | Alembic. The schema is owned by migrations, never `create_all()` |
| `deploy/` | Pull-based **signed-tag** deploy agent: backs up, health-gates, rolls back and *verifies* the rollback |
| `frontend/` | Vite + React, multi-stage Dockerfile, vitest unit tests, Playwright e2e |
| `frontend/nginx.conf` | SPA fallback **and the `/api` proxy** — without the latter `/api/*` returns `index.html` and the frontend can never reach its backend |
| `*/.dockerignore` | **Both present deliberately** — a missing one shipped a 1.1 GB context over SSH and overwrote an arm64 install with x86-64 binaries, twice |
| `.github/workflows/ci.yml` | 7 jobs: tests, typecheck, build, one-alembic-head, migrations up/down, destructive-migration guard, images, gitleaks |
| `.github/workflows/e2e.yml` | The full stack: nightly, on demand, or on a `run-e2e` label |
| `.github/workflows/deploy.yml` | The *alternative* deploy model (self-hosted runner). Pick this **or** `deploy/`, not both |
| `scripts/init-project.sh` | Turns a copy of this template into a real project: placeholders, git history, GitHub repo |
| `scripts/check_migration_safety.py` | Fails a PR that drops a table or column in `upgrade()` |
| `.claude/hooks/session-start.sh` | Re-roots auto-created agent branches from `main` onto `develop` |
| `.env.example` | Every variable, with safe local defaults |
| `CLAUDE.md` | What an agent session must read before writing code |
| `docs/DEVELOPING.md` | Gitflow + worktrees, the checks, schema changes, and the gotchas |
| `docs/INFRASTRUCTURE.md` | **Start here if you have no server yet** — Pi, Cloudflare Tunnel, shared Caddy, SSH, signing keys |
| `docs/DEPLOYMENT.md` | The Pi pattern, both deploy models, plus static-site variants |
| `docs/BACKUPS.md` | Encrypted backups and — the part everyone skips — a *verified* restore |

## Quick start

```bash
cp .env.example .env
# If 5432 / 8000 / 5173 are taken on your machine, set DEV_DB_PORT,
# DEV_API_PORT, DEV_WEB_PORT in .env first: ss -ltn | grep -E ':5432|:8000|:5173'
docker compose up --build
docker compose exec backend python -m app.seed
# frontend  http://localhost:5173     (lists the three seeded items)
# backend   http://localhost:8000/api/health
```

And the check that actually proves it works, end to end:

```bash
./scripts/e2e.sh
```

A fresh clone with **no real secrets** must build, typecheck, pass every test
and pass the e2e suite. If something appears to need a credential to develop,
that is a design problem.
