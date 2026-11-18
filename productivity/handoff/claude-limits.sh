#!/bin/bash
# Statusline pass-through: saves Claude Code's statusline payload (it carries the account's rate limits) for quota.py,
# then prints it unchanged for the next statusline command in the pipe.
i=$(cat)
f="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/statusline-payload.json"
printf %s "$i" > "$f.$$" && mv -f "$f.$$" "$f"
printf %s "$i"
