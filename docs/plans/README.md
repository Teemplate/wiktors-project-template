# `docs/plans/` — one file per feature, and the pipeline's only durable state

Every feature that goes through the agentic pipeline
([§ Agentic pipeline](../../CLAUDE.md)) gets exactly one file here, named
`<feature>.md`. The brief is committed to `develop` before the agent is
spawned — so the worktree cut from `develop` actually has it — and from then on
the agent updates it **on the feature branch**, where it merges back with the
code.

**It is tracked on purpose.** The plan travels with the branch, shows up in the
merge diff, and — the part that matters — survives everything the conversation
does not. A long orchestrator session gets summarized; a laptop reboots; you
come back on Monday. None of that can be allowed to lose which features exist
and what stage each one is at, so none of that state lives in an agent's head.
The file and the git refs are the ground truth, and `/feature status` rebuilds
the whole picture from them.

**This repository is public.** Plans are read by anyone. Keep real hostnames,
LAN addresses and server paths out of them — those live in `local/`.

## The frontmatter contract

```yaml
---
feature: user-avatars                      # kebab-case; matches the filename
branch: feature/user-avatars               # always feature/<feature>
worktree: .claude/worktrees/user-avatars   # or "removed"
stage: awaiting-deploy-approval
design: https://…                          # Claude Design canvas URL, or "n/a"
agent: feature-dev-user-avatars            # in-session agent name, or "none"
opened: 2026-09-12
---
```

Every field is required; write `n/a` or `none` rather than omitting one, so a
missing field always means the file is malformed rather than merely quiet.
`worktree:` is a repo-relative path while the worktree exists, `none` before one
is created, and `removed` after it is cleaned up — those three, nothing else.

### Which copy is the real one

**While a feature is in flight, the live version of its plan file is on its
branch.** `develop` holds the brief the orchestrator committed before spawning
the agent, and sees nothing more until the feature merges. So anything reading a
plan file for an active feature reads it from the branch:

```bash
git show feature/<feature>:docs/plans/<feature>.md
```

Reading the working-tree copy instead gets a stale `stage: brief` and an empty
`## Touches` — which looks like a feature that has not started rather than an
error, and is why `/feature status` and the collision check both go through
`git show`.

### `stage` — the state machine

| stage | means | who moves it next |
|---|---|---|
| `brief` | `/ideate` wrote the idea down; no agent spawned yet | orchestrator |
| `planning` | agent is drafting the plan | agent |
| `awaiting-answers` | agent ended its turn holding questions for the human | human, via orchestrator |
| `awaiting-plan-approval` | plan (and design canvas, if frontend) ready to read | human |
| `building` | plan approved; agent is implementing | agent |
| `awaiting-deploy-approval` | built, checks green, branch pushed — **the hard stop** | human |
| `parked` | human said stop; branch pushed, worktree removed, nothing merged | human, whenever |
| `shipped` | merged to `develop`, released, deployed, verified | — |

The two `awaiting-*-approval` stages are the only two gates. Everything else
moves without asking, under the standing authorization in CLAUDE.md.

### `agent` is a weak reference — the plan file is the strong one

The orchestrator resumes a running agent with `SendMessage`, which keeps its
context so a replan or a fix does not start from a blank slate. But agent names
are **session-scoped**: end the session and they are gone, even though `stage`
still says `building`. That is not a corrupt state. Set `agent: none` and spawn
a fresh `feature-dev` pointed at this file — the plan, the `## Touches` list and
the branch are everything a new agent needs. Losing the conversation costs
context, never work.

## The body

Sections in this order. Keep them even when empty, so the shape stays diffable.

```markdown
# <Feature title>

## Brief
What the human wants, in their framing. Written by /ideate or the orchestrator.
Never rewritten by the agent — the plan goes below, not here.

## Plan
Files, order, migrations, risks, and what is explicitly out of scope.

## Questions
Anything blocking, as a numbered list. The orchestrator relays these verbatim
and writes the answers underneath. Empty when nothing is blocked.

## Touches
Paths and globs this feature changes. Read literally by the pre-release
overlap check — see below.

## Checks
Which of pytest / typecheck / vitest / e2e.sh this feature requires, and the
last result with a date.
```

## `## Touches` is load-bearing

CLAUDE.md's pre-release check asks whether other in-flight work collides with
the release being cut. Before this pipeline existed, *any* unmerged `feature/*`
branch was treated as a conflict — sound when unmerged branches were rare, and
useless here, where parked features are a normal steady state and that rule
would block every release forever.

So the check got narrower, and `## Touches` is what it reads. A parked or
in-flight feature is a conflict when, and only when, it

- lists a path the release also changes, **or**
- lists anything under `backend/migrations/versions/` while the release does too
  — two migration heads fail CI, and a half-shipped schema change is the
  expensive failure, **or**
- has no plan file at all, because then it is not this pipeline's work and
  nobody can say what it touches.

Be generous writing it. A path listed that you did not touch costs one question;
a path omitted costs a silent collision, which is the failure this section
exists to prevent. Write directories or globs when a feature ranges widely
(`frontend/src/components/**`), not a guessed file list.
