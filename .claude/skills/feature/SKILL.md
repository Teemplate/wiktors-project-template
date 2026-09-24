---
name: feature
description: Run the agentic feature pipeline as orchestrator — take a feature idea, hand it to a feature-dev agent for planning, relay the plan for human approval, hand back for the build, then gate on deploy approval and ship it. Also `/feature status` to see every feature in flight. Use when the user describes something to build, approves or rejects a plan or a deploy, or asks where a feature stands.
---

You are the **orchestrator**. You do not write the feature's code — a
`feature-dev` agent does, in its own worktree. You talk to the human, spawn and
resume that agent, and you alone merge, release and deploy.

Read `CLAUDE.md` (§ Shipping, § Development workflow) and
[`docs/plans/README.md`](../../../docs/plans/README.md) before acting. The plan
file contract in the latter is the state machine you are driving.

**Claude Code only.** Codex has no Agent tool, no worktree tool and no
SendMessage. A Codex session ignores this skill and follows § Development
workflow by hand.

## The human has exactly six moves

Everything they say maps to one of these. If a message maps to none of them —
a question, a correction, a new idea mid-flight — answer it normally; only these
six change a feature's stage.

| they say | you do |
|---|---|
| **ideate** — describe something to build | create the plan file, spawn `feature-dev` in PLAN mode |
| **approve plan** | resume the agent in BUILD mode |
| **revoke plan + update** — "replan: …" | resume the agent with the feedback, still in PLAN mode |
| **revoke plan + stop** | park the feature |
| **approve deploy** | run the ship sequence below |
| **revoke deploy + update** | resume the agent in BUILD mode with the feedback |
| **revoke deploy + stop** | park the feature |

Never ask them to do anything else. Picking the version number, resolving a
merge, choosing whether to run e2e — those are yours.

## Ideate → plan

1. Pick a kebab-case `<feature>` name. Check `docs/plans/<feature>.md` does not
   already exist.
2. If `/ideate` already wrote a brief, use it. Otherwise write the plan file
   yourself with full frontmatter, `stage: brief`, and the human's framing in
   `## Brief` — their words, not your paraphrase.
3. **Commit the brief to `develop` and push it, before you spawn anything:**

   ```bash
   git add docs/plans/<feature>.md
   git commit -m "docs(plans): brief for <feature>"
   git push origin develop
   ```

   This is not bookkeeping. The agent's worktree is cut from `develop`, so a
   brief that is only in your working tree simply is not there when the agent
   goes looking for the path you gave it. Committing first means every branch
   cut afterwards inherits the file, and `/feature status` can see the feature
   exists before any branch does.

4. Spawn the agent:

   ```
   Agent(
     subagent_type: "feature-dev",
     isolation: "worktree",
     description: "Plan <feature>",
     prompt: "Mode: PLAN. Plan file: docs/plans/<feature>.md. Branch: feature/<feature>.
              <the brief, verbatim>"
   )
   ```

   Record the agent's name in the `agent:` field and set `stage: planning`.

5. The agent runs in the background and notifies you when it finishes. **Do not
   fabricate its result.** If the human asks before it lands, say it is still
   running.

## Where the plan file actually lives — read this before writing any check

From the moment the agent creates its branch, **the current version of a plan
file is on that branch, not on `develop`.** `develop` keeps the brief you
committed in step 3 and does not see another word until the feature merges. So
your working tree is the wrong place to look, and every check below reads the
branch instead:

```bash
git show feature/<feature>:docs/plans/<feature>.md
```

Enumerate features from the branches themselves:

```bash
git for-each-ref --format='%(refname:short)' refs/heads/feature/
```

Get this wrong and both things it feeds fail *quietly*: `/feature status`
reports stale stages, and the collision check decides no in-flight branch has a
plan file — which sends every release back to the old strict answer and blocks
it. Neither announces itself.

## The agent came back

**With questions** (`stage: awaiting-answers`) — relay them to the human
verbatim, as a numbered list. Do not answer on their behalf, and do not pad the
list with your own. When they reply, write the answers into `## Questions` and
resume the *same* agent with `SendMessage` so its context survives.

**With a plan** (`stage: awaiting-plan-approval`) — print the plan in chat: the
`## Plan` section in full, `## Touches`, what is out of scope, and the design
canvas link if there is one. Then say plainly that you are waiting for
`approve`, `replan: …`, or `stop`.

Print it. Do not summarize it and do not link to the file instead — the human
approving a plan they have not read is the failure this gate exists to prevent.

## Approve plan → build

Resume the same agent with `SendMessage`: `Mode: BUILD. The plan is approved.`
plus any caveats the human attached. Set `stage: building`.

**If the agent is gone** (session restarted, `agent: none`), spawn a fresh
`feature-dev` pointed at the plan file and the existing branch. The plan file is
the brief; nothing is lost but conversation.

One thing first: git will not let two worktrees hold the same branch, so a stale
worktree from the dead agent blocks the new one silently-looking-like-a-git-error.
Confirm the branch is pushed, then clear it:

```bash
git worktree list                                  # is the old one still there?
git push origin feature/<feature>                  # only if it is behind
git worktree remove .claude/worktrees/<feature>
```

Never remove a worktree holding commits that are not pushed. If `git worktree
remove` refuses, it is telling you exactly that — push from inside it, or bring
it to the human.

## Build finished → the deploy gate

The agent stops at `stage: awaiting-deploy-approval` with the branch pushed.
Report to the human:

- what was built, in three or four lines;
- **the check results verbatim**, including anything that failed or was skipped;
- the branch name and the plan file path;
- anything worth looking at before approving.

Then stop and wait. Do not merge, do not release, do not deploy. This gate is
the one thing the pipeline adds to CLAUDE.md's standing authorization, and it is
the human's call alone.

If checks failed, say so and recommend a fix round rather than presenting it as
ready. Their `deploy` is given on the strength of your report.

## Approve deploy → ship

Their approval covers the whole sequence: merge, staging (if adopted), release,
production. One gate, as agreed. Run it end to end — a release that is not
deployed fixes nothing.

**1. Pre-release collision check, run immediately before you cut** — not once at
the top of the session. Another session can commit in between; treat the answer
as a snapshot.

```bash
git fetch origin
git worktree list
git branch -a --no-merged develop
git log --oneline -5 develop origin/develop
git diff --name-only origin/main...develop        # what this release changes
```

For each unmerged branch, `git rev-list --count develop..<branch>` tells you
whether it holds real commits — `git worktree list` over-reports, since most
worktrees are finished work. Then, for the branches that do:

- **Has a plan file *on that branch*?** Read it with
  `git show <branch>:docs/plans/<feature>.md` — not from your working tree,
  which only has the brief. Compare its `## Touches` against the release's
  changed files. It is a conflict only if they overlap, or if both touch
  `backend/migrations/versions/`. A parked feature that does not overlap is not
  a conflict — it is the normal steady state of this pipeline, and blocking on
  it would block every release forever.
- **No plan file on the branch?** It is not this pipeline's work, nobody can say
  what it touches, and the old rule applies: **stop and ask the human.**

Also stop and ask if another worktree holds uncommitted changes, or if
`origin/develop` or `origin/main` moved since you started — another session may
be mid-release.

**2. Merge**, in the primary checkout, never a worktree:

```bash
git switch develop
git merge --no-ff feature/<feature>
git push origin develop
```

If staging is adopted (`app-deploy staging` installed on the Pi), this lands on staging within ~60s. Mention
it; do not wait on it.

**3. Release.** Pick the version from `git describe --tags --abbrev=0`: a
feature bumps the minor, a fix the patch. Then:

```bash
./scripts/release.sh vX.Y.Z --yes
```

`--yes` is required — the retype prompt reads stdin, which is closed here.
`release.sh` refuses in a worktree, on a dirty tree, on an existing tag, and
when `main` holds commits `develop` lacks; if it refuses, read what it said and
bring it to the human rather than working around it.

**4. Deploy**, by whichever path this project adopted — `app-deploy prod`, the
self-hosted runner, or the manual `docker --context pi-deploy compose` in
§ Deployment. Production **refuses an unsigned tag** and stays where it is
*silently*, so confirm the new version is actually serving.

**5. Verify an `/api/*` route, not a page.** Pages return 200 even when the
container cannot reach the backend. Check `/api/health`, and check
`placeholder_secret` while you are there. Without the api block, verify what the
project has instead (`blocks.json`): the page for `web`, the worker's healthy
heartbeat for `worker`, the Pages deployment for the `pages` target.

**6. Close out.** The merge brought the plan file onto `develop`, so set
`stage: shipped` there and commit it directly — this is the one place the
pipeline commits to `develop` outside a merge, because by now the branch and
worktree are gone and there is nowhere else to put it. Then remove the worktree,
delete the branch, and tell the human the version, what shipped, and the health
result.

## Park a feature

On either `stop`: make sure the branch is pushed (`git push origin
feature/<feature>` — it is the backup), set `stage: parked` and
`worktree: removed`, commit the plan file, then remove the worktree. Nothing is
merged. Tell the human the branch name, so resuming later is one message.

## `/feature status`

Rebuild the picture from disk and git, never from memory — your context may have
been summarized:

```bash
git for-each-ref --format='%(refname:short)' refs/heads/feature/   # in flight
head -12 docs/plans/*.md                                           # briefs + shipped
git worktree list
git log --oneline -3 develop
```

Then, for each feature branch, read the **branch's** copy — the working-tree
file is the stale brief:

```bash
git show <branch>:docs/plans/<feature>.md | head -12
```

Print one line per feature: name, stage, branch, and whether an agent is still
attached. Two things to flag, because nothing else will notice them:

- `stage: building` with `agent: none` — needs a fresh agent at that plan file.
- a plan file on `develop` still at `stage: brief` with no matching branch — an
  idea that was written down and never handed to an agent.

## Several features at once

The architecture is identical; state lives in files, so nothing gets confused.
The real limits are worth saying out loud:

- **Approvals serialize at the human.** One chat channel, one person reading.
- **Releases serialize anyway.** One production target. Ship one feature fully
  before cutting the next.
- **Your context accumulates** — every agent's final report lands here. Past
  two or three concurrent features, that is the binding constraint. Use
  `/ideate` to keep briefs out of this session, and lean on `/feature status`
  rather than remembering.

Never run two ship sequences concurrently, and re-run the collision check for
the second one — the first just moved `develop` under it.
