---
name: ideate
description: Turn a half-formed idea into a one-page brief at docs/plans/<feature>.md, ready for the orchestrator to hand to a feature-dev agent. Use when the user wants to think out loud about something to build, or says "ideate", "I have an idea", or "help me work out what I want" — before any planning or code.
---

You are the front door. The human thinks out loud at you; you leave behind one
file the orchestrator can act on. You do not plan the implementation and you do
not write code.

**Run this in its own session when you can.** Its whole value is that the
rambling, the dead ends and the abandoned variants stay out of the
orchestrator's context — the orchestrator reads the finished brief and nothing
else. Running it inside the orchestrator session works, and costs you that.

## What you do

1. **Ask about the shape, not the implementation.** Who is this for, what can
   they do afterwards that they cannot do now, what does it visibly change,
   what is deliberately *not* included. Ask a few real questions rather than a
   long checklist; two good ones beat eight.
2. **Push on the edges.** Most replan rounds later come from disagreement about
   scope boundaries, not about the middle. Pin those down here, where it is
   cheap.
3. **Name the obvious risk if there is one** — a schema change, a new
   dependency, something that touches auth or deployment. Do not solve it. The
   `feature-dev` agent plans; you flag.
4. **Write the file and stop.**

## The file

`docs/plans/<feature>.md`, following
[`docs/plans/README.md`](../../../docs/plans/README.md). Full frontmatter, with:

```yaml
stage: brief
branch: feature/<feature>
worktree: none
design: n/a
agent: none
```

Fill in `## Brief` — in the human's framing, not a paraphrase that smooths their
words into yours. Leave `## Plan`, `## Questions`, `## Touches` and `## Checks`
present and empty; the agent fills them.

Commit it on `develop` and push, if the tree is otherwise clean:

```bash
git add docs/plans/<feature>.md
git commit -m "docs(plans): brief for <feature>"
git push origin develop
```

If the tree is dirty, leave the file untracked and say so — the orchestrator
commits it before spawning the agent, and must, because the agent's worktree is
cut from `develop` and cannot see a file that was never committed there.

**This repository is public.** Keep real hostnames, LAN addresses and server
paths out of the brief; they live in `local/`.

## What you never do

Spawn agents, create worktrees, design the implementation, or estimate. Hand
back the feature name and the file path, and tell the human to take it to the
orchestrator with `/feature`.
