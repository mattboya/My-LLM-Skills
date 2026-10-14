# /queue

A skill for Claude Code (`/queue`) and Codex (`$queue`) that turns "this is broken" or "I want X" into a fully spec'd entry in a project's `WORK_QUEUE.md`, ready for [`/wave`](../wave) to build.

It specs from the code, not from the report: it finds where the behavior lives, confirms it still happens on current code, checks `git log` for a recent fix, and searches the queue for a duplicate before writing anything. Each entry gets real file paths (including the test file), `file:line` evidence, and a "Done when" so an agent can build it unattended.

Manual-only (`disable-model-invocation: true`): it runs when you type `/queue`, never on its own.

## How the queue works

`WORK_QUEUE.md` lives at the git root and is gitignored on purpose (a private, local inbox). It has three working sections:

| Section | Meaning |
|---|---|
| `## Ready` | Exactly what `/wave` builds next. |
| `## Waiting` | Can't start until something outside the code happens (a person's go, a teammate's unpushed work, legal). Each entry's first line says what it's waiting on. |
| `## Later` | Parked. `/queue promote` pulls items up when they fit. |

Decisions the code can't settle (product, wording, design, cost, legal) are not asked in chat. The entry is written with the recommended answer and a `🔴 Decision open` block, and that question later appears as a card on a stakeholder page. Stakeholders answer on the page; `/queue answers` folds their answers back into the queue.

Because the file has no git history, every write is a "safe write": copy to scratch, build the new version, `cmp` the live file against the copy (another session may have edited it), then `cp`.

## Commands

```
/queue <what's wrong or wanted>   Spec a fix or change from the code and add it to Ready.
/queue <…> later                  Same, but file it under Later.
/queue summary                    One line per item on what it's worth, and the time to finish. Changes nothing.
/queue fit <7h | 11:30pm>         The most Ready items one /wave run finishes in that window, and the /wave line to paste. Changes nothing.
/queue fit <window> lean          The same for a /wave lean run (test-first builders, one final check, no reviews).
/queue quick [3h]                 Pull small fixes that share nothing (single bullets from follow-up lists too) into Ready, and hand you the /wave lean line.
/queue promote                    Move Later items that fit the next wave into Ready, report what moved, and the model and effort to kick off /wave with.
/queue unblock                    Publish a page to decide the Waiting items; answers move them to Ready.
/queue answers                    Apply answers saved on the queue's pages (every /queue also does this first).
/queue help                       This list.
/wave                             Build everything in Ready: plan, one go/no-go, then the run (a separate skill).
/wave ID, ID, …                   Build only those Ready items (the line /queue fit hands you).
/wave auto                        The same, unattended: it takes the recommended answers and logs them for you.
```

## Files

| File | What it is |
|---|---|
| `SKILL.md` | The skill itself: intake steps, safe-write rules, and the summary / fit / promote / unblock / answers procedures. |
| `queue-template.md` | Starting `WORK_QUEUE.md` for a project that doesn't have one yet. |
| `batch-page-template.html` | The stakeholder page published after each batch (and by `/queue unblock`): plain-language decision cards that save answers to the page. |
| `estimate.py` | Sizes entries, groups them into parallel lanes by shared files, and estimates wave hours and the share of weekly usage (Claude, or Codex with `--codex`) from past runs. Powers `summary`, `fit`, `promote` and the model/effort recommendation. `python3 estimate.py --selftest` checks it. |
| `batch-page-companion.draft.md` | Draft of a separate "publish the batch page" skill. Not loaded (it isn't named `SKILL.md`). |
| `agents/openai.yaml` | Codex metadata: runs only when you type `$queue`. |

## Requirements

- Claude Code or Codex. Stakeholder pages that save answers need Claude's Artifact / ArtifactData tools. In Codex the page is a local file: people press **Copy my answers**, and `$queue answers <pasted>` applies them (see the skill's **In Codex** section).
- `python3` on the PATH for `estimate.py`.
- Linked at `~/.agents/skills/queue` (and `~/.claude/skills/queue` for Claude), per the [root README](../../README.md). `SKILL.md` and `/wave` read `estimate.py` through `~/.agents/skills/queue`.
