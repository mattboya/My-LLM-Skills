# My LLM Skills

Skills I've written for Claude Code and Codex, grouped by area. In Codex, type `$queue` / `$wave` instead of `/queue` / `/wave`.

| Skill | What it does |
|---|---|
| [`productivity/queue`](productivity/queue) | `/queue`: spec a fix or feature from the code into a project's `WORK_QUEUE.md`, plus summary, time-fit, quick-wins, promote, unblock and stakeholder-answer commands. |
| [`productivity/wave`](productivity/wave) | `/wave`: build everything in the queue's Ready section as one parallel, test-first, adversarially reviewed batch. |

Both skills are manual-only: they run when you type them, never on their own.

## How the two fit together

`/queue` fills a project's work queue, and `/wave` empties it.

```
 "this is broken" / "I want X"
            │
            ▼
   /queue <what>  ──spec from the code──▶  WORK_QUEUE.md (git root, gitignored)
                                             ## Ready     what /wave builds next
                                             ## Waiting   blocked on something outside the code
                                             ## Later     parked
            │
   /queue summary · fit · quick · promote · unblock      (size, choose and move work)
            │
            ▼
   /wave  ──plan──▶ one go/no-go ──▶ parallel lanes (test-first, reviewed) ──▶ handoff
            │                                                                    │
            │      shipped entries deleted, leftovers back to Later or Ready ◀───┘
            ▼
   stakeholder page (decisions the code couldn't settle) ──▶ /queue answers
```

- **Queue entries are specced from the code**, not from the report: real file paths (tests included), `file:line` evidence and a "Done when", so an agent can build each one unattended.
- **Decisions the code can't settle** (product, wording, design, cost, legal) aren't asked in chat. The entry gets a recommended answer and a `🔴 Decision open` block. After a wave, those questions appear as cards on a published page, and the answers flow back with `/queue answers`.
- **Planning tools:** `/queue summary` gives one line per item and the time to finish; `fit <window>` picks what one run finishes before a deadline; `quick` pulls small, unrelated fixes into one lean run; `promote` moves Later items that fit the next wave into Ready and recommends the model and effort to start `/wave` with. All of these use `estimate.py`, which is calibrated on past runs: every `/wave` handoff adds its real hours and cost and checks the fit.
- **`/wave` never pushes and never moves a ticket to Done.** `/wave plan` shows the estimate (hours, and weekly usage from the planned units) and stops; `/wave auto` runs unattended, and picks up that plan; `/wave lean` skips reviews for about a third of the usage.

Each skill's README has the full command list and file guide: [queue](productivity/queue/README.md), [wave](productivity/wave/README.md).

## Repo layout

```
productivity/
  queue/                    /queue skill
    SKILL.md                the skill (intake, safe writes, every subcommand)
    estimate.py             sizing, lanes, hours, weekly usage, model/effort profile
    queue-template.md       starting WORK_QUEUE.md
    batch-page-template.html  stakeholder decision page
    agents/openai.yaml      Codex: run only when typed
  wave/                     /wave skill
    SKILL.md                the skill (plan, go/no-go, run, handoff, auto, lean)
    lane-runner.js          generic Workflow script that runs every lane
    native-host.mjs         Codex native-subagent bridge
    codex-host.mjs          Codex CLI host (only on explicit request)
    prepare-auto.mjs        isolated checkout for /wave auto
    *.check.mjs             stub checks for each of the scripts above
    helpers/                commit, lock and run-cost helpers
    references/             Codex dispatch and auto-start procedures
    protocol-template.md    template for a project's ## Wave protocol
docs/superpowers/plans/     implementation plans for past changes to these skills
```

## Install

This repo holds the only copy of the skills. Claude Code loads skills from `~/.claude/skills/<name>/`, and Codex from `~/.agents/skills/<name>/`. Both follow symlinks, so link each skill folder into both places:

```bash
for s in queue wave; do
  ln -sfn "$PWD/productivity/$s" ~/.claude/skills/$s
  ln -sfn "$PWD/productivity/$s" ~/.agents/skills/$s
done
```

Run from the repo root. Edits here are live in both tools immediately, and `git pull` picks up changes made elsewhere. Make the `~/.agents/skills` links even without Codex: the skills find their own files (`estimate.py`, `codex-host.mjs`…) through `~/.agents/skills/<name>/`.

Each skill's `agents/openai.yaml` is Codex's version of `disable-model-invocation`: it runs only when you type it.

### Outside this repo

`/wave` also uses two things that live outside this repo:

| What | Where | Used for |
|---|---|---|
| `wave-builder`, `wave-checker`, `wave-planner` agent types | `~/.claude/agents/wave-*.md` | Claude Code only. Slim agents with just the tools each role needs, so each starts at 28–39k tokens instead of about 78k. Without them `/wave` falls back to general agents. |
| `simplified-technical-english` skill | `~/.agents/skills/simplified-technical-english/` | Every text a person reads (go/no-go, wave doc, tickets, batch page, wrap-up) is written in it and run through its `ste_check.py`. |

## Requirements

- Claude Code (with the Workflow tool for `/wave`), or Codex with native subagent tools.
- `python3`, `node`, `git`, `bash` and `perl`.
- Stakeholder pages that save answers need Claude's Artifact tools. In Codex the page is a local file, and people paste their answers back.

## Checks

Run these after editing the scripts. Each one prints `ok` lines and stops on the first failure.

```bash
python3 productivity/queue/estimate.py --selftest
```

```bash
python3 productivity/wave/helpers/codex-usage.py --selftest
```

```bash
cd productivity/wave && for f in *.check.mjs; do node "$f" || break; done
```
