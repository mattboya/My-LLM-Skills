#!/usr/bin/env python3
"""How much usage this harness has left, and whether a long job should keep going, wait, or hand off.

Usage: quota.py --harness claude|codex|antigravity [--threshold 5] [--wait-max 60] [--json]
       quota.py --selftest

Prints one line per usage window, then a verdict line:
  verdict: ok             more than --threshold percent left in every window
  verdict: wait <min>     a window is low, but it is short (under a day) and resets within --wait-max minutes,
                          and no other window is low: wait that long, then carry on in this harness
  verdict: handoff        a window is low and won't reset soon: finish the chunk, write HANDOFF.md, stop
  verdict: unknown        no reading: carry on and check again at the next chunk
Exit code: 0 ok, 10 wait, 20 handoff, 30 unknown.

Where each harness's numbers come from:
- claude: the statusline payload, saved by claude-limits.sh (beside this file) on every statusline refresh, at
  ${CLAUDE_CONFIG_DIR:-~/.claude}/statusline-payload.json. Claude Code gives the limits to the statusline only.
- codex: the newest rate_limits reading in ~/.codex/sessions (Codex logs one on every turn).
- antigravity: the picked Gemini model's quota, from queue/agy-models.py --json (the running app's local server).

ponytail: the readings are only as fresh as the harness's last log or statusline refresh; a reading whose window has
already reset counts as full. Upgrade path if a stale reading misleads a run: refuse readings older than N minutes.
"""
import argparse, glob, json, os, subprocess, sys, time
from datetime import datetime

HERE = os.path.dirname(os.path.realpath(__file__))
DAY_MIN = 1440


def epoch(v):
    """resets_at as epoch seconds: Codex and Claude give epoch numbers, Antigravity an ISO string."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return datetime.fromisoformat(str(v).replace('Z', '+00:00')).timestamp()


def window(name, used_pct, resets_at, minutes, now, read_at=None):
    """One usage window. A window whose reset time has passed has reset: it is full again."""
    reset = epoch(resets_at)
    left = 100.0 - float(used_pct)
    if reset is not None and reset <= now:
        left = 100.0
    age = round((now - read_at) / 60) if read_at else None
    return {'name': name, 'left': round(left, 1), 'resets_at': reset, 'minutes': minutes, 'age_min': age}


def claude(now):
    path = os.path.join(os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude'), 'statusline-payload.json')
    try:
        limits = json.load(open(path)).get('rate_limits') or {}
        read_at = os.path.getmtime(path)
    except (OSError, ValueError):
        return []
    sizes = {'five_hour': 300, 'seven_day': 7 * DAY_MIN}
    out = []
    for name, w in limits.items():
        if isinstance(w, dict):
            used = w.get('used_percentage', w.get('used_percent'))
            if used is not None:
                out.append(window(name, used, w.get('resets_at'), w.get('window_minutes') or sizes.get(name), now, read_at))
    return out


def codex(now, sessions=os.path.expanduser('~/.codex/sessions')):
    files = sorted(glob.glob(os.path.join(sessions, '**', '*.jsonl'), recursive=True), key=os.path.getmtime, reverse=True)
    for path in files[:5]:  # the newest reading is in the newest rollouts
        last = None
        read_at = os.path.getmtime(path)
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                if '"rate_limits"' in line:
                    try:
                        last = json.loads(line)['payload']['rate_limits']
                    except (ValueError, KeyError, TypeError):
                        pass
        if last:
            return [window(f"{w['window_minutes']}-minute", w['used_percent'], w.get('resets_at'), w['window_minutes'], now, read_at)
                    for w in (last.get('primary'), last.get('secondary')) if w and w.get('used_percent') is not None]
    return []


def antigravity(now):
    script = os.path.join(HERE, '..', 'queue', 'agy-models.py')
    r = subprocess.run([sys.executable, script, '--json'], capture_output=True, text=True, timeout=15)
    if r.returncode:
        return []
    d = json.loads(r.stdout)
    for m in d['models']:
        if m['label'] == d['picked'] and 'remainingFraction' in m:
            reset = epoch(m.get('resetTime'))
            # ponytail: Antigravity doesn't say the window's length; time to reset stands in, so a refill due soon reads as short
            minutes = (reset - now) / 60 if reset else None
            return [window(m['label'], 100 * (1 - m['remainingFraction']), m.get('resetTime'), minutes, now)]
    return []


def verdict(windows, now, threshold=5, wait_max=60):
    """('ok' | 'wait' | 'handoff' | 'unknown', minutes to wait)."""
    if not windows:
        return 'unknown', 0
    low = [w for w in windows if w['left'] <= threshold]
    if not low:
        return 'ok', 0
    if len(low) == 1:
        w = low[0]
        mins = (w['resets_at'] - now) / 60 if w['resets_at'] else None
        if mins is not None and (w['minutes'] or 0) < DAY_MIN and mins <= wait_max:
            return 'wait', max(1, round(mins))
    return 'handoff', 0


def selftest():
    now = 1_000_000.0
    w = lambda left, reset_min, size: window('w', 100 - left, now + reset_min * 60, size, now)
    assert verdict([], now) == ('unknown', 0)
    assert verdict([w(40, 100, 300), w(60, 3000, 10080)], now) == ('ok', 0)
    assert verdict([w(4, 30, 300), w(60, 3000, 10080)], now) == ('wait', 30)  # short window, resets soon
    assert verdict([w(4, 90, 300), w(60, 3000, 10080)], now) == ('handoff', 0)  # short window, resets too late
    assert verdict([w(60, 30, 300), w(3, 30, 10080)], now) == ('handoff', 0)  # weekly window: never wait it out
    assert verdict([w(4, 30, 300), w(4, 3000, 10080)], now) == ('handoff', 0)  # both low
    assert window('w', 99, now - 1, 300, now)['left'] == 100  # its reset has passed: full again
    assert epoch('2026-11-18T00:00:00Z') == 1794960000
    print('selftest ok')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--harness', choices=['claude', 'codex', 'antigravity'])
    ap.add_argument('--threshold', type=float, default=5)
    ap.add_argument('--wait-max', type=float, default=60)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.harness:
        ap.error('--harness is required')
    now = time.time()
    windows = {'claude': claude, 'codex': codex, 'antigravity': antigravity}[a.harness](now)
    v, mins = verdict(windows, now, a.threshold, a.wait_max)
    if a.json:
        print(json.dumps({'harness': a.harness, 'windows': windows, 'verdict': v, 'wait_minutes': mins}))
    else:
        for w in windows:
            when = datetime.fromtimestamp(w['resets_at']).strftime('%a %-I:%M%p') if w['resets_at'] else 'unknown'
            age = f", read {w['age_min']} min ago" if w['age_min'] else ''
            print(f"{a.harness} {w['name']}: {w['left']:.0f}% left, resets {when}{age}")
        if not windows:
            print(f'{a.harness}: no usage reading found')
        print(f'verdict: {v}' + (f' {mins}' if v == 'wait' else ''))
    sys.exit({'ok': 0, 'wait': 10, 'handoff': 20, 'unknown': 30}[v])


if __name__ == '__main__':
    main()
