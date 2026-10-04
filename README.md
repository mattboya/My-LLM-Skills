# My LLM Skills

Skills I've written for Claude Code and Codex, grouped by area. In Codex, type `$queue` / `$wave` instead of `/queue` / `/wave`.

| Skill | What it does |
|---|---|
| [`productivity/queue`](productivity/queue) | `/queue`: spec a fix or feature from the code into a project's `WORK_QUEUE.md`, plus summary, time-fit, promote, unblock and stakeholder-answer commands. |
| [`productivity/wave`](productivity/wave) | `/wave`: build everything in the queue's Ready section as one parallel, test-first, adversarially reviewed batch. |

## Install

This repo is the only copy. Claude Code loads skills from `~/.claude/skills/<name>/`, and Codex from `~/.agents/skills/<name>/`. Both follow symlinks, so link each skill folder into both places:

```bash
for s in queue wave; do
  ln -sfn "$PWD/productivity/$s" ~/.claude/skills/$s
  ln -sfn "$PWD/productivity/$s" ~/.agents/skills/$s
done
```

Run from the repo root. Edits here are live in both tools immediately, and `git pull` picks up changes made elsewhere. Make the `~/.agents/skills` links even without Codex: the skills find their own files (`estimate.py`, `codex-host.mjs`…) through `~/.agents/skills/<name>/`.

Each skill's `agents/openai.yaml` is Codex's version of `disable-model-invocation`: it runs only when you type it.
