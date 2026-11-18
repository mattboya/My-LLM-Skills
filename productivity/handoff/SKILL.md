---
name: handoff
description: Use on any long-running job (multi-hour work, an overnight run, /wave) to check the usage left at each chunk boundary and, when it gets low, stop cleanly and write HANDOFF.md so another model can continue; also when the user says "continue from HANDOFF.md" or types /handoff.
argument-hint: |-
  check      the usage left in this harness, and what to do about it
  now        stop at the end of this chunk and write HANDOFF.md, whatever the usage
  continue   pick the job up from HANDOFF.md
---

# /handoff

Long jobs stop dead when a usage limit runs out, often overnight. This skill makes them stop on purpose instead, near the limit, at a clean point, with a note (`HANDOFF.md`) any model can continue from: Claude, Codex or Gemini. The user chooses which model takes over and starts it.

## Reading the usage

```
python3 ~/.agents/skills/handoff/quota.py --harness <claude | codex | antigravity>
```

Claude Code → `claude`, Codex → `codex`, Antigravity → `antigravity`. It prints each usage window, then one verdict line (the exit code says the same: 0, 10, 20, 30):

| Verdict | Do |
|---|---|
| `ok` | Carry on. |
| `wait <min>` | Only the short limit is low, and it resets within the hour. Wait that long in the background, then check again and carry on here. Claude Code: a background `sleep <seconds>` (Bash with `run_in_background`); it wakes you when it exits. A harness that can't wait that long → treat it as `handoff`. |
| `handoff` | Stop, as **Stopping** says. |
| `unknown` | No reading. Carry on, check again at the next chunk, and say in the final message that usage couldn't be read. For Claude, the reading comes from the statusline (`claude-limits.sh` saves it on each refresh), so it exists only while a terminal Claude Code session runs. |

Each line says how old its reading is. The numbers are account-wide, so other sessions' use counts.

## When to check

A long job is any task that will take more than about an hour or runs while the user is away: an overnight run, a big refactor, a /wave.

- At the start, and at every **chunk boundary**: the point where a piece of work is finished and saved (a test turned green and committed, a file done, a /wave phase returned). Never mid-edit.
- Before starting a chunk that will be big (many files, a long test run, a fan-out of agents).
- `/handoff check` runs it once and reports.

## Stopping

On `handoff`, or `/handoff now`:

1. **Finish the chunk, small.** Don't start a new one. If the current chunk is far from done, cut back to its last working point (tests green), and put the rest under Left. Below 5% there's room for little more than this.
2. **Save the work.** If the job was already committing (the user asked for commits, or a skill like /wave commits), commit as the job does. Otherwise leave the changes uncommitted and list them on the Tree line: the user's own commit rules still hold.
3. **Write `HANDOFF.md`** at the git root (the working directory if there's no repo), in the format below. Keep it out of git: add `/HANDOFF.md` to `$(git rev-parse --git-common-dir)/info/exclude` if it isn't there. If a `HANDOFF.md` is already there from an earlier stop on this job, rewrite it: Done grows, Left shrinks.
4. **Stop**, ending with: `Stopped at <n>% left (<window>, resets <time>). HANDOFF.md has the rest: open any model in this folder and say "continue from HANDOFF.md".`

```
# Handoff

**Written:** YYYY-MM-DD HH:MM by <harness> · <model> — <why: "weekly limit at 4%, resets Thu 1:50PM">
**Branch:** <branch> · **Commit:** <short sha> · **Tree:** clean | <files changed but not committed, and why>
**Job:** <what the user asked for, in their words where possible>

## Done
- <what is finished and saved, one line each>

## Left
- <what remains, in the order to do it>

## Next step
<exactly one action, specific enough to start without re-reading the whole job>

## Check
<the commands that prove the done part works: tests, builds, gates>

## Notes
<decisions made and why, dead ends, gotchas, anything the next model would otherwise find out the hard way>
```

Write it for a model that has never seen this conversation: real paths, real commands, no "as discussed".

## Continuing (`/handoff continue`, or "continue from HANDOFF.md")

1. Read `HANDOFF.md`. Check it against git: the branch, `git rev-parse --short HEAD` against its Commit, and `git status` against its Tree line. If they differ (someone committed or edited since), read what changed (`git log <its commit>..HEAD`, `git diff`), and say so before going on.
2. Run its Check commands. If something it calls done is broken, fixing that is the first job.
3. Do the Next step, then work through Left, with the same checks as **When to check**, in this harness.
4. Stopping again → rewrite `HANDOFF.md` (**Stopping**). Job finished → delete `HANDOFF.md` and say so.

## /wave

`/wave` does these checks itself (its **Usage checks** rule): before each phase and each Workflow launch. Its wave doc is its record, so its `HANDOFF.md` is short: the wave doc's path, its Status, and "type `/wave` to continue it".

## Mistakes these rules exist for

| Tempting move | Why not |
|---|---|
| Push on past 5% to finish the whole task | The limit cuts the run mid-edit, and nobody writes down what was done. Stopping clean costs one chunk. |
| Commit to save the work when the job wasn't committing | The user decides when to commit. Uncommitted changes stay in the folder, and the Tree line names them. |
| Write "see above" or "the plan we agreed" | The next model can't see this conversation. |
| Wait out a weekly limit | It resets in days. Hand off. |
