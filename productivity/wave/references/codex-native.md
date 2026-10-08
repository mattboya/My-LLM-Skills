# Wave in Codex: native subagents

Read this reference only in Codex. The parent chat owns native agent dispatch; `native-host.mjs` runs the existing `lane-runner.js` scheduling and prompt logic. Its `agent()` creates a job file and waits for a report. It never launches a model or a CLI agent. Claude keeps its Workflow tool.

## Start

1. Confirm this chat exposes native spawn, wait, inspect/list and interrupt tools. Names vary by client; use the available tool definitions (for example, `collaboration.spawn_agent`, `wait_agent`, `list_agents`, `interrupt_agent`). If absent, report that native orchestration is unavailable here. Leave an unstarted plan PLANNED and preserve an interrupted RUNNING wave; do not silently substitute detached CLI agents. Use the legacy `codex-host.mjs` only when the user explicitly requests CLI execution.
2. In auto mode, first follow [auto-start.md](auto-start.md): use its effective run repo/branch/base and recorded checkout on resume. Prepare the same workflow script and args as the shared skill requires. For lanes, the script is `lane-runner.js`, args are `{SP}/wave/lanes.args.json`; omit Claude's `agentTypes` and `codexSandbox`. For planning, write a Workflow-API script and args as before. Planning stays read-only; lanes start only after Go and Wave 0.
3. Start the scheduler with the shell tool's background/session facility and keep its process/session ID:

   ```bash
   node ~/.agents/skills/wave/native-host.mjs serve ~/.agents/skills/wave/lane-runner.js "<scratchpad>/wave/lanes.args.json"
   ```

   The run folder is `<args minus .json>.native.run`. Use its absolute path in chat links. Keep the parent turn active until handoff; the scheduler cannot dispatch agents without it.

## Dispatch loop (planning, lanes, reviews and gates)

1. Read `node ~/.agents/skills/wave/native-host.mjs status "<args.json>"`. It lists `ready`, `running`, `completed` and `failed` jobs, each with a label and absolute `jobPath`. Read each ready job's full JSON for its `prompt`, `schema`, `phase` and `effort`.
2. Use available native slots, accounting for other active agents. A queued job is not a running agent. There is no fixed 16-agent requirement: use this client's limit. All Wave jobs are direct children of the parent chat so their activities belong to this chat. Workers perform their assigned job without starting another wave or spawning hidden CLI agents. Use a short descriptive task name based on the label, such as `impl_u1`, `review_u1`, `journey_j1`; include the exact Wave label in the prompt.
3. Spawn with the job's complete prompt and these additions: work in `args.repo`; inherit this chat's permissions; return a final JSON value matching the supplied schema (include the full schema); interpret "return through StructuredOutput" as that final JSON. Prefer a minimal context fork (`none` where supported): the job prompt and referenced wave doc carry its context. Leave model and effort overrides unset unless the job sets its own `effort`. Use that effort if supported; if not, record the actual supported setting and the deviation in the wave doc. Do not assume Claude's `max` always maps to one Codex setting.
4. Immediately record the returned native ID (or canonical task handle when the tool exposes that instead) and task name:

   ```bash
   node ~/.agents/skills/wave/native-host.mjs bind "<args.json>" "<job-id>" "<native-agent-id>" "<task-name>"
   ```

   Only the parent writes bridge state. The native agent receives no instructions to complete its own job file. Keep completed agent threads inspectable while the run remains active; release/reuse native slots through the client's supported lifecycle. Each independent reviewer is a fresh agent, not the builder under a new label. Reuse a completed thread only for the same role and unit when it cannot compromise review independence.
5. Wait for native results while continuing to dispatch ready jobs into available slots. Use bounded waits, and give concise progress updates at least once a minute. Native activity is the UI view; `host.log` and the job bindings are the durable trace. Name the run folder once in chat. A debug-only diagnostic mode is available with `WAVE_NATIVE_DEBUG=1`; routine phase and completion logs remain available.
6. For each completed native agent, parse its actual final report. Save a JSON envelope `{"agentId":"<bound-id>","result":<actual JSON report>}` to a scratch file, then submit it:

   ```bash
   node ~/.agents/skills/wave/native-host.mjs complete "<args.json>" "<job-id>" "<report.json>"
   ```

   The bridge validates the schema before releasing the runner's dependency waits. It supports the runner's schema subset: `type`, `properties`, `required`, `items`, `enum`. Build planning schemas from that subset. A schema-rejected report remains running: send the agent a correction request for its report, without asking it to repeat already completed work. Preserve the original report; never invent missing tests, commits or gate evidence. An `impl:` report marked partial/blocked, with no commits, or without any tests reporting red-first evidence is saved as failed and stops the host before downstream work. This validates reported evidence, not the test execution itself: reviewers and the parent still check the evidence files. Reconcile incomplete code and missing TDD evidence before resuming; do not repeatedly retry the same blocked task. If an agent fails or cannot produce a report, submit `fail "<args.json>" "<job-id>" "<reason>"`. This also stops the host; dependent jobs are not treated as successes.
7. Loop until the host's state is `finished` and its process exited successfully. Read `result.json` and apply the shared handoff. A finished scheduler is not proof of shipped work: check the unit statuses, open items, TDD evidence, gate reports and final verification. List partial/blocked units and remaining failures honestly. Take agent count, native thread IDs and duration from jobs, `journal.jsonl` and archived failed attempts in `attempts.jsonl`; deduplicate by native ID. Weekly usage comes from `helpers/codex-usage.py` (SKILL.md, In Codex, Run cost).

## Interruptions and recovery

- If the host fails or the user stops the run, inspect the bound native agents and stop those still working before any replacement. Stop the host through its shell session or recorded PID; SIGINT/SIGTERM record an interrupted state. Preserve each writer's diff and the wave's RUNNING doc.
- In auto mode, a recoverable host/agent failure keeps the parent turn active: reconcile the work, repair the cause and resume using the procedure below. Follow auto-start's bounded recovery and preserve missing-TDD guards; automatic continuation never means fabricating a successful report. A user-requested stop still stops the run.
- Before resuming, inspect `<run>/jobs` and the native agent list. Reconcile every `running` binding: an agent still running is reused, a completed agent's real report is submitted after restarting the host, a stopped/failed agent is marked failed after restarting. Marking a job failed stops the host; resume it again to make that failed job ready for replacement. A `ready` job may have been spawned just before a crash prevented binding: inspect native activities by its label/task name, then bind the existing agent once the restarted host is running rather than duplicating it.
- If the original host is still running, keep servicing it; a parent interruption alone is not a reason to launch another host. Otherwise restart the exact original script and args with `serve ... --resume`. The host refuses concurrent hosts and changed inputs. Leave the args file unchanged: the host reads journal seeds internally, overriding the generic Claude `args.seeds` procedure. Completed journal results are seeded; unjournaled completed job reports and running bindings survive. Failed jobs are archived with their reports, errors and native identities in `attempts.jsonl` before becoming ready on resume; replace them only after the original agents have stopped. Recheck Wave 0 against the current branch and saved base without discarding expected Wave commits. Do not require a clean tree until interrupted writers' changes have been reconciled.
- Native tools do not guarantee a live agent survives a new chat/session. If an ID is no longer reachable, record that, preserve its work and restart that unfinished task under a new native binding; retain completed evidence. Never start a new wave over a RUNNING wave.
