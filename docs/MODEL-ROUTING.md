# Model routing for feature work

Gitflow decides where work happens. Model routing decides which capability
handles each stage. The aim is to spend on judgment where mistakes are
expensive, use a balanced model for the bulk of the code, and let reproducible
checks decide when to escalate.

This is a default route, not a reason to split every change into three agent
sessions. A small, well-specified change with obvious checks can stay on Terra
from plan through review. An explicit model choice from the user always wins.

## Default Codex route

| Stage | Default | Use it for | Exit condition |
|---|---|---|---|
| Plan | `gpt-6-astra`, high reasoning | architecture, acceptance criteria, risks, migrations, affected paths and checks | The plan in `docs/plans/<feature>.md` is specific enough that another model can implement it without inventing requirements. |
| Build | `gpt-5.6-terra`, medium reasoning | normal implementation, focused refactors and local test updates | The planned change is complete and the required checks have run. |
| Mechanical work | `gpt-5.6-luna`, medium reasoning | bounded renames, repetitive edits, fixtures and documentation updates under an accepted plan | The file set is fixed and deterministic checks cover the result. |
| Repair | Terra for a clear local failure; `gpt-5.6-sol`, high reasoning for a difficult code failure | reading failing tests, isolating regressions and correcting implementation | The failure is explained and the previously failing check passes without weakening it. |
| Risk review | `gpt-6-astra`, high reasoning | cross-cutting diffs, unclear root causes and the high-risk areas below | Findings are fixed or recorded, and all required checks pass. |

Use Astra immediately for authentication or authorization, privacy or secret
handling, destructive migrations, concurrency, deployment infrastructure,
irreversible operations, or a change whose architecture remains ambiguous.
Escalate to Astra after two unsuccessful repair attempts. Do not keep spending
cheap-model turns on a failure whose cause is still unknown.

`gpt-5.6-sol` is the coding escalation between routine Terra work and an Astra
architecture or risk review. Skip it when the problem is architectural or
high-risk; use Astra directly. Luna is only for closed, mechanical tasks. It
must not decide architecture, change scope, debug an unknown failure, or relax
a test to make a check pass.

## Run the stages serially

Only one writing agent owns a feature worktree at a time. Finish or stop that
agent before starting the next model. Two models editing the same branch at
once defeats the worktree isolation that protects other sessions.

Every handoff consists of durable repository state:

1. the feature plan, including accepted scope, risks and `## Touches`;
2. the current branch and worktree;
3. the committed or working diff;
4. exact check commands and their latest results; and
5. any unresolved failure, reduced to the smallest reproducible symptom.

Record routing decisions that matter in the plan's `## Plan` section and model
changes or repair evidence in `## Checks`. A fresh agent reads `AGENTS.md`, the
plan, the diff and the check output. A conversation transcript is optional and
must never be the only copy of a decision.

## Verification controls routing

Models do not certify their own work. Run the checks selected in the plan after
the build phase and after every repair. A stronger model is not a substitute
for pytest, type checking, unit tests, builds, migration checks or the e2e
suite.

Use the result to choose the next step:

- All checks pass and the change is local and low-risk: Terra may complete the
  review and hand back the feature.
- A check fails with a direct, local cause: let Terra make one focused repair.
- The failure survives that repair or spans several components: hand the diff
  and failure to Sol.
- The cause is unclear, two repairs failed, the implementation departs from the
  accepted plan, or the change is high-risk: hand it to Astra.
- A review finds new scope rather than a defect: return to planning before more
  implementation.

Do not paste an entire long build log into an expensive-model prompt. Preserve
the log, then provide the command, first relevant error, affected paths and the
smallest reproduction. The model can request more evidence when it needs it.

## Availability and configuration

Keep `.codex/config.toml` model-neutral. Model choice belongs to the user,
account or per-agent launch, and hard-coding one model would make the template
less portable. When the agent runner supports per-agent model and reasoning
overrides, start a separate serial agent for each routed phase. When it does
not, use the closest available capability tier and note the substitution in
the plan.

Other agent harnesses should map the roles above to their closest available
planning, balanced implementation, coding-escalation and high-risk-review
models. The concrete IDs are Codex defaults, not a claim that another harness
offers the same models.

Review the defaults when the available model catalog changes. OpenAI's
[model selection guide](https://developers.openai.com/api/docs/guides/model-selection)
recommends establishing accuracy with the strongest model before optimizing
cost and latency; the current IDs and capability descriptions live in the
[model catalog](https://developers.openai.com/api/docs/models).
