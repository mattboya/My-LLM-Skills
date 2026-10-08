#!/usr/bin/env python3
"""How much of the Codex weekly usage limit a /wave run took, from Codex's own session logs.

Usage: codex-usage.py --since 2026-10-08T01:36 [--until 2026-10-08T04:30] [--sessions ~/.codex/sessions]
       codex-usage.py --selftest
  --since / --until  the run's go and handoff times (local time unless they carry a zone); --until defaults to now

Every Codex turn logs the account's weekly percent used (token_count events, the 10080-minute window), so this reads
every rollout written in the window, native subagents and codex exec workers included, and adds up how far the
percent rose. A weekly reset mid-run is handled: each reset window counts on its own. It is account-wide, so other
Codex work done during the run counts too. Put the line it prints in the wave doc's Results; the queue's
estimate.py turns those into CODEX_RUN_PCT.
"""
import argparse, glob, json, os
from datetime import datetime, timezone

WEEK_MIN = 10080


def when(s):
    t = datetime.fromisoformat(s.replace('Z', '+00:00'))
    return t if t.tzinfo else t.astimezone()


def readings(lines, since, until):
    """(time, resets_at, used_percent) for each weekly reading in [since, until]."""
    for line in lines:
        if '"rate_limits"' not in line:
            continue
        try:
            e = json.loads(line)
            t = when(e['timestamp'])
            limits = e['payload']['rate_limits']
        except (ValueError, KeyError, TypeError):
            continue
        if not since <= t <= until:
            continue
        for w in (limits.get('primary'), limits.get('secondary')):
            if w and w.get('window_minutes') == WEEK_MIN and w.get('used_percent') is not None:
                yield t, w.get('resets_at'), w['used_percent']


def used(rs):
    """Percent of the weekly limit used: the rise within each reset window, summed."""
    windows = {}
    for _, reset, pct in rs:
        reset = round((reset or 0) / 3600)  # resets_at drifts a few seconds between sessions; a real reset moves it days
        lo, hi = windows.get(reset, (pct, pct))
        windows[reset] = (min(lo, pct), max(hi, pct))
    return sum(hi - lo for lo, hi in windows.values()), windows


def selftest():
    def ev(t, pct, reset=1):
        return json.dumps({'timestamp': t, 'payload': {'type': 'token_count', 'rate_limits': {
            'primary': {'used_percent': pct, 'window_minutes': WEEK_MIN, 'resets_at': reset}, 'secondary': None}}})
    lines = [ev('2026-10-08T00:00:00Z', 10), ev('2026-10-08T01:00:00Z', 20), ev('2026-10-08T02:00:00Z', 27),
             ev('2026-10-08T03:00:00Z', 2, reset=7 * 86400), ev('2026-10-08T04:00:00Z', 5, reset=7 * 86400 + 4), 'not json', ev('2026-10-09T00:00:00Z', 90)]
    total, _ = used(readings(lines, when('2026-10-08T00:30:00Z'), when('2026-10-08T05:00:00Z')))
    assert total == 7 + 3, total  # 20 -> 27, then the reset, 2 -> 5; the readings outside the window don't count
    print('selftest ok')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--since')
    ap.add_argument('--until')
    ap.add_argument('--sessions', default=os.path.expanduser('~/.codex/sessions'))
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.since:
        ap.error('--since is required')
    since, until = when(a.since), when(a.until) if a.until else datetime.now(timezone.utc)
    rs = []
    for path in glob.glob(os.path.join(a.sessions, '**', '*.jsonl'), recursive=True):
        if datetime.fromtimestamp(os.path.getmtime(path), timezone.utc) >= since:  # untouched since the go: nothing in the window
            with open(path, encoding='utf-8', errors='replace') as f:
                rs.extend(readings(f, since, until))
    if not rs:
        raise SystemExit('codex-usage.py: no weekly readings in that window (is --since right, and did Codex run?)')
    total, windows = used(rs)
    rs.sort()
    print(f'**Codex weekly usage:** about {total:.0f}% of the weekly limit ({rs[0][2]:.0f}% → {rs[-1][2]:.0f}%'
          + (f', across {len(windows)} reset windows' if len(windows) > 1 else '') + f'; {len(rs)} readings).')


if __name__ == '__main__':
    main()
