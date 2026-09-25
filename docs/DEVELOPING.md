# Developing in this repo

Gitflow, in a git worktree, with the checks green before anything merges.
`AGENTS.md` (and its identical twin `CLAUDE.md`) carries the short version
every session loads; this is the full procedure and the gotchas.

Gitflow is paired with **[model routing](./MODEL-ROUTING.md)**. For substantial
Codex features, Astra plans, Terra implements, the checks provide evidence,
and Sol or Astra handles failures that need stronger diagnosis. These stages
run serially in the same feature worktree and exchange state through the plan,
diff and check results. A tiny, low-risk change can remain on Terra throughout.

## 1. Always develop in a worktree

The primary checkout is shared: the human and any number of parallel agent
sessions work there, and it usually holds uncommitted WIP that is *not* yours.
Before the first edit, move into a worktree. Codex has no tool for this — use
the `git worktree add` below. Claude Code has **`EnterWorktree`** (a dispatched
agent gets the same from `Agent`'s `isolation: "worktree"`), which bases the
worktree on `origin/main`, so it needs `git switch -c feature/<name> develop`
immediately afterwards.

```bash
# after EnterWorktree — do this immediately, before any edit
git switch -c feature/<name> develop
```

**That `git switch` is not optional.** `EnterWorktree` bases the new worktree on
`origin/<default-branch>`; Gitflow features start from `develop`. Skip it and
you branch from the wrong base and silently miss everything released since.

What a worktree does and does not isolate:

- **Isolated: the working tree and index.** Your edits cannot collide with
  another session's WIP, and git's branch-checkout exclusivity keeps two
  worktrees off the same branch — so every session sits on its own
  `feature/<name>` and nobody has to stash anything.
- **Shared: refs, objects, tags, config and the stash.** That is the point —
  merging your feature into `develop` is visible everywhere at once. It also
  means `git stash` is repo-wide: **never** use bare `git stash`/`git stash pop`,
  because another session may pop your entry. Use a WIP commit instead.
- **Absent: everything gitignored.** A fresh worktree has no `.env`, no
  `backend/.venv`, no `frontend/node_modules`, no `dist/`, and no `local/`.
  Four consequences:
  1. **Symlink what the checks need**, or run them in the primary checkout.
  2. **Never deploy from a worktree** (see §5).
  3. Merging into `develop` has to happen where `develop` is checked out —
     normally the primary checkout. `ExitWorktree` first.
  4. `local/` holds the real hostnames and server paths, so a session in a
     worktree is working from placeholders until you symlink it:
     `ln -s ../../../local local`.

  > When you symlink these, note that the ignore rules for them are written
  > **without a trailing slash** (`local`, `node_modules`, `dist`). `foo/`
  > matches only a real directory — a *symlink* named `foo` stays untracked but
  > visible, and `git add -A` commits a link pointing into your home directory.
  > CI has a step that fails if that regression is reintroduced for `local`.

## 2. Branch roles

| branch | forks from | merges into | notes |
|---|---|---|---|
| `main` | — | — | release history, **tagged only**; never commit feature work directly |
| `develop` | `main` | — | integration branch; the parent of every feature |
| `feature/<name>` | `develop` | `develop` | never interacts with `main` |
| `release/vX.Y.Z` | `develop` | `main` **and** `develop` | no new features — fixes, docs, release chores; `main` gets the tag |
| `hotfix/<name>` | **`main`** | `main` **and** `develop` | the only branch forking off `main` |
| `experimental/<name>` | `develop` | **nothing** | research, not product — see below |

**`experimental/<name>` is research that never ships**: prototypes, spikes,
benchmarks, parameter sweeps, the data they produce. It never merges into
`develop` or `main`, CI does not run on it, and it is pushed for backup only.
It is **not** unfinished feature work: it shows up in
`git branch -a --no-merged develop` by design, so never "finish", merge or
delete one as cleanup. When something on it turns out to be worth shipping,
the code leaves on a fresh `feature/<name>` off `develop` carrying just that
code — never the branch itself, which drags its data along. Keep production
hosts from downloading these branches at all by fetching only what they
deploy (`DEPLOYMENT.md` § Production hosts fetch only `main`).

Commit messages are conventional: `feat(scope): …`, `fix(scope): …`,
`docs(dev): …`. Merge commits read `Merge feature/<name> into develop`.

## 3. The command sequences

**Feature** (the everyday path):

```bash
# in a worktree
git switch -c feature/<name> develop
# … implement + test …
git commit -am "feat(scope): …"

# where develop is checked out (primary checkout)
git switch develop
git merge --no-ff feature/<name>
git branch -d feature/<name>
```

`--no-ff` is deliberate: one merge commit per feature keeps the history
readable.

**Release:**

```bash
git switch -c release/vX.Y.Z develop
# … release chores only ­— docs, changelog, no new features …
git switch main
git merge --no-ff release/vX.Y.Z
git tag -a vX.Y.Z -m "Release vX.Y.Z — <headline>"
git switch develop
git merge --no-ff release/vX.Y.Z      # critical: fixes made on the release branch
git branch -d release/vX.Y.Z
git push origin main develop --tags
```

**Hotfix** (production is broken and `develop` is not shippable):

```bash
git switch -c hotfix/<name> main
# … minimal fix + test …
git switch main && git merge --no-ff hotfix/<name>
git tag -a vX.Y.Z+1 -m "Hotfix vX.Y.Z+1 — <what broke>"
git switch develop && git merge --no-ff hotfix/<name>
git push origin main develop --tags
```

> **Finishing work means releasing it.** There is no "small change, skip the
> release" path — that is how a real project's `main` once
> drifted 80 commits behind `develop`. A release that is not deployed also fixes
> nothing: the live site keeps serving the old image.

## 4. Checks

**Before every merge** — all fast, none needs a secret. Run the lines for the
blocks this project has (`python3 scripts/blocks.py checks` prints exactly
those):

```bash
cd backend  && pytest                # api / worker / postgres — no database, no secrets
cd frontend && npm run typecheck     # web — tsc --noEmit
cd frontend && npm test              # web — vitest unit tests
cd frontend && npm run build         # web — catches what typecheck alone does not
python3 scripts/blocks.py check      # blocks.json, the files and the compose agree
```

Changed a compose fragment (`frontend/compose/`, `backend/compose/`)? Run
`python3 scripts/blocks.py sync` to regenerate the root files — they are
`include:` lists, never edited by hand — and see [BLOCKS.md](./BLOCKS.md).

**Before merging anything that touches the API surface, nginx, a migration or
the seed** — the full stack, for real:

```bash
./scripts/e2e.sh            # builds, migrates, seeds, runs Playwright, tears down
./scripts/e2e.sh --keep     # leave it up to poke at
./scripts/e2e.sh --ui       # Playwright UI mode
```

It stands up a disposable stack of this project's blocks on ports 5273/8273
(override with `E2E_WEB_PORT`/`E2E_API_PORT`), with Postgres on **tmpfs** so
nothing survives the run. With `postgres` it **refuses to start the browser
tests unless the seed produced rows** — against an empty list every UI
assertion passes vacuously. With `worker` it waits for a healthy heartbeat.
Without `web` the stack checks are the whole suite.

CI runs the fast checks on pushes to `develop` and `main` and on every PR —
not on feature-branch pushes, so run the relevant checks locally before you
merge. The e2e suite runs weekly, on demand, and on any PR labelled `run-e2e` —
it is deliberately not a required check, because a gate people learn to wait
out is a gate they learn to ignore. Keep everything secret-free: a fresh clone
with no `.env` must pass.

### Actions minutes

Projects made from this template are usually **private**, and private
repositories share the account's monthly allowance of GitHub-hosted Actions
minutes (3,000 on GitHub Pro; public repositories and self-hosted runners cost
nothing). The account has a **$0 Actions budget with "stop usage" on**, so
running out costs nothing but **stops every hosted workflow in every private
repo until the 1st of the month**, including CI that a deploy waits on. In
September 2026 the estate reached 90% by the 25th. The causes, and the rules
that follow from them:

- **Every job bills at least one minute, rounded up.** A workflow of five
  ten-second jobs costs five minutes. Put a new cheap check in an existing job
  as a step (with `if: ${{ !cancelled() }}` so one failure does not hide the
  next) rather than adding a job. Jobs skipped by an `if:` cost nothing, which
  is why `ci.yml` gates each job on the blocks present.
- **Trigger on the branches that matter.** `ci.yml` runs on `develop`, `main`
  and PRs, with `concurrency` cancelling a superseded run. Do not add
  `feature/**` back to `push`: agent sessions push often, and that alone spent
  hundreds of minutes a month per active project.
- **Schedules are paid for every time.** `e2e.yml` runs weekly. A scheduled
  job that must stay on GitHub's runners (a monitor that alerts when the Pi is
  offline) still bills a minute per run: hourly is ~720 minutes a month,
  every three hours ~240.
- **Filter checks by path.** `agent-context.yml` runs only when agent context
  or documents change.
- **Heavy or frequent CI can run on the Pi.** A self-hosted runner
  ([DEPLOYMENT.md](DEPLOYMENT.md#self-hosted-runner-what-githubworkflowsdeployyml-expects))
  costs no minutes. The Pi is Ubuntu on arm64: `actions/setup-node` works, but
  `actions/setup-python` has no builds for it, so install Python with `uv`
  (`astral-sh/setup-uv`, then `uv venv --python 3.12 "$RUNNER_TEMP/venv"`) and
  keep the venv outside the checkout. Jobs share the Pi with production and run
  one at a time. Only a private repository may use it, because a PR's code runs
  on the Pi.

Check usage at <https://github.com/settings/billing/usage>, and per workflow
with `gh run list`.

## 4a. Schema changes

The schema is owned by Alembic. Never create tables with
`Base.metadata.create_all()` — migrations and reality drift permanently apart
the first time you do.

These apply to projects with the **postgres** block.

```bash
cd backend
alembic revision --autogenerate -m "add the thing"   # review the file it writes
alembic upgrade head
alembic downgrade base && alembic upgrade head       # prove it round-trips
python -m app.seed                                   # keep the seed in step
```

With the dev stack up, `docker compose up migrate` applies a new revision and
`docker compose run --rm migrate python -m app.seed` seeds.

Three things CI enforces, each of which has cost real time in production:

- **Exactly one head.** Two feature branches that each autogenerate a revision
  produce sibling heads, and `alembic upgrade head` then fails *on the Pi at
  deploy time* rather than in CI. Fix by re-pointing the newer revision's
  `down_revision` at the other.
- **Up and back down against an empty database**, so a revision that cannot be
  applied from scratch is caught before a fresh environment needs it.
- **No `drop_table`/`drop_column` in `upgrade()`** without the `destructive-ok`
  label on the PR. Data loss is not reversible by a rebuild.

Update `app/seed.py` in the same commit as the migration. A seed that no longer
matches the schema breaks `scripts/e2e.sh` and every fresh clone.

## 5. Never deploy from a worktree

The deploy command uses the *checked-out directory* as the Docker build context
**and reads `.env` locally**. From a worktree that means empty `${POSTGRES_*}`
interpolation, no secrets, and shipping code that is not on `develop`/`main`
yet. Deploy from the primary checkout, on `main`, always.

## 6. Adding a dependency

- **Backend:** add to `requirements.txt` **pinned to an exact version**, inside
  the `# block:` section of the block that needs it, so it leaves with that
  block. An open
  range once resolved to a breaking 2.0.0 release on a fresh Pi install while the
  dev machine stayed on an old cached 1.x — the failure appeared only in
  production.
- **Frontend:** `npm install <pkg>` and **commit `package-lock.json`**. CI uses
  `npm ci`, which fails without it.

## 7. Working for a non-technical stakeholder

If someone who is not a developer requests changes:

- **Take their description, not their diagnosis.** "Too cramped" is the
  requirement; the padding value is your job.
- **Never ask them for a secret.** Frontend work needs none.
- Change design tokens rather than individual components for colour/spacing.
- Follow the normal flow — branch, checks, merge to `develop`. They see the
  result on staging, which is the point.
- **Never tag or deploy to production on their behalf.** That gate is deliberate.
