# Developing in this repo

Gitflow, in a git worktree, with the checks green before anything merges.
`AGENTS.md` (and its identical twin `CLAUDE.md`) carries the short version
every session loads; this is the full procedure and the gotchas.

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

**Before every merge** — all fast, none needs a secret:

```bash
cd backend  && pytest                # needs no database and no secrets
cd frontend && npm run typecheck     # tsc --noEmit
cd frontend && npm test              # vitest unit tests
cd frontend && npm run build         # catches what typecheck alone does not
docker compose -f compose.deploy.yml config --quiet
```

**Before merging anything that touches the API surface, nginx, a migration or
the seed** — the full stack, for real:

```bash
./scripts/e2e.sh            # builds, migrates, seeds, runs Playwright, tears down
./scripts/e2e.sh --keep     # leave it up to poke at
./scripts/e2e.sh --ui       # Playwright UI mode
```

It stands up a disposable stack on ports 5273/8273 (override with
`E2E_WEB_PORT`/`E2E_API_PORT`), with Postgres on **tmpfs** so nothing survives
the run. It **refuses to start the browser tests unless the seed produced
rows** — against an empty list every UI assertion passes vacuously.

**Never run `next lint`** on a Next.js variant of this template — it prompts
interactively and will hang a CI runner or an agent session. Use `eslint`
directly.

CI runs the fast checks on every push and PR. The e2e suite runs nightly, on
demand, and on any PR labelled `run-e2e` — it is deliberately not a required
check, because a gate people learn to wait out is a gate they learn to ignore.
Keep everything secret-free: a fresh clone with no `.env` must pass.

## 4a. Schema changes

The schema is owned by Alembic. Never create tables with
`Base.metadata.create_all()` — migrations and reality drift permanently apart
the first time you do.

```bash
cd backend
alembic revision --autogenerate -m "add the thing"   # review the file it writes
alembic upgrade head
alembic downgrade base && alembic upgrade head       # prove it round-trips
python -m app.seed                                   # keep the seed in step
```

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

- **Backend:** add to `requirements.txt` **pinned to an exact version**. An open
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
