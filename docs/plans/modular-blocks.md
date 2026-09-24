---
feature: modular-blocks
branch: feature/modular-blocks
worktree: ../wiktors-project-template-modular-blocks
stage: awaiting-deploy-approval
design: n/a
agent: none
opened: 2026-09-24
---

## Brief

Not every project needs a website, a backend and a database. Make the template
a set of compatible blocks — `web`, `api`, `worker`, `postgres` — plus a deploy
target — `pi-compose` or `pages` — so a new project starts with only what it
uses, and a block can be added later without hand-editing every cross-cutting
file.

## Plan

1. `docs/BLOCKS.md`: the contract every block satisfies, and how blocks are
   chosen, pruned and added.
2. Compose split per block: fragments under `frontend/compose/` and
   `backend/compose/`; root `docker-compose.yml`, `compose.deploy.yml` and
   `compose.e2e.yml` become generated `include:` lists. Staging reuses
   `compose.deploy.yml` with `STACK=<app>-staging`; `compose.staging.yml` goes.
   Code wires itself by discovery (FastAPI routers in `app/routes/`, React
   features in `src/features/`) so removing a block is deleting files.
3. CI: a `detect` job reads `blocks.json`; every other job gates on it. A
   `blocks` matrix job initialises a copy per preset and runs its checks.
4. `deploy/app-deploy`, the runner workflow and `scripts/e2e.sh` check only the
   blocks the project has.
5. `init-project.sh --blocks … --target …`, backed by `scripts/blocks.py`
   (`set`, `add`, `sync`, `check`, `env`, `checks`, `describe`).
6. `pages` target: `.github/workflows/pages.yml` for a `web`-only project.
7. Remove the Next.js leftovers.

Out of scope: a Cloudflare Workers target (stays documented, unscaffolded);
per-block repositories or copier; changing service names (`frontend`,
`backend`, `db` stay, so Caddy blocks and sibling projects are unaffected).

## Questions

None.

## Touches

- `blocks.json`, `scripts/blocks.py`, `scripts/check_preset.py`, `scripts/tests/test_blocks.py`
- `docker-compose.yml`, `compose.deploy.yml`, `compose.e2e.yml`, `compose.staging.yml` (removed)
- `frontend/` — `compose/`, `nginx/` (replaces `nginx.conf`), `Dockerfile`, `vite.config.ts`, `src/`, `e2e/`
- `backend/` — `compose/`, `app/main.py`, `app/routes/`, `app/worker.py`, `requirements.txt`, `tests/`
- `deploy/app-deploy`, `scripts/e2e.sh`, `scripts/init-project.sh`, `scripts/release.sh`
- `.github/workflows/{ci,e2e,deploy,pages}.yml`
- `AGENTS.md`, `CLAUDE.md`, `README.md`, `SETUP.md`, `.env.example`, `.gitignore`
- `docs/BLOCKS.md`, `docs/DEPLOYMENT.md`, `docs/DEVELOPING.md`, `.claude/agents/feature-dev.md`, `.claude/skills/feature/SKILL.md`

## Checks

2026-09-24, on this branch:

- `backend: pytest` (python:3.12-slim) — 10 passed. `frontend: typecheck,
  test, build` — green, 6 unit tests.
- `./scripts/e2e.sh` (all four blocks) — seed, worker heartbeat, nginx proxy,
  7/7 Playwright.
- `scripts/check_preset.py classic site web-api api worker bot --unit --e2e
  --docker-python` — all six ok: each project installs only its own
  requirements, passes its tests, and passes its own e2e stack.
- `scripts/check_preset.py --all` — all seven presets init and validate
  (`blocks.py check`, agent context, every generated compose file).
- `scripts/tests/test_blocks.py` — 16 passed; `test_agent_context.py` — ok;
  `check_agent_context.py --check-rules` — ok (27424/28672 bytes).
- Drag and drop: a `bot` project, then `blocks.py add web,api,postgres --from
  <template>` — `check` ok, and that project's own e2e 7/7.
