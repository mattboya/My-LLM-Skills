# Wave in Antigravity: run_workflow

Read this reference only in Antigravity. Every substantive phase runs with the `run_workflow` tool: read Antigravity's built-in `run-workflow` skill for its API before the first one. The lane runner does not change: `native-host.mjs` runs `lane-runner.js` and publishes each `agent()` call as a job, and `antigravity-host.py`, run by `run_workflow`, runs each job as a workflow agent and hands its report back through the host's checks (schema, and the red-first guard on `impl:` reports).

Use `run_workflow`, not `invoke_subagent`. An `invoke_subagent` call returns at once, and the subagent answers later in free text with no result schema. A workflow agent returns a schema-checked result through its `finish` tool. If this client has no `run_workflow` tool, follow [codex-native.md](codex-native.md) with `invoke_subagent` (`TypeName: "self"`) as the spawn tool: each subagent sends a message when it is done, and the parent submits the JSON it returns. Say in the go/no-go that this path has no result schema.

## Paths

- `{SP}` is this conversation's scratch folder, `~/.gemini/antigravity/brain/<conversation id>/scratch/`. Where the skill says "this session's id", use the conversation id.
- The skill's own files are reached through `~/.agents/skills/wave/` (the README's install links). `run_workflow` paths must be absolute: expand `~`.

## Prove unattended agents (Wave 0 step 2)

This replaces the slim-type proof. Run a one-agent workflow before the lanes: the agent runs `git -C <repo> status --short` and writes `{SP}/wave/agy-proof.txt`; its schema is `{"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}`. Lane agents run shell commands for hours and edit files in `{SP}` and in an auto run checkout, which are outside the workspace. The proof fails, or waits on an approval in the agent's card, when either of these settings blocks that:

- **Tool Execution Policy:** `always-proceed`, or an allowlist that covers `git`, `node`, `bash`, `perl` and the protocol's gate commands.
- **Non-Workspace File Access:** `allow`.

These are the user's security settings: never change them. Stop and name the setting. In auto mode this is a genuine blocker: record it and end, per SKILL.md's auto rules.

## Planning

Write each planning workflow as a `run_workflow` Python script with the same agents, prompts and schemas a Claude run would use. Set `role` to the agent's label. Leave out `agentType` (`type_name` stays `"self"`). `parallel` cancels every other agent when one fails, so wrap each checker in an `async def` that catches its exception and runs it once more, then returns `None`: this is SKILL.md's "re-run once". Planning agents stay read-only.

## Lanes

Write step 3's args to `{SP}/wave/lanes.args.json`, without `agentTypes` or `codexSandbox`. Then:

```
run_workflow(ScriptPath="<home>/.agents/skills/wave/antigravity-host.py",
             Description="Wave <date> lanes",
             Args={"script": "<home>/.agents/skills/wave/lane-runner.js", "args": "<SP>/wave/lanes.args.json"})
```

It runs in the background with up to 16 agents at once, and Antigravity tells this conversation when it ends. Its log carries the host's lines, `STALL` included: that replaces the Monitor watchdog (Wave 0 step 5). The run folder is `<args minus .json>.native.run/`, and the result is its `result.json`. A finished run is not proof of shipped work: check unit statuses, red-first evidence and gate reports as [codex-native.md](codex-native.md) step 7 says.

## Model and effort

Every workflow agent runs on the model this conversation is set to (`model` stays `"inherit"`). Antigravity has no per-agent effort, so the plan's unit `effort` and the gate keepers' `medium` run on that model too: record this in the wave doc as a deviation. Do not turn an effort into a lighter model tier.

## Interruptions and recovery

- The workflow ends with an error when a job fails: an agent that still did not call `finish` after one correction turn, a report the host rejects, or an `impl:` report with no commits or no red-first evidence. Before it ends, the bridge lets the agents that are still running finish and saves their reports in `<run>/agy-reports/`.
- A conversation stop or a server restart ends the workflow and every agent in it at once. Antigravity says so in a system message.
- **Before you resume**, save a `git diff` of the files each cut-off job owns. Reconcile incomplete builders and missing red-first evidence as codex-native.md says. Never write a report for an agent.
- **Resume:** run the same `run_workflow` call with `"resume": true` added to `Args`, and leave the args file unchanged. The bridge stops a host that a stopped workflow left running, submits the saved reports, and runs each cut-off job again with a note to check its partial work first. The host archives failed jobs in `attempts.jsonl` and makes them ready again. A second bridge refuses to start while the first one is alive.
- In auto mode, a recoverable failure keeps this turn going: reconcile, repair, and resume, as auto-start.md says. Never start a new wave over a RUNNING one.
