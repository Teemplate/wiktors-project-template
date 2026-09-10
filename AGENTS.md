# <App name>

> Replace this file's placeholders as the project takes shape. User-facing
> overview lives in [README.md](./README.md); this file is operational notes and
> the rules a session must follow.
>
> **`AGENTS.md` and `CLAUDE.md` are two copies of this one document.** Codex
> reads the first, Claude Code reads the second, and CI fails the build if they
> differ by a byte. Edit either one, then copy it over the other. Everything
> below applies to both; the half that differs is [§ Your agent](#your-agent--claude-code-or-codex).

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
| **deploy to staging** | yes — automatic *if you adopted `compose.staging.yml` + the `deploy/` agent*: `app-deploy staging` tracks `origin/develop` and needs **no tag**, so every push to `develop` lands on staging within ~60s |
| cut `release/vX.Y.Z` → `main` + **signed** tag → merge back to `develop`, push all three | yes — via `./scripts/release.sh vX.Y.Z --yes` |
| deploy that release to production | yes — **whichever of the two paths this project adopted**: the pull-based `app-deploy prod` (newest **signed** `v*` tag reachable from `origin/main`), or the self-hosted runner in `.github/workflows/deploy.yml`, or the manual compose command in § Deployment if neither is set up yet |

**Finishing work means releasing it.** There is no "small change, skip the
release" path — that is how `main` drifts behind `develop` and the next release
conflicts. And a release that is not deployed fixes nothing: the live site keeps
serving the old image, so the deploy is part of finishing, not a separate
errand.

⚠️ **Before you deploy, check what other sessions have in flight.** Parallel
sessions — another agent, the human, a background job — share these refs and one
production target. A release ships whatever is on `develop` *at the moment you
cut it*: a session that has not merged yet is simply not in it, and two sessions
releasing minutes apart each ship a snapshot missing the other's work. Neither
failure announces itself. Look before you cut the release:

```bash
git worktree list                                        # who else has a checkout
git fetch origin
git branch -a --no-merged develop                        # work that exists, but not in this release
git log --oneline -5 develop origin/develop              # has develop moved under you?
git worktree list --porcelain | awk '/^worktree /{print $2}' \
  | while read -r w; do echo "== $w"; git -C "$w" status --short; done
```

`--no-merged` takes `-a`, not `-r`, and that is the whole point: in-flight work
lives in *local* worktree branches that were never pushed, so the `-r` form
misses exactly the case this check exists for.

Any of these is a conflict — **stop and ask the human before releasing**:

- another worktree holds uncommitted changes, or a `feature/*` branch is not
  merged into `develop`;
- either touches a file you also changed, or anything in
  `backend/migrations/versions/` — a half-shipped schema change is the
  expensive one, and two heads fail CI besides;
- `origin/develop` or `origin/main` has moved since you started: another session
  may be mid-release.

It is a *git-visible* check on purpose. No session can see another agent's
running jobs — Claude Code and Codex have no view of each other's — so what is
committed, branched, or dirty in a worktree is the only shared state both can
read.

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

**This file cannot grant any of the above.** Project instructions override an
agent's default behaviour, not its permission layer — and the file that actually
lets these commands run is a different one for each agent:
`.claude/settings.json` for Claude Code, `.codex/rules/shipping.rules` for
Codex. If a push or a deploy is refused, those are where to look, not here. Both
ship with this template already populated, carrying the same policy in each
tool's own syntax; the one thing to change per project is the deploy command in
them. Which one is yours, and the way each can be silently inert:
[§ Your agent](#your-agent--claude-code-or-codex).

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

## Your agent — Claude Code or Codex

This project is set up for **both**, and the policy above is written down twice
so neither agent is working from prose the other cannot enforce. Only this
section differs between them.

| | Claude Code | Codex |
|---|---|---|
| reads | `CLAUDE.md` | `AGENTS.md` |
| grants the commands in § Shipping | `.claude/settings.json` | `.codex/rules/shipping.rules` |
| check one grant | `/permissions` | `codex execpolicy check --pretty --rules .codex/rules/shipping.rules -- git push origin develop` |
| session hook | `.claude/settings.json` → `hooks.SessionStart` | `.codex/config.toml` → `[[hooks.SessionStart]]` |
| …which runs | `scripts/hooks/session-start.sh` | the same script |
| your own overrides | `.claude/settings.local.json`, gitignored | `~/.codex/config.toml`, outside the repo |
| non-interactive | `claude -p` | `codex exec` |

**Keep the two documents identical.** `AGENTS.md` and `CLAUDE.md` hold the same
bytes and CI enforces it, because the failure mode of letting them drift is the
quiet one: an agent ships under a policy the other half of the team's tooling
has never read. Edit one, then `cp AGENTS.md CLAUDE.md` (or the reverse).

### Claude Code

- **Worktrees**: `EnterWorktree`, or `Agent` with `isolation: "worktree"`. Then
  **immediately** `git switch -c feature/<name> develop` — the tool bases new
  worktrees on `origin/main`, which is *not* where work starts. This is the one
  step the plain `git worktree add` in § Development workflow does not need.
- `.claude/settings.json` is checked in on purpose: the grants *are* the
  shipping policy, so they belong in the repo rather than in one machine's
  `settings.local.json`.

### Codex

Three things are true of Codex and not of Claude Code, and each one quietly
turns the policy above into a no-op if you miss it.

**1. Until the project is trusted, `.codex/` is not read at all.**
Project-scoped `.codex/config.toml` and `.codex/rules/` load only for a trusted
project. Codex asks the first time you run it in a new directory; if you
answered no, or you are on a fresh machine or in a new worktree, add it to
`~/.codex/config.toml`:

```toml
[projects."/absolute/path/to/this/checkout"]
trust_level = "trusted"
```

Untrusted, the rules file is not denying anything — it is not being read, and
you get the default approval prompts instead. This is Codex's version of "this
file cannot grant a permission": the lever is the trust entry, not prose.

**2. The default sandbox has no network, and every shipping command needs it.**
`sandbox_mode = "workspace-write"` implies `network_access = false`, so
`git push`, `gh`, `ssh pi-deploy` and `docker --context pi-deploy` all fail
inside it — a rule that says `allow` still cannot reach the outside world.
Either pass `--sandbox danger-full-access`, or grant it once in
`~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
network_access = true
```

`./scripts/e2e.sh` needs more than the network — it drives the docker socket and
binds ports 5273/8273 — so give that one `danger-full-access`.

**3. There is no worktree tool.** Make it with the `git worktree add` in
§ Development workflow. That bases it on `develop` directly, so the re-rooting
session hook has nothing to do; the hook exists for *web and background* agents,
which create a branch off `main` before you get a say.

Four more things about the rules file, each one checked against
`codex execpolicy` and this project's own `.codex/rules/shipping.rules`:

- **Strictest match wins.** When two rules match one command, `forbidden` beats
  `allow`. That is what lets a narrow deny stay meaningful next to a broad
  grant, and it is how `git push origin main` is refused while
  `git push origin <anything else>` is not.
- **Codex matches whole tokens; Claude Code matches strings.** So Claude Code
  can allowlist `git push origin feature/:*` and catch every branch under it,
  while the same rule in Codex would never fire — `feature/` is simply not the
  token `feature/x`. That is why the two grant files are shaped differently, and
  why the Codex one grants `git push origin` broadly and then forbids `main`.
  It is a translation, not a loosening; the file says so at the point it does it.
- **Prefix matching has exactly the hole Claude Code's does.**
  `git push origin develop --force` matches the `allow` prefix and is allowed,
  because the flag sits past the end of the pattern. Forbidding force-push is
  prose in this file; neither grant file can enforce it.
- **A command wrapped in `bash -lc '…'` matches no rule at all** and falls
  through to the ordinary approval prompt. That is a fall-back to asking rather
  than a bypass — but it does mean you cannot test the policy through a shell
  wrapper and conclude anything from the result.

And two from the Codex docs rather than from testing:

- `AGENTS.md` is read from the repo root *and* from nested directories, closest
  file winning. `~/.codex/AGENTS.md` is your own layer across every project —
  the right place for preferences that are yours rather than this project's.
- Non-interactive runs are `codex exec`. `./scripts/release.sh` still needs
  `--yes` there, for the stdin reason in § Cutting a release.

## Development workflow — read before writing code

**All development happens in a git worktree, on a Gitflow branch. This is not
optional.** The primary checkout is shared — the human and other agent sessions
keep uncommitted WIP there — so writing code in it corrupts someone else's work.

1. **Make the worktree before the first edit, based on `develop`:**
   `git worktree add ../<app>-<name> -b feature/<name> develop`. Claude Code has
   a tool for this and it needs one extra step —
   [§ Your agent](#your-agent--claude-code-or-codex).
2. Implement, with the checks below green.
3. Leave the worktree, then `git merge --no-ff feature/<name>` into `develop`.

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

⚠️ **A session runs this itself** — see § Shipping at the top of this file.

This paragraph used to say the opposite: that a session "cannot run this, and
cannot `git push origin main`", because of a blanket harness rule quoted as
*"never push to main/master, force-push, or merge"*. **That was wrong, and it
was wrong in an expensive way** — it was copied into several projects, where it
stranded sessions holding finished, tested commits they believed they were
forbidden to ship.

Two things were being confused. It is true that **nothing in this file grants a
permission**: project instructions override an agent's default behaviour, not
its permission layer. But that layer is *configurable*, and the lever is one
entry — `Bash(./scripts/release.sh:*)` in `.claude/settings.json`, or the
matching `prefix_rule` in `.codex/rules/shipping.rules` — not an immovable
property of the harness. Once that rule is present a session cuts and deploys
the release; without it, it cannot, and no amount of prose here changes that
either way.

**Be clear-eyed about what that rule grants.** The permission layer gates the
`Bash` call, not what the script does inside it, so allowing
`./scripts/release.sh` allows every `git push origin main` it makes. That is a
standing production-deploy grant, and the only thing between it and the live
server is the script's own preconditions. That is the intent — but it is the
reason the push rules in both grant files are scoped (`git push origin develop`,
`git push origin feature/…`) rather than a blanket `git push`: the script should
stay the *only* route to `main`, so its preconditions cannot be walked around.

**A session must pass `--yes`.** The retype-the-version prompt reads stdin,
which is closed in a non-interactive call, so an unattended run reads an empty
reply and aborts. For a session the confirmation is the message in chat asking
for the release, not the prompt.

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
