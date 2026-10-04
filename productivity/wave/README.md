# /wave

A skill for Claude Code (`/wave`) and Codex (`$wave`) that builds everything in a project's `WORK_QUEUE.md` `## Ready` section as one parallel batch (a "wave"), from plan to handoff, with test-driven development and adversarial review on every unit. Pairs with [`/queue`](../queue), which fills the queue.

Manual-only (`disable-model-invocation: true`): it runs when you type `/wave`. Typing it is your opt-in to multi-agent orchestration for the whole run.

## What a run does

1. **Pick up or plan.** Resumes an interrupted run (wave doc at `RUNNING`) or a saved plan (`PLANNED`); applies any pending stakeholder answers first. A missing `## Wave protocol` section in the queue is drafted from the repo (README, scripts, CI, linters) and confirmed with you once.
2. **Plan.** Staleness check per item (already shipped? already ticketed?), a snapshot of the queue, a collision graph of which items touch the same files, then lanes: units in a lane run in order, lanes run in parallel, and files three or more lanes touch get locks. Writes a dated wave doc beside the queue with scope, lanes, calls made, and an hour estimate.
3. **Go/no-go: the only stop.** One message with scope, critical path, risks, estimate and up to three questions only you can answer, then Go / Go with changes / Stop.
4. **Run.** Wave 0 checks the tree is clean and the baseline gates pass, files tickets per the protocol, and arms a stall watchdog. Then `lane-runner.js` runs every lane as a workflow: each unit is written test-first (red output saved before any production code), reviewed adversarially with revert-proofs, and fixed up to two rounds. Cross-lane "journey" reviews follow shared user paths, and final gates run on the quiet tree.
5. **Handoff.** Tickets move to review, shipped entries are harvested and deleted from the queue, leftover findings become `## Later` entries, a stakeholder batch page is published for the product decisions, and the wave doc gets its Results (which calibrate the next estimate).

It never pushes and never moves a ticket to Done.

## Commands

```
/wave                      every ## Ready item: plan, one go/no-go, then build
/wave ITEM-ID [ITEM-ID…]   only those items (IDs as the ### heading writes them, e.g. INC-12 S5)
/wave auto                 same as /wave, unattended: takes every recommended answer and its own Go
/wave auto ITEM-ID […]     auto mode for only those items
/wave lean [ITEM-ID…]      build only: test-first builders, one final check, no reviews (~a third of the usage)
/wave auto lean [ITEM-ID…] lean and unattended
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

**Auto mode** answers its own go/no-go with the recommended options and logs every self-answered question in the wave doc and on the batch page. It still never lifts a hold, settles a stakeholder disagreement, or posts outside its own tickets; those go in a "Held for you" list. It hard-stops on an empty Ready section, a missing protocol, uncommitted changes, or red baseline gates.

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
| `codex-host.mjs` | Runs `lane-runner.js`, or any script written for the Workflow tool, under Codex: one `codex exec` per agent, with a journal for `--resume` and a stall watchdog. |
| `codex-host.check.mjs` | Stub-codex check of the host. Run `node codex-host.check.mjs` after any host edit. |
| `agents/openai.yaml` | Codex metadata: runs only when you type `$wave`. |

## Requirements

- Claude Code with the Workflow tool and the `workflow-authoring` skill, or Codex with the `codex` CLI (on the PATH, or the copy inside ChatGPT.app). In Codex, agents run with full access by default (`codexSandbox` in the runner args), because Codex's sandbox makes `.git` read-only.
- `node`, `git`, `bash`, `perl` (lock polling).
- [`/queue`](../queue) linked at `~/.agents/skills/queue`: `/wave` reads its `SKILL.md` and `estimate.py` from there.
