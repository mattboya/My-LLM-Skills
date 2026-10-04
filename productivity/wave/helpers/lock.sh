#!/bin/bash
# Mutex for a wave's hot files in a shared checkout (/wave).
# One lock per repo-relative path = one atomic `mkdir` holding an owner file.
# `acquire` takes every path given, in sorted path order, so two agents that
# each need several locks can never deadlock. It blocks (1.5s polls) until it
# has them all; on timeout it releases whatever it took and exits 5.
#
# Usage:
#   lock.sh acquire <owner> <path>...   # e.g. lock.sh acquire L6-U1 resources/css/app.css
#   lock.sh release <owner> <path>...   # only releases locks that <owner> holds
#   lock.sh status                      # who holds what, since when
#   lock.sh break <path>                # MAIN SESSION ONLY: clear a dead agent's lock
# Hold a lock from your first edit of the file to the commit that contains it.
# Never hold one across a review or while waiting on another agent.
set -uo pipefail
LOCKROOT="$(cd "$(dirname "$0")/.." && pwd)/locks"
TIMEOUT_S="${LOCK_TIMEOUT_S:-2700}"
mkdir -p "$LOCKROOT"
key() { printf '%s' "$1" | sed 's#^\./##; s#/#__#g'; }
sleep15() { perl -e 'select(undef,undef,undef,1.5)'; }

cmd="${1:-}"; shift || true
case "$cmd" in
  acquire)
    owner="${1:?owner}"; shift
    [ $# -gt 0 ] || { echo "lock.sh: no paths" >&2; exit 2; }
    taken=()
    start=$(date +%s)
    for p in $(printf '%s\n' "$@" | sed 's#^\./##' | sort -u); do
      d="$LOCKROOT/$(key "$p").lock"
      warned=0
      until mkdir "$d" 2>/dev/null; do
        if [ -f "$d/owner" ] && [ "$(head -1 "$d/owner")" = "$owner" ]; then break; fi
        now=$(date +%s)
        if [ $((now - start)) -ge "$TIMEOUT_S" ]; then
          echo "lock.sh: TIMEOUT waiting for $p (held by: $(cat "$d/owner" 2>/dev/null | tr '\n' ' ')); releasing what I took" >&2
          for t in "${taken[@]:-}"; do [ -n "$t" ] && rm -rf "$LOCKROOT/$(key "$t").lock"; done
          exit 5
        fi
        if [ $warned -eq 0 ] && [ $((now - start)) -ge 300 ]; then
          echo "lock.sh: still waiting for $p, held by: $(cat "$d/owner" 2>/dev/null | tr '\n' ' ')" >&2; warned=1
        fi
        sleep15
      done
      printf '%s\n%s\n%s\n' "$owner" "$p" "$(date '+%Y-%m-%d %H:%M:%S')" > "$d/owner"
      taken+=("$p")
      echo "LOCKED $p by $owner"
    done
    ;;
  release)
    owner="${1:?owner}"; shift
    for p in "$@"; do
      p="${p#./}"; d="$LOCKROOT/$(key "$p").lock"
      if [ ! -d "$d" ]; then echo "lock.sh: $p was not locked"; continue; fi
      holder="$(head -1 "$d/owner" 2>/dev/null)"
      if [ "$holder" != "$owner" ]; then echo "lock.sh: REFUSED to release $p: held by $holder, not $owner" >&2; continue; fi
      rm -rf "$d"; echo "RELEASED $p by $owner"
    done
    ;;
  status)
    found=0
    for d in "$LOCKROOT"/*.lock; do
      [ -d "$d" ] || continue; found=1
      echo "$(sed -n 2p "$d/owner")  <-  $(sed -n 1p "$d/owner")  since $(sed -n 3p "$d/owner")"
    done
    [ $found -eq 1 ] || echo "(no locks held)"
    ;;
  break)
    p="${1:?path}"; p="${p#./}"; rm -rf "$LOCKROOT/$(key "$p").lock"; echo "BROKE lock on $p"
    ;;
  *) echo "usage: lock.sh acquire|release <owner> <path>... | status | break <path>" >&2; exit 2 ;;
esac
