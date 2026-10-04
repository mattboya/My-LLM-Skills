#!/bin/bash
# Commit ONLY the named paths in a shared checkout, safely alongside other lanes:
# `git commit --only` builds the commit from HEAD + these paths, so another lane's
# staged or unstaged work can never ride along. Retries while another lane holds
# .git/index.lock. New files get intent-to-add first.
# Config: wave.env beside this script (written at Wave 0) sets WAVE_REPO, and
# optionally WAVE_BRANCH (default main) and WAVE_AUTHOR (required git user.name).
# Usage: wave-commit.sh <message-file> <path> [<path>...]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/wave.env" ] && . "$HERE/wave.env"
REPO="${WAVE_REPO:?WAVE_REPO is not set; write it to $HERE/wave.env}"
BRANCH="${WAVE_BRANCH:-main}"
MSG="$1"; shift
cd "$REPO" || exit 2
if [ -n "${WAVE_AUTHOR:-}" ] && [ "$(git config --get user.name)" != "$WAVE_AUTHOR" ]; then echo "ABORT: git user.name is not $WAVE_AUTHOR"; exit 3; fi
[ "$(git rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || { echo "ABORT: not on $BRANCH"; exit 3; }
for p in "$@"; do
  if [ -e "$p" ] && ! git ls-files --error-unmatch -- "$p" >/dev/null 2>&1; then
    for i in $(seq 1 40); do git add -N -- "$p" 2>/dev/null && break; perl -e 'select(undef,undef,undef,1.5)'; done
  fi
done
for i in $(seq 1 60); do
  OUT=$(git commit --only -F "$MSG" -- "$@" 2>&1); RC=$?
  if [ $RC -eq 0 ]; then echo "$OUT" | head -3; git log -1 --format='COMMITTED %H %s'; exit 0; fi
  if echo "$OUT" | grep -q "index.lock"; then perl -e 'select(undef,undef,undef,1.5)'; continue; fi
  echo "$OUT"; exit $RC
done
echo "ABORT: index.lock held for too long"; exit 4
