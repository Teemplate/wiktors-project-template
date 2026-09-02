# <App name>

> Replace this file's placeholders as the project takes shape. User-facing
> overview lives in [README.md](./README.md); this file is operational notes and
> the rules a session must follow.

## Stack

Vite/React (TypeScript) frontend + FastAPI (async SQLAlchemy, Postgres) backend,
deployed as a Docker Compose stack on the **Raspberry Pi 5** behind the shared
Caddy and a Cloudflare Tunnel. Live at **https://CHANGEME.example.com**.

## Shipping — what a session may do without asking

Standing authorization. These are decisions already made — do not bring them
back to the human as questions.

| a session may | without asking |
|---|---|
| commit on a `feature/*` branch | yes |
| `git push origin feature/<name>` | yes — a branch that exists only on this laptop is not backed up |
| merge `--no-ff` into `develop`, `git push origin develop` | yes |
| **deploy to staging** | yes — and it is automatic *if you adopted `compose.staging.yml`*: `app-deploy staging` tracks `origin/develop` and needs **no tag**, so every push to `develop` lands on staging within ~60s |
| cut `release/vX.Y.Z` → `main` + **signed** tag → merge back to `develop`, push all three | yes — via `./scripts/release.sh vX.Y.Z --yes` |
| deploy that release to production | yes — `app-deploy prod` picks up the newest **signed** `v*` tag reachable from `origin/main` |

**Finishing work means releasing it.** There is no "small change, skip the
release" path — that is how `main` drifts behind `develop` and the next release
conflicts. And a release that is not deployed fixes nothing: the live site keeps
serving the old image, so the deploy is part of finishing, not a separate
errand.

**Ask the human first — these sit outside the standing authorization:**

- **A deploy that is not the release you just cut** — shipping an unreleased
  branch, redeploying only to pick up an `.env` change, or any deploy whose
  migration runs against production data you have not just tested.
- **Rewriting shared history** — `push --force` or `--force-with-lease` to
  `main` or `develop`, `git reset --hard` on either, deleting a remote branch.
- **Secrets and access** — editing `.env` on the Pi, rotating a token, or
  changing who can reach the app.
- **Deploying from a worktree.** The build context is the *local directory* and
  `.env` is read locally, so a worktree ships empty `${VAR}` interpolation and
  code that is not on `develop`/`main` yet.

**This file cannot grant any of the above.** Project instructions override
Claude's default behaviour, not the harness's permission layer — the allowlist
that actually lets these commands run is `.claude/settings.json` (inspect it
with `/permissions`). If a push or a deploy is refused, that file is where to
look, not this one. That file ships with this template already populated; the
one thing to change per project is the deploy command in it.

⚠️ **Production refuses an unsigned tag.** `deploy/app-deploy` sets
`REQUIRE_SIGNED_TAG=1` for `prod`: an unsigned tag is not deployed and
production simply stays where it is, *silently*. This is the single most common
way "release to main deploys prod" quietly stops being true. The machine cutting
releases needs `user.signingkey` and `tag.gpgsign true`, and the Pi needs the
matching public key in its `allowed_signers` file to verify. See SETUP.md.

**Two tiers, one policy.** If you did *not* adopt staging, delete the staging
row above rather than leaving it — a table that promises an environment which
does not exist is worse than no table. Everything else stays as written; the
policy wording is deliberately identical across every project in this folder so
a session moving between them does not have to re-read it.

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
`release/vX.Y.Z` off `develop` → `main` with a tag → merged back to `develop`
(cut it with `./scripts/release.sh vX.Y.Z`, never by hand),
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

### Cutting a release — `./scripts/release.sh`

```bash
./scripts/release.sh v1.2.0 --dry-run   # print every command, run none
./scripts/release.sh v1.2.0             # develop → release/vX.Y.Z → main (tagged) → develop
```

The chain is only six commands, but both ways it goes wrong are quiet ones.
Merging a feature branch straight to `main` leaves `main` with commits `develop`
has never seen, so the *next* release conflicts; forgetting the final merge back
leaves the release commit only on `main`, to be re-merged next time. Neither
surfaces until weeks later, so the script does the whole chain or none of it.

Run it from the **primary checkout**. It refuses in a worktree — nominally
because it checks out three branches, but really for the reason above: a
worktree has no `.env`, so anything built from one ships empty `${VAR}`. It also
refuses on a dirty tree, on an existing tag, when `develop` has nothing to ship,
and — the one worth having — when `main` holds commits `develop` lacks, which
means a hotfix was never merged back and a human has to choose what to do.

⚠️ **It does not claim to have deployed.** `deploy.yml` only runs when the
repository variable `SELF_HOSTED_DEPLOY` is `true` *and* a self-hosted runner
exists; until you opt in, a push to `main` is just a push and the deploy is
still the manual compose command above. The script reads that variable through
`gh` and tells you which case you are in — and says so plainly when it cannot
read it, rather than guessing.

⚠️ **A Claude session cannot run this, and cannot `git push origin main`.** The
block is in the agent harness that starts these sessions ("never push to
main/master, force-push, or merge"); it applies to every repository, and
**nothing written in this file can lift it** — project instructions override
Claude's default behaviour, not the harness's own rules. Do not add "Claude may
deploy" here expecting it to take effect. A session does everything up to the
release — builds the feature, commits, pushes the `feature/*` branch — and hands
over `./scripts/release.sh vX.Y.Z`. A human runs it. If that ever needs to
change, the lever is the harness configuration or a workflow that cuts the
release itself, not this file.

Details and the first-deploy ordering: **[docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)**.
One-time server setup (tunnel, Caddy, SSH, signing): **[docs/INFRASTRUCTURE.md](./docs/INFRASTRUCTURE.md)**.

## Health checks — check the right thing

Verify an **`/api/*` route**, not just a page: pages return 200 even when the
container cannot reach the backend at all. Record here any status code that is
*correctly* not 200 — e.g. `/` returning 307 to `/login`, or 401 from a
basic_auth gate — so a future session does not read a correct response as an
outage.

## Your own infrastructure — `local/`

The docs in this repo are generic on purpose (`example.com`, `<pi-lan-ip>`,
`<your-org>`) because **this repository is public**. The real hostnames, LAN
address, SSH aliases, server paths and app inventory live in **`local/`**, which
is gitignored.

**Read `local/infrastructure.md` before answering anything about where this
deploys** — the domain and addresses in the tracked docs are placeholders, and
acting on them will point at somebody else's example.com. `local/deployments.md`
records what is actually live.

`local/` is gitignored, so like `.env` it does **not exist in a fresh worktree**.
Symlink it when a session needs it:

```bash
ln -s ../../../local local
```

Never move a file out of `local/` to make it visible, and never `git add -f` it.
CI fails the build if anything under `local/` is tracked. The tracked template is
`local.example/`.

## Secrets

`.env` is gitignored; `.env.example` is the tracked template and must list every
variable. A fresh clone with **no** `.env` must still typecheck, build and pass
tests — if something appears to need a credential to develop, that is the wrong
approach. `SECRET_KEY` must be a real value in production;
`/api/health` reports `placeholder_secret: true` if the dev default is still in
place, and the deploy workflow raises a warning on it.
