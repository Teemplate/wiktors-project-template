# Project Template

A ready-to-clone scaffold built from **blocks** — a Vite/React website, a
FastAPI service, a Python worker, Postgres — that fit together, deployed as a
**Docker Compose app on the Raspberry Pi 5** behind the shared Caddy +
Cloudflare Tunnel, or as a **static site on GitHub Pages**. A new project takes
only the blocks it uses, with the CI, deploy automation, tests, docs and dev
workflow a production deployment actually needs — and with the traps that bite
it pre-fixed.

**This is a starting point, not a deployed app.**

```bash
git clone --depth 1 https://github.com/inspizzz/wiktors-project-template.git my-app
cd my-app && ./scripts/init-project.sh my-app                         # web, api, postgres
#          ./scripts/init-project.sh my-app --blocks web --target pages   # a static site
#          ./scripts/init-project.sh my-app --blocks worker               # a bot, no website
```

That is SETUP.md steps 1–5 in one command. **[docs/BLOCKS.md](./docs/BLOCKS.md)**
lists the blocks, the contract that makes them compatible, and how to add one
to a project later. See **[SETUP.md](./SETUP.md)** for
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
| `blocks.json`, `scripts/blocks.py` | **Which blocks this project has** and which files each owns; prunes, adds, and regenerates the compose files. [docs/BLOCKS.md](./docs/BLOCKS.md) |
| `frontend/compose/`, `backend/compose/` | Each block's compose fragments, per environment, plus the glue between blocks |
| `docker-compose.yml` | Local dev (generated `include:` list): overridable ports, hot reload, **migrates itself on start** |
| `compose.deploy.yml` | Production on the Pi (generated): no ports, external `web` network, bind-mounted data, one-shot `migrate` service. Staging is the same file with `STACK=<app>-staging` |
| `compose.e2e.yml` + `scripts/e2e.sh` | Disposable stack of this project's blocks: build → migrate → seed → Playwright → tear down |
| `backend/app/worker.py` | The `worker` block: a loop with no port, healthy while its heartbeat is fresh |
| `backend/app/seed.py` | **The keystone.** An empty database is not a runnable app |
| `backend/migrations/` | Alembic. The schema is owned by migrations, never `create_all()` |
| `deploy/` | Pull-based **signed-tag** deploy agent: backs up, health-gates, rolls back and *verifies* the rollback |
| `frontend/` | Vite + React, multi-stage Dockerfile, vitest unit tests, Playwright e2e. Features in `src/features/` are discovered, so one that needs the api leaves with it |
| `frontend/nginx/` | SPA fallback, and — with the api block — **the `/api` proxy**: without it `/api/*` returns `index.html` and the frontend can never reach its backend |
| `*/.dockerignore` | **Both present deliberately** — a missing one shipped a 1.1 GB context over SSH and overwrote an arm64 install with x86-64 binaries, twice |
| `.github/workflows/ci.yml` | Gated on the blocks present: tests, typecheck, build, one-alembic-head, migrations up/down, destructive-migration guard, images, gitleaks, agent instructions — and, in the template, a project cut per block combination |
| `.github/workflows/e2e.yml` | The full stack: nightly, on demand, or on a `run-e2e` label |
| `.github/workflows/deploy.yml` | The *alternative* deploy model (self-hosted runner). Pick this **or** `deploy/`, not both |
| `.github/workflows/pages.yml` | The `pages` target: build and publish `frontend/` on every push to `main` |
| `scripts/check_preset.py` | Template only: init a project per block combination and check it (`--unit`, `--e2e`) |
| `scripts/init-project.sh` | Turns a copy of this template into a real project: placeholders, `--blocks`/`--target`, git history, GitHub repo |
| `scripts/check_migration_safety.py` | Fails a PR that drops a table or column in `upgrade()` |
| `scripts/hooks/session-start.sh` | Re-roots auto-created agent branches from `main` onto `develop`. Run by **both** agents, from a path belonging to neither |
| `.env.example` | Every variable, with safe local defaults |
| `local.example/` | Template for `local/` — your own hostnames, paths and app inventory, gitignored |
| `AGENTS.md`, `CLAUDE.md` | What an agent session must read before writing code. Byte-identical copies — Codex reads the first, Claude Code the second, and CI fails if they drift |
| `.codex/`, `.claude/` | The shipping policy in each agent's own syntax: `rules/shipping.rules` and `settings.json`. Prose alone grants nothing; these are the files that do |
| `docs/DEVELOPING.md` | Gitflow + worktrees, the checks, schema changes, and the gotchas |
| `docs/MODEL-ROUTING.md` | Cost-aware Codex routing: Astra plans and reviews risk, Terra builds, checks trigger escalation |
| `docs/INFRASTRUCTURE.md` | **Start here if you have no server yet** — Pi, Cloudflare Tunnel, shared Caddy, SSH, signing keys |
| `docs/DEPLOYMENT.md` | The Pi pattern, both deploy models, plus static-site variants |
| `docs/BACKUPS.md` | Encrypted backups and — the part everyone skips — a *verified* restore |

## Quick start

```bash
cp .env.example .env
# If 5432 / 8000 / 5173 are taken on your machine, set DEV_DB_PORT,
# DEV_API_PORT, DEV_WEB_PORT in .env first: ss -ltn | grep -E ':5432|:8000|:5173'
docker compose up --build
docker compose run --rm migrate python -m app.seed
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

## Agent-context maintenance

`AGENTS.md` and `CLAUDE.md` are mirrored entry points. Run
`python3 scripts/check_agent_context.py` before committing; CI checks parity,
a 28 KiB size budget, tracked references, configuration and duplicate hooks.
Run `python3 scripts/tests/test_agent_context.py` after changing the checker.
Use `--check-rules` with the checker to verify the declared Codex command policy.
The initializer fills `.agent-context.json` for each new app. The separate
`project-template` repository is superseded; use this repository for new apps.
