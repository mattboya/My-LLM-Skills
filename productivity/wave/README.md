# /wave

A skill for Claude Code (`/wave`) and Codex (`$wave`) that builds everything in a project's `WORK_QUEUE.md` `## Ready` section as one parallel batch (a "wave"), from plan to handoff, with test-driven development and adversarial review on every unit. Pairs with [`/queue`](../queue), which fills the queue.

Manual-only (`disable-model-invocation: true`): it runs when you type `/wave`. Typing it is your opt-in to multi-agent orchestration for the whole run.

In Codex, `$wave` uses native subagents launched from the parent chat, so the app can show their threads and activity. The Codex-only bridge uses the existing lane runner for scheduling and reports; the parent chat stays active to dispatch jobs. [Native dispatch and recovery](references/codex-native.md). Claude Code continues to use the Workflow tool. An explicitly requested Codex CLI run can still use `codex-host.mjs`, with file logs rather than parent-chat native activity.

## What a run does

1. **Pick up or plan.** Resumes an interrupted run (wave doc at `RUNNING`) or a saved plan (`PLANNED`); applies any pending stakeholder answers first. A missing `## Wave protocol` section is drafted from repo evidence: manual mode confirms it once; auto records conservative local defaults and continues.
2. **Plan.** Staleness check per item (already shipped? already ticketed?), a snapshot of the queue, a collision graph of which items touch the same files, then lanes: units in a lane run in order, lanes run in parallel, and files three or more lanes touch get locks. Writes a dated wave doc beside the queue with scope, lanes, calls made, and an estimate: hours, and weekly usage priced from the unit count.
3. **Go/no-go: the only stop.** One message with scope, critical path, risks, estimate and up to three questions only you can answer, then Go / Go with changes / Stop.
4. **Run.** Wave 0 checks the prepared checkout and baseline gates, files tickets per the protocol, and arms a stall watchdog. Manual mode stops for a dirty tree or red baseline; auto preserves source work and diagnoses failures before continuing verifiable units. Then `lane-runner.js` schedules parallel lanes through the client's adapter: each unit is written test-first (red output saved before any production code), reviewed adversarially with revert-proofs, and fixed up to two rounds. Cross-lane "journey" reviews follow shared user paths, with a skeptic re-checking each high and medium finding (lows go to the queue unchecked), and final gates run on the quiet tree. A test that fails, then passes when re-run alone, with the problem in the test, goes to the queue's Ready list instead of holding the run open.
5. **Handoff.** Tickets move to review, shipped entries are harvested and deleted from the queue, leftover findings become `## Later` entries and flaky tests become `## Ready` entries, the open-questions page is updated in place with the wave's decisions, and the wave doc gets its Results. The run's hours and cost are added to `estimate.py`'s calibration rows, and a miss over 30% is reported as a refit to do.

It never pushes and never moves a ticket to Done.

## Commands

```
/wave                      every ## Ready item: plan, one go/no-go, then build
/wave ITEM-ID [ITEM-ID…]   only those items (IDs as the ### heading writes them, e.g. INC-12 S5)
/wave auto                 same as /wave, unattended: takes every recommended answer and its own Go
/wave auto ITEM-ID […]     auto mode for only those items
/wave lean [ITEM-ID…]      build only: test-first builders, one final check, no reviews (~a third of the usage)
/wave auto lean [ITEM-ID…] lean and unattended
/wave plan [ITEM-ID…]      plan only: shows the estimate and questions, saves the plan; then /wave auto runs it without stopping
/wave help                 this list

Automatic, no argument needed:
- a wave doc at RUNNING resumes the interrupted run instead of planning fresh
- a wave doc at PLANNED is picked up instead of re-planning
- Ready empty → an unlock message: what each Waiting item waits on, with questions you can answer
- pages under ## Awaiting answers are applied before planning

Model and effort come from the app setting when you type /wave; /queue promote recommends one.
The plan can run single units higher or lower, and units below the risky rows skip their own review.
Never pushes, never moves a ticket to Done.
```

**Auto mode** prepares and recovers the run without another user turn, answers its own go/no-go and logs the decisions. Uncommitted work is captured into an isolated local checkout; the source files, staging and branch history are preserved. Missing protocol details use conservative local defaults. Baseline failures are diagnosed/repaired, and independent verifiable work continues. Empty Ready or unresolved blockers that prevent all scoped work are reported honestly. Existing holds, stakeholder disagreements and external posts remain in "Held for you". See [auto startup and recovery](references/auto-start.md).

## Files

| File | What it is |
|---|---|
| `SKILL.md` | The skill itself: plan, go/no-go, run, handoff and auto-mode rules. |
| `lane-runner.js` | Generic Workflow script that runs the lanes, journeys, open-item close-outs and final gates. Everything project-specific arrives in `args`; don't edit it per wave. |
| `lane-runner.check.mjs` | Stub-agent check of the runner's control flow. Run `node lane-runner.check.mjs` after any runner edit. |
| `protocol-template.md` | Template for the queue's `## Wave protocol` section (branch, author, helpers, hot-file locks, test method, gates). |
| `helpers/wave-commit.sh` | Commits only the named paths in a shared checkout (`git commit --only`), so one lane's work never rides along in another's commit. |
| `helpers/lock.sh` | Hot-file locks for files several lanes edit. Takes all paths in one sorted call so lanes can't deadlock. |
| `helpers/wave-cost.py` | Run-cost table from Claude session transcripts (Claude only). |
| `helpers/codex-usage.py` | The share of the Codex weekly limit a run took, from Codex's session logs (Codex only). |
| `codex-host.mjs` | Runs `lane-runner.js`, or any script written for the Workflow tool, under Codex: one `codex exec` per agent, with a journal for `--resume` and a stall watchdog. |
| `codex-host.check.mjs` | Stub-codex check of the host. Run `node codex-host.check.mjs` after any host edit. |
| `native-host.mjs` | Codex-only job bridge: runs the shared scheduler while the parent chat dispatches native subagents; validates and checkpoints their reports. |
| `native-host.check.mjs` | Bridge checks for ordering, reports, failures and interrupted-run recovery. Run `node native-host.check.mjs`. |
| `references/codex-native.md` | Parent-chat native dispatch, permissions, concurrency and recovery procedure. |
| `prepare-auto.mjs` | Capture existing work with a temporary index and create/reuse an isolated auto checkout; preserve the original source branch/index. |
| `prepare-auto.check.mjs` | Real-Git checks for dirty startup, source preservation, ignored queue inputs and recovery. |
| `references/auto-start.md` | Unattended preparation, preflight recovery and handoff for both clients. |
| `agents/openai.yaml` | Codex metadata: runs only when you type `$wave`. |

## Requirements

- Claude Code with the Workflow tool and the `workflow-authoring` skill, or Codex with native subagent tools. Native agents inherit the parent chat's permissions. The legacy CLI host requires the `codex` CLI and uses its own sandbox settings; it is selected only on explicit request.
- `node`, `git`, `bash`, `perl` (lock polling).
- [`/queue`](../queue) linked at `~/.agents/skills/queue`: `/wave` reads its `SKILL.md` and `estimate.py` from there.
- The `simplified-technical-english` skill at `~/.agents/skills/simplified-technical-english/`: every text a person reads is written in it and checked with its `ste_check.py`.
- Claude Code only, optional: the agent files `wave-builder.md`, `wave-checker.md` and `wave-planner.md` in `~/.claude/agents/`. They give each agent only the tools its role needs (28–39k starting tokens instead of about 78k). They aren't in this repo; without them, `/wave` uses general agents.

## Checks

Run `node <name>.check.mjs` for each check script after editing the script it covers, and `python3 helpers/codex-usage.py --selftest` after editing that helper.
