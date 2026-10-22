---
name: wave
description: Use when the user types /wave or $wave to work WORK_QUEUE.md as one parallel batch; Codex uses native subagents, Claude Code uses workflows.
argument-hint: |-
  [ITEM-IDs...]         plan, one go/no-go, then build Ready
  auto [ITEM-IDs...]    unattended: preserves existing work, prepares the run, takes recommended answers and Go
  lean [ITEM-IDs...]    build only: test-first builders and one final check, no reviews (combines with auto)
  plan [ITEM-IDs...]    plan only: shows the estimate and questions, saves the plan, builds nothing; /wave auto then runs it
  land                  push the finished wave as one branch and one PR; after you merge it, move its tickets
  help                  list every way to run /wave; starts nothing
disable-model-invocation: true
---

# /wave

One command runs a batch of queued work, from plan to handoff, at ultracode quality.

**Invoking /wave or $wave is the user's explicit opt-in to multi-agent orchestration for this whole run.** In Codex, first read **In Codex** below and use native subagents for every substantive phase. In Claude Code, load `workflow-authoring`, then run every substantive phase (the planning checks, the lanes, the reviews) with the Workflow tool. The quality bar is ultracode's: the most exhaustive, correct result, not the fastest or cheapest; token cost is not a constraint; verify adversarially before claiming anything. Every agent runs on the model the user set in the app before `/wave`, and on its effort, except where the plan sets a unit's own effort (step 1.4) and the lane gate keepers, which run at medium; `/queue promote` recommends the setting. In Claude Code, agents start as the slim types in `~/.claude/agents/` (`wave-builder`, `wave-checker`, `wave-planner`): only the tools their role uses, so each starts at 28–39k tokens instead of about 78k (measured 2026-10-03).

**Test-driven development is mandatory for every slice.** Red, then green, then refactor: the test is written first and seen failing for the right reason, with that output saved, before any production code. Reviewers fail a unit that has no red-first evidence, and revert every fix to prove its test goes red. `lane-runner.js` encodes this; never write a runner or an agent prompt without it.

**Every edit of `WORK_QUEUE.md`** (trims, the protocol section, the page link, the handoff) runs the protocol's backup step first if it names one, then the safe write: copy it to the scratchpad, build the new version there, `cmp` the live file against your copy, then `cp`. The file is gitignored and has no undo.

**Queue IDs never reach the tracker.** Queue IDs (the `###` heading IDs, e.g. `INC-12 S5`) and unit IDs (`U1a`) exist only in this skill and on this machine. Never write one into a tracker: no ticket title, description, comment, field, label or link text, no review plan, no heads-up on someone else's ticket. Name the ticket key and say the rest in plain words, and put this rule in every prompt for an agent that writes to the tracker. Trackers show linked commits, so when the protocol's `Tickets:` line names a tracker, no commit message names a queue ID either. Only with no tracker (`Tickets: none…`) is the queue ID the commit's key, and then `QUEUE_IDS.txt` decodes it (Wave 0 step 4).

**People read Simplified Technical English.** Read `~/.agents/skills/simplified-technical-english/SKILL.md` (not its references) before the go/no-go. Write every text a person reads in it: the go/no-go message, the wave doc, tickets, review plans and heads-ups, the open-questions page and the wrap-up. Code, identifiers, paths, ticket keys and quoted text stay as they are. Before you send the go/no-go and the wrap-up, pipe each draft through `python3 ~/.agents/skills/simplified-technical-english/scripts/ste_check.py --mode mixed --no-vocab` and correct what it finds. Lane agents get the short form in `lane-runner.js` (`STE`); paste that paragraph into every ticket clerk's prompt too.

## In Codex

Claude Code and Codex share this skill (`~/.agents/skills/wave`). In Codex, these replace the Claude-only parts; everything else, the quality bar and TDD included, applies as written.
- The user types `$wave …`, and `$ARGUMENTS` is the text after it. Read `/wave` and `/queue` as `$wave` and `$queue`. The queue skill's own **In Codex** section covers pages and answers.
- **Native dispatch is the default:** read and follow [references/codex-native.md](references/codex-native.md) before planning. Skip `workflow-authoring`. The parent chat spawns the planners, builders, reviewers and gate keepers with its native subagent tools, so their threads belong to this chat and appear in the client’s subagent activity UI. Tool availability and UI support come from the current client; do not promise a specific panel or silently substitute detached CLI agents when native tools are absent.
- **Workflow tool** → `native-host.mjs` beside this file. It runs the same Workflow-API scripts (`args`, `agent`, `parallel`, `pipeline`, `log`, `phase`) and the unchanged `lane-runner.js`; `agent()` publishes a job that the parent chat dispatches natively. Write each planning workflow and its args as usual. For lanes, write step 3's args to `{SP}/wave/lanes.args.json`. Start the host and service its jobs through handoff as the reference specifies. Results land in `<args minus .json>.native.run/result.json`.
- **Args and permissions:** leave out `agentTypes` and skip Wave 0's Claude slim-type proof. Native subagents inherit the parent chat’s model, effort and permissions, except explicit supported effort overrides from the plan. Record unsupported overrides instead of guessing a mapping. `coAuthor` = the protocol's co-author line. If it names none, ask at the go/no-go (recommend `Co-Authored-By: Codex <noreply@openai.com>`) and add the answer to the protocol's Setup. The bridge does not set `codexSandbox` or elevate permissions.
- **Stall watchdog** (Wave 0 step 5): the host writes `STALL` to `host.log` after 30 minutes with no agent finishing. Look for it when you poll.
- **Resume:** reconcile recorded native agent IDs and interrupted writers first, then restart the original host command with `--resume`. Follow the reference's recovery procedure; reuse completed reports and reachable running agents. Never duplicate an unfinished writer or plan fresh over a RUNNING wave.
- **Native overrides:** the host reads journal seeds itself; keep its original args file unchanged on resume rather than adding `args.seeds` as the generic Claude procedure describes. Singleton lanes are valid when dependencies or lean mode require them. An incomplete builder or missing red-first test report stops native dispatch before dependent work starts; reconcile its code and evidence before resuming.
- **Legacy CLI:** `codex-host.mjs` remains available only for an explicitly requested CLI run. It launches separate `codex exec` processes and does not provide parent-chat native subagent visibility; name that limitation before running it.
- **AskUserQuestion** → use this client's question UI for clarification and its supported approval flow for Go; recommended choices first. If unavailable, send one numbered message with recommended options and **Go** / **Go with changes** / **Stop** last, then wait for the reply. Auto mode retains its standing Go.
- **Setting check** (go/no-go): name the Codex `model_reasoning_effort` that the queue skill's **In Codex** section maps to, on the model Codex is set to. The estimates, the review failure rates and the risk line in step 1.4 come from Claude waves: say so until a Codex wave's Results exist.
- **Tickets:** if Codex has no tools for the protocol's tracker, say so at the go/no-go, file nothing, and use ticket `none` (Wave 0 step 4).
- **Run cost** (step 4.4): `wave-cost.py` reads Claude transcripts only. Skip it, and run `python3 ~/.agents/skills/wave/helpers/codex-usage.py --since <go time> --until <handoff time>` instead: it reads the weekly percent Codex logs on every turn. Paste its line, with the item and unit counts, into Results, and add the run to `CODEX_RUN_PCT` in the queue's `estimate.py` (its docstring says how). Take the native agent count, IDs and hours from the run's jobs, journal and archived attempts. Codex has no memory step: put the unpushed state and deploy prerequisites in the wrap-up.

## In Antigravity

Not supported yet. Antigravity has no Workflow tool, and `native-host.mjs` has not been tried with its `invoke_subagent`. `/wave help` works as written. For any other `/wave`, say this, plan and build nothing, and tell the user to run it in Claude Code or Codex.

## Input

- `help` as the only word → print the block below as-is (markdown, not a code block, so long lines wrap inside their column), then stop. No queue read, no workflow, no edits.

  | Command | What it does |
  |---|---|
  | `/wave` | Every ## Ready item: plan, one go/no-go, then build. |
  | `/wave ITEM-ID [ITEM-ID…]` | Only those items (IDs as the ### heading writes them, e.g. INC-12 S5). |
  | `/wave auto` | Same as /wave, unattended: takes every recommended answer and its own Go. |
  | `/wave auto ITEM-ID […]` | Auto mode for only those items. |
  | `/wave lean [ITEM-ID…]` | Build only: test-first builders, one final check, no reviews (~a third of the usage). |
  | `/wave auto lean [ITEM-ID…]` | Lean and unattended. |
  | `/wave plan [ITEM-ID…]` | Plan only, then stop: the estimate (hours, and weekly usage from the unit count) and the questions with their recommended answers. Builds nothing. Then `/wave auto` runs that plan to handoff without stopping, or `/wave` asks the questions first. Combines with lean. |
  | `/wave land` | Push the finished wave as one branch and open one PR, with the wave's summary as its description. You merge it; type `/wave land` again after the merge to move the tickets. |
  | `/wave help` | This list. |

  **Automatic, no argument needed:**
  - a wave doc at RUNNING resumes the interrupted run instead of planning fresh
  - a wave doc at PLANNED is picked up instead of re-planning
  - Ready empty → an unlock message: what each Waiting item waits on, with questions you can answer
  - pages under ## Awaiting answers are applied before planning

  Model and effort come from the app setting when you type /wave; /queue promote recommends one. The plan can run single units higher or lower, and units below the risky rows skip their own review. Only /wave land pushes, and it never merges.

- `land` as the only word → **Land** (below). No planning, no workflow.
- `auto` as the first word → **auto mode** (below) for this whole run; the rest of `$ARGUMENTS` works as usual.
- **Auto startup:** before planning, read and follow [references/auto-start.md](references/auto-start.md). Its preparation/recovery rules override the manual clean-tree, missing-protocol and baseline-stop rules below. Uncommitted source work never requires a user cleanup step in auto mode.
- `lean` as the first word, or right after `auto` or `plan` → **lean mode** (below) for this whole run; the rest works as usual.
- `plan` as the first word → **plan mode** (below): plan, show the go/no-go, save the plan and stop.
- `$ARGUMENTS` = queue item IDs (as written in the `###` heading, e.g. `INC-12 S5`) → only those items. Empty → every `## Ready` item: Ready is exactly what a wave builds. `## Waiting` items are never built; each waits on something outside the code, named in its `Waiting on:` line. A `🔴 Decision open` block is not a wait: it is built with its recommended answer.
- **Ready is empty** → don't plan an empty wave. The go/no-go becomes an unlock message: each Waiting item and what it waits on, and for waits the user can clear (their own go, a call they can make), one question each with a recommendation. A yes moves that entry to Ready (safe write) and into scope. Plan only what the answers would unlock, and say so.

## 0. Pick up or plan

- `WORK_QUEUE.md` at the git root. None → tell the user to `/queue` some work first, and stop.
- **Protocol:** the queue's `## Wave protocol` section (between the header's `---` and `## Ready`). Missing → propose it, then confirm:
  1. Reuse first: a `WORK_QUEUE.md` in another worktree of this repo (`git worktree list`) with a `## Wave protocol` is the starting draft; change only its checkout-specific lines (repo path, branch, "never touch" paths).
  2. Otherwise draft every `{{…}}` in `protocol-template.md` from the repo: README, CONTRIBUTING, CLAUDE.md/AGENTS.md, package.json scripts, Makefile/justfile/mise tasks, `scripts/`, CI config, formatter and linter configs, the current branch and `git config user.name`. Mark anything you guessed rather than read.
  3. Show the draft and ask once with AskUserQuestion: branch, author, ticket rules, and whether the test/format/lint commands and docs are right, each with your proposal as the recommended option. Write the section with the answers.
  In auto mode derive and record the conservative local draft under [auto startup](references/auto-start.md), then continue with the standing Go.
- **Saved plan:** a wave doc beside the queue whose first lines say `**Status:** PLANNED` is an unstarted plan (older docs without a Status line are history, not plans). Pick up the newest one: diff the live queue against its snapshot (step 1.2) and bring the differences to the go/no-go. Otherwise plan fresh. This skill sets the Status line: `PLANNED` when written, `RUNNING` at go, `DONE` at handoff. A doc still at `RUNNING` is an interrupted run: never plan fresh over it. Resume it: re-run Wave 0 steps 0-3, then relaunch the runner with `args.seeds` from its last run's journal (step 3). Picking up a `PLANNED` doc re-runs the staleness check on any entry that changed since its snapshot. A plan that says `Mode: lean` runs lean.
- **Pending answers:** pages listed under `## Awaiting answers` → apply them first, as step 2 of `~/.agents/skills/queue/SKILL.md` says, with two differences: disagreements are not asked now but go into the go/no-go message, and follow-up entries the answers create are written to `## Later` and listed there as "added from answers"; they move to Ready and into scope only if the user keeps them.

## 1. Plan

1. **Staleness check** (read-only agents, one per area of about three items, in parallel, so no checker runs long: a 100-turn agent re-reads its whole context every turn). Area checkers run as `agentType: 'wave-planner'`, which has no tracker tools, so one default-type `plan:tracker` agent at `effort: 'low'` does every tracker lookup for all items (closed tickets included, assignee, comments) and the main session merges the two. A slim agent that returns null is re-run once without `agentType`. When a checker prototypes a fix (keep asking them to: it is what keeps first-review failures down, and in lean it is the only adversarial look), it saves it as a patch `git apply` accepts at the repo root (`git init -q && git add -A && git commit -qm base` in its snapshot before editing, then `git diff --binary`) at `{SP}/proto/<item>.patch`, and its red output under `{SP}/tdd/`. A prototype's tests become the unit's committed tests, so paste the `PLACEMENT` paragraph from `lane-runner.js` (and the protocol's `### Test tiers` block, if it has one) into every checker prompt that prototypes. For each item: search the tracker, closed tickets included; verify against the code that the symptom can't recur, not just that the named mechanism is gone; read any existing ticket's assignee and comments. Shipped → delete the entry. Partly done → trim it to what's left. Already ticketed → plan to work that ticket, unless someone else is assigned or a comment says the work is parked or in flight. A Ready item that can't start for any reason moves to `## Waiting` with a `Waiting on:` line and is named in the go/no-go. Also read each Waiting entry: one whose wait looks over (the teammate's work is on origin, the call is recorded) is offered at the go/no-go as "move back to Ready?". A ticket that is Done while work remains gets a new ticket linked to it at Wave 0 (never reopen it). No ticket is filed or changed before Go. The queue trims are facts, so a later Stop doesn't undo them.
2. **Snapshot the queue** after the trims, beside the wave doc as `YYYY-MM-DD-wave[-N].queue.md` (the wave-doc ignore pattern covers it). Wave 0 diffs against it; a new session can find it.
3. **Collision graph.** Intersect the Touches lists mechanically, then trace what that misses: shared test files, behavioural coupling, migrations, undeclared consumers, append-only registries. Check every anchor exists; named symbols are often wrong.
4. **Lanes.** Units in a lane run in order. Cross-lane dependencies are waits, not barriers. A file two lanes touch gets a wait (one lane finishes first) when that costs little, otherwise a lock; a file three or more lanes touch always goes on the hot-file list. Assign fixed migration filenames. Code every lane needs first (a shared constant, a helper) is unit `U0` in its own lane, and dependent units list it in `deps`: it gets TDD and review like any unit, and its `items` name the queue item it mainly serves, whose ticket it commits under. Define journeys: cross-lane reviews along shared user paths, each listing the units it covers. Keep each journey to one user path and about four units, so no journey agent runs past about 100 turns; a journey that runs a whole browser suite is split by shard (the protocol says how). Plan lanes of two or more units: a one-unit lane's lane gates cost what a full-gate review would.
   - **Review by risk:** set `lean: true` on a unit when every change in it sits below the extra row of the queue skill's Promote rubric (no pay math, security or privacy, data, background jobs, or what Linda says and her tools). It skips its own review; its lane gates, the journeys and the final gates still cover it. Reviews pay off where that rubric says: since 09-30, first reviews failed 38–41% of pay-math and Linda-chat units but 5–19% of page, list and accessibility units.
   - **Unit effort:** set `effort` when the rubric's row for that unit differs from the session's: `high` for an Opus · high unit in an extra session, `max` for a max-row unit. One max unit no longer makes the whole wave max.
   - **`proto`:** the checker's patch path, when there is one. The builder lands it test-first instead of re-deriving the fix (trial 2 builds took 2–4 minutes with one).
5. **Wave doc** `YYYY-MM-DD-wave[-N].md` beside the queue: Scope; Not in this wave (and who each waits on); Protocol additions and hot files; Wave 0; Lanes table (units, size, owned files, waits for); Calls made where the notes left a gap (top two options and why; binding on agents); Journeys; Handoff; Human steps. Write every call out: nothing may live only in the scratchpad. First line: `**Status:** PLANNED`.
6. **Estimate** in agent time (hours, agent count, most at once), scaled from the last wave doc's Results (agents and hours per unit); with no history, about 4 agents and 25 minutes per small unit, plus about 6 agents per journey. List human-gated waits separately. **Usage:** `python3 ~/.agents/skills/queue/estimate.py --units <units in the plan>` (add `--lean` for a lean run, `--codex` in Codex) gives the run's share of the weekly limit, planning included. It prices units, not items: units are what the cost follows, so this number is firmer than `/queue promote`'s.

## 2. Go/no-go: the only stop

One message, then one AskUserQuestion call: up to three questions only the user can answer, then **Go** (recommended) / **Go with changes** / **Stop** as the last. More than three questions → ask the scope-changing ones in a first call, then the rest with Go. Anything posted outside this run's own tickets (a heads-up on a teammate's ticket) is named in the message, and Go approves it. The message covers:
- scope (every Ready item), naming those that answers on an unblock page just moved into Ready; what the plan moved to Waiting and why; and Waiting items whose wait looks over;
- lanes and the critical path; which units skip their own review (risk-tiered) and which run at their own effort, each with the reason;
- risks, and the calls you made;
- questions only the user can answer, each standing alone in plain words;
- the estimate;
- uncommitted changes in the working tree, if any: in a manual run the user commits or sets them aside before Go; in auto, report the preserved snapshot and isolated run checkout, then continue;
- the setting check: the model this chat runs on, and the setting this Ready set needs (`estimate.py <queue> --profile`, corrected with the rubric in step 7 of the queue skill's Promote section). If the chat is on a lower setting, say which tasks need more and that the model and effort are changed in the app before Go. In auto mode, log it under `## Held for you` and carry on.

Record the answers in the wave doc under `## Answers`, and set its Status to `RUNNING` at Go. In the same edit, make its second line `**In flight:** <every queue ID in scope, comma-separated, exactly as the ### headings write them>`. While the Status is `RUNNING`, `/queue` holds any stakeholder answer about these entries until the handoff (queue skill, step 2), so a mid-run `/queue` never rewrites a spec agents are building.

## 3. Run

**Wave 0**, in this session:
0. Diff the live queue against the plan's `.queue.md` snapshot. Hold entries added since, and say which; fold in changed specs.
1. `git fetch`; confirm branch and author per the effective run protocol; note the base sha. A fresh manual run requires an empty `git status --porcelain`. A fresh auto run checks its prepared run checkout, not the preserved dirty source. Resume reconciles expected in-flight edits instead of treating them as a fresh dirty-tree failure. Auto recovers local preparation/fetch failures per [auto startup](references/auto-start.md).
2. Copy exactly the helper files the protocol's Setup names into `{SP}/wave/` (the skill's `helpers/` first, then the project's), and write `{SP}/wave/wave.env`. Prove any e2e helper once. Prove the slim agent types once too: a one-agent workflow with `agentType: 'wave-checker'` and a schema `{ok: boolean}` must return ok. If it returns null, leave `agentTypes` out of the runner args and note it in the wave doc (the run then costs about 15% more, nothing else changes).
3. Baseline gates at the base (the protocol's Gates block), or the last run's final gates when they ran at this exact sha (cite them). Record each whole suite's test count and minutes in the wave doc (time each run; a cited run's Results have them): the handoff compares them with the final gates. Manual red → stop and report. Auto saves/diagnoses the failures, repairs what it can and continues independent verifiable work per [auto startup](references/auto-start.md); it never hides the failed gates.
4. File tickets per the protocol, reusing existing ones, with no queue IDs in them.
   - **No tracker** (`Tickets: none…`): each item's ticket is its queue ID. Instead of filing, append one line to `QUEUE_IDS.txt` at the repo root for every in-scope ID it lacks, `<ID> — <what the item changes, plain words, one line>`, and commit that file alone with `wave-commit.sh` before the lanes start. A line is final: never edit or delete one, since commits cite it and IDs are never reused.
   - **Tracker named but unusable this run** (no tools for it, unreachable, or details unknown in auto): file nothing and set every item's ticket to `none`, so commits carry no key. Never fall back to queue IDs. Results list each commit's sha and item so the tickets can be filed and linked later.
5. Arm a stall watchdog (Monitor): alert when neither a commit nor an agent result has appeared for 30 minutes.

**Lanes:** run `lane-runner.js` (beside this file) with the Workflow tool's `scriptPath` and these `args`:
- `wave`, `repo`, `sp`, `base`, `waveDoc`, `tickets` ({item: key});
- `coAuthor`: the co-author line from this session's attribution reminder;
- `protocol`: `{shared, hot, method, snapshot, gates}` = the queue's protocol blocks with `{REPO}`, `{SP}`, `{BASE}` and `{HOT_FILES}` filled in, plus `reviewGates` = its `### Review gates` block when it has one and the heading isn't marked `(paused)` (unit reviews and the verifiers after a fix then run those targeted gates, and each lane gets one full-gates run after its last unit: one more agent per lane); plus `flaky` = its `### Flaky tests` block when it has one (how this project reproduces and fixes its flaky tests; gate keepers read it); plus `tiers` = its `### Test tiers` block when it has one (it wins over the runner's default `PLACEMENT`);
- `units`: `items` are the queue IDs exactly as the `###` headings write them (e.g. `INC-12 S5`); `brief` = that unit's binding calls, short, since agents read the wave doc; `files` = the paths it owns; `lean`, `effort` and `proto` as step 1.4 set them;
- `agentTypes`: `{builder: 'wave-builder', checker: 'wave-checker'}` when both files exist in `~/.claude/agents/` (`ls` them; agent types load when a session starts, so leave it out if they were added during this session);
- `lanes`, `journeys`. The runner refuses to start on an unknown unit ID or a unit in no lane.
- `{HOT_FILES}` with no hot files → `none in this wave.`

Don't edit the runner per wave. A real improvement goes into the runner itself, followed by `node lane-runner.check.mjs`.

**If the run stops or stalls:** never `resumeFromRunId`. Its cache is a call-order prefix, so it re-runs finished reviews. Save a `git diff` of any interrupted agent's files, then relaunch with `args.seeds` = `{label: result}` for every finished agent, taken from the run's `journal.jsonl`.

## 4. Handoff

1. Each ticket gets a numbered review plan and the move the protocol's lifecycle sets for the handoff (the move it sets for the merge waits for `/wave land`). In a full run, a unit that skipped its own review (`lean` in the runner's results) opens its plan with: "Built without its own review (low risk): the cross-lane reviews and the full test suite covered it." Each ticket's technical notes also get the unit's engineering decisions (`productFlavour: false`), one line each: `question → pick, why`. Ticket clerks run as default-type agents at `effort: 'low'`; queue edits as `wave-planner`.
2. **Queue:**
   - Back it up first.
   - Harvest before deleting: a constraint on later work moves onto the pending entry it affects; a leftover defect becomes a new `## Later` entry. The runner's `later` list (every low the journeys and verifiers found, each with how to reproduce it; fix loops don't chase lows) becomes `## Later` entries too, grouped by area, keyed to their ticket, reproduction kept.
     A `later` item with `unconfirmed: true` was graded low by a journey reviewer and not re-reproduced: its entry says `(unconfirmed: reproduce before fixing)`. The runner's `flaky` list (tests that failed, then passed when re-run alone, with the problem in the test, not the product) becomes `## Ready` entries, never Later: one per test file, typed as test tooling, with the runs, the test-or-product reasoning, the reproduction and the suggested fix, and the rule that the fix never loosens an assertion. Ready, because the next wave then fixes it on a quieter machine; left in Later, CI stays noisy until someone remembers it.
   - Before deleting, diff each in-flight entry against the wave's `.queue.md` snapshot. A change someone made mid-run (a note, a rewritten Want) is carried into a follow-up entry or onto a pending entry, never deleted with the shipped one.
   - Then delete the shipped entries with the safe write: scratch copy; split on `\n## Ready\n` / `\n## Waiting\n` / `\n## Later\n`; print the headings; `cmp` the live file; `cp`.
   - **Held answers:** apply every saved answer whose card's `data-entry` is on the wave doc's `**In flight:**` line, as step 2 of `~/.agents/skills/queue/SKILL.md` says (disagreements go to the wrap-up, not a question). The entry is gone now, so the deleted-entry rows apply: a pick that matches what was built needs nothing; a pick that differs becomes a follow-up entry citing the page and question. "What was built" is the card's `data-built`, or, when that is empty, the option this wave built (the entry's 🔴 assumed answer, or the wave doc's call on it). This bullet may run inside step 3's roll, which pulls answers anyway.
3. **Open-questions page:** roll it, as the queue skill's **Open-questions page** section says, with this wave's cards. The roll carries every question still open and adds:
   - **Needs you before it's built** (`data-built=""`): any decision this wave left undone. The roll already adds every `🔴` block still on an entry left in the queue after the step 2 deletions. When a wave decision is the same question as a queue block (a "left unchanged" call that became a Later entry), make one card, with `data-entry` on the queued entry.
   - The built decisions (`data-built` = the letter that shipped, "left as is" included): product, design and wording decisions (the runner's `productFlavour` decisions and `productCalls`, plus the shipped entries' `🔴` blocks). Split them by whether the build matches the card's recommendation:
     - **Built differently from my recommendation** (`data-built` ≠ `data-rec`): full cards, NOT pre-filled, each `Built as` saying why it went that way. The user overturned 10 of 10 of these (2026-10-01), so they're the ones worth a read.
     - **Built as recommended** (`data-built` = `data-rec`): this wave's own group, pre-filled with what was built, each card folded to one line (number, question, a few-word `Built as`), per the template. The user changed 7 of 85 of these.
   - **Ready to merge:** one card per side branch this wave leaves for a merge decision.

   Engineering calls are listed as decisions made. **Latest run** gets this wave's report and the judge-while-testing list.
4. Write the wave doc's `## Results` (commits, units, agents, the times `/wave` was typed, Go and the handoff, hours from go to handoff, first-review failure rate, journey findings confirmed, lows queued unchecked, flaky tests queued: the next estimate scales from these) and set its Status to `DONE`. **Tests:** each whole suite's test count and minutes, baseline → final gates, and the number of proofs kept out of CI (the runner's `testsAdded` with tier `proof`). The browser suite's change is what this wave adds to every CI run.
   **PR description:** write `<wave doc stem>.pr.md` beside the wave doc for `/wave land`, in Simplified Technical English (run it through `ste_check.py` like the wrap-up), with no queue or unit IDs and no scratchpad paths. Its parts, in order: `## What changes` (one line per ticket: `<KEY>: what changes for the user`); `## Design calls` (the wave doc's calls, and the engineering decisions a teammate could question, one line each: `question → pick, why`); `## Tests` (the Tests line above); `## Before you merge` (deploy and human steps; say that each ticket has its review plan). **Run cost:** run `python3 ~/.agents/skills/wave/helpers/wave-cost.py --session <the doc's **Plan session:** id and a comma, if it has one, then this session's id: the UUID in your scratchpad path> --prev <the newest *.cost.md beside the wave doc> --ledger <wave doc stem>.cost.md` from the repo root after the handoff agents finish. Paste its table into Results; put its first line and any **Got dearer** line at the top of the page's **Latest run** and in the wrap-up. A role that got dearer is a finding: say what changed. If the run used `reviewGates`, add the review minutes (first review, median and range), the lane-gates runs that went red and what caused them, and the final gates' failures. Give first-review failures by tier too (reviewed units only; the risk-tiered `lean` units had none), so the risk line in step 1.4 can be re-checked. Update memory with the unpushed state and deploy prerequisites. Fold what the wave taught into the queue's `## Wave protocol`.
   **Calibrate the estimator** (Claude runs; Codex has its own step under **In Codex**), so the next estimate learns from this one. In `~/.agents/skills/queue/estimate.py`, add one row to `CALIBRATION` (`LEAN_CALIBRATION` for a lean run): the wave, `ready_now.waves[0].longest_lane_h` from `estimate.py <this wave's .queue.md> --json --only <the in-scope IDs>`, the item count, and the hours from typing `/wave` to the handoff (a `/wave plan` run: its planning hours plus the run's; leave out any time between the two and any usage-limit pause). Add one row to `UNIT_CALIBRATION`: the wave, the item count, units, the ledger's dollars, and lean or not. Then run `estimate.py --selftest`. If it passes, commit `estimate.py` alone in its own repo (`git -C "$(dirname "$(readlink -f ~/.agents/skills/queue/estimate.py)")" commit -m "queue: calibrate from wave <date>" estimate.py`). Never push. If the selftest fails, the run missed by more than the model allows: take the row back out, and write `Estimator missed: <row>, <estimate> against <actual>; refit needed` in Results and in the wrap-up.
5. Wrap-up in the user's status conventions: `git fetch` before any ahead count, the page link, the browser suite's test count and minutes baseline → final, the flaky tests queued to Ready (CI may flake on them until the next wave), the human steps, and "type `/wave land` to push this wave as one PR". No push.

## Land (`/wave land`)

Typing `/wave land` is the user's OK to push one finished wave: the newest wave doc at `**Status:** DONE` with no `**Merged:**` line. It goes up as one branch and one pull request, so CI runs once on the whole wave instead of once for each fix.

- **No `**Landed:**` line yet: open the PR.**
  1. `git status --porcelain` is empty, HEAD is on the protocol's branch, and `git log` has every commit in the wave doc's Results. `gh auth status` shows the account the protocol's Setup names; if not, stop and say so (never switch accounts).
  2. `git fetch`. If the protocol's branch moved on origin since the wave's base, merge it into the local branch, resolve, run every gate again (the protocol's Gates block), and stop on red.
  3. `git push origin HEAD:refs/heads/wave/<wave doc stem>`. Never force, and never push to the protocol's branch.
  4. `gh pr create --base <protocol branch> --head wave/<stem> --title "<the wave's scope in plain words>" --body-file <stem>.pr.md`. Write `**Landed:** <PR url>` under the Status line.
  5. Tell the user to merge it on GitHub with **Create a merge commit** once CI is green (a squash or rebase merge gives the commits new shas, and the local branch then stops matching origin), then to type `/wave land` again. Never merge it, and never turn on auto-merge.
- **`**Landed:**` line, PR still open:** report `gh pr checks <url>` and stop. For a red check, say to reproduce it with the protocol's Gates in CI's environment before any new push. A PR closed without a merge: say so and stop; never reopen it.
- **PR merged** (`gh pr view <url> --json state,mergeCommit`): `git pull --ff-only` on the protocol's branch. Move each of the wave's tickets as the protocol's lifecycle sets for the merge, with ticket clerks as in step 4.1. Write `**Merged:** <merge sha>` under the Landed line, and update memory: the wave is no longer unpushed.

A wave stacked on an earlier unpushed wave pushes that wave's commits too: put each older `DONE` doc without a `**Landed:**` line into the same PR (its `.pr.md` parts under the newest's), and give it the same Landed and Merged lines. Side branches the wave left for a merge decision are not in this PR; the reply names them.

## Auto mode (`/wave auto`)

The same run, unattended: invoking `/wave auto` is the user's standing instruction to perform routine local preparation/recovery, preserve existing work, take every recommended answer and give the Go. Read [auto startup](references/auto-start.md) before planning. Nothing is asked with AskUserQuestion during the run. Everything below that differs from a normal run:

- **Go/no-go:** write the full message into the wave doc under `## Go/no-go (auto)` and print it, then answer each question with its recommended option and give **Go**. Log every self-answered question in the wave doc's `## Answers` as `Qn — <question> — auto: <letter> <label>; alternatives: <letters and labels>`, and the Go as one unnumbered line (it gets no card). A new dependency is always a question for the user, never an engineering call; in auto its answer is "no new dependency".
- **Never decided for the user, even in auto** (each is listed in the wrap-up instead):
  - lifting a hold or moving a Waiting item to Ready, including Waiting items whose wait looks over;
  - stakeholder answers that disagree on a page (they stay open);
  - anything posted outside this run's own tickets (a heads-up on a teammate's ticket): draft it into the wave doc under `## Held for you` and post nothing. The item is still built, on the local branch only; the wrap-up says to post the draft before any push.
- **Nothing to run or genuine blockers:** end with the recorded reason only when:
  - Ready is empty (report what's waiting and on what);
  - required capabilities/resources or permissions remain unavailable after bounded recovery and no scoped unit can make meaningful progress.
  Dirty source work is automatically preserved in an isolated checkout; a missing protocol gets a conservative local draft; baseline failures are diagnosed and do not cancel unrelated verifiable work. An internal host stop triggers the parent's recovery procedure, not an immediate final response asking the user to restart.
- **Open-questions page:** add a theme group **Answered for you**, first in this wave's **Built as recommended** group (folded like the rest), with one card per self-answered question. Set `data-built` and `data-rec` to the letter it took, and `data-entry` to the item the question was about (empty for a plan-level question). A different pick then becomes a follow-up through `/queue answers`, as for any other card.
- **Wrap-up:** add two blocks. **Answered for you** gives one line per question, the answer taken and the page card it's on. **Held for you** lists the drafts to post, the stakeholder disagreements, and the Waiting items that look ready to move.

## Plan mode (`/wave plan`)

The user's way to see the estimate before an unattended run. Steps 0 and 1 run as in a normal run; a missing protocol is still asked. Then:

- **Go/no-go:** write the full message (step 2) into the wave doc under `## Go/no-go (plan)` and print it. Each question shows its recommended answer. Ask nothing, give no Go, and stop. The Status stays `PLANNED`. Nothing is filed and nothing is built.
- **For the run that picks it up:** under the Status line, write `**Plan session:** <this session's id: the UUID in your scratchpad path>`, so the run cost counts the planning (step 4.4), and `**Plan files:** {SP}`, where the prototypes and red outputs are. If that folder is gone at pick-up, the units run without their `proto`.
- **End** with what to type next: `/wave auto` runs this plan to the handoff with the recommended answers and does not stop; `/wave` asks the questions first. Both pick up the plan, so planning is not done again.

## Lean mode (`/wave lean`)

The user's choice to trade the review layers for usage. In wave 2026-10-01 (2), the builders were about a quarter of the run's usage, and the per-unit reviews, fixes and re-checks were half; the cross-lane reviews were another 12%. Lean keeps TDD and drops the rest. Everything not listed here is a normal run, and auto mode combines with it.

- **Plan:** no journeys (step 4). The staleness check stays, prototypes included: they are lean's only adversarial look, and each patch becomes its unit's `proto`, so the builder lands it instead of re-deriving it (lean 10-03: planning was 43% of the run's cost, builders 31%). The estimate is `lean_hours` from `estimate.py`, and usage is `estimate.py --units <units> --lean`.
- **Go/no-go:** the message says it's a lean run: no per-unit reviews and no cross-lane reviews, so the bugs those catch (8 of 49 units failed first review on 10-01) land on the local branch. The setting check uses the lean line in the queue skill's Promote step 7, and names its *risky lean* tasks.
- **Run:** pass `lean: true` to the runner. It runs one test-first builder per unit, then one final-gates agent that fixes anything red except a test-side flaky test, which it lists for the queue's Ready. It skips journeys, `reviewGates` and close-outs, and reports open items instead of closing them.
- **Handoff:**
  - Each ticket's review plan opens with: "Built lean: no adversarial or cross-lane review. Test it as unreviewed code."
  - A unit that built nothing (an open item) doesn't count as shipped: its entry stays in the queue, and the wrap-up names it.
  - The wrap-up lists every unit whose report has no test, or a test with `sawRedFirst` false.
  - Open-questions page: this wave adds only its built decisions (the builders' `productFlavour` decisions and the shipped entries' `🔴` blocks) and the judge-while-testing list. The roll still carries every open question.
  - Results open with `Mode: lean` and leave out review and journey figures. Calibrate the estimator as step 4.4 says, with the lean rows.

## Never

- Push, or move a ticket to Done, outside `/wave land`. Merge a pull request or turn on auto-merge, even in `/wave land`.
- Write a queue or unit ID into the tracker, or into a commit message when the project has a tracker.
- Stop between go and handoff to ask a question. In auto mode, ask nothing at all. Decide, document the top two options, and send product calls to the open-questions page.
- Land a unit without red-first evidence.
- Rely on per-lane review alone (lean mode, the user's explicit choice, skips review entirely). The journey pass found 34 to 39 real defects per wave that per-lane review missed.
- Resume a lane run with `resumeFromRunId`.
