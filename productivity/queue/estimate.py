#!/usr/bin/env python3
"""Estimate how long a WORK_QUEUE.md takes to finish in parallel /wave runs.

Usage: estimate.py <path/to/WORK_QUEUE.md> [--json] [--with ID,ID] [--only ID,ID]
       estimate.py <path/to/WORK_QUEUE.md> --candidates     (JSON: each Later/Waiting item vs Ready)
       estimate.py <path/to/WORK_QUEUE.md> --promote ID,ID [--exempt ID,ID]  (JSON: which Later items fit the next wave, added in that order)
       estimate.py <path/to/WORK_QUEUE.md> --profile [--only ID,ID]  (JSON: the model and effort each Ready task needs)
       estimate.py <path/to/WORK_QUEUE.md> --splits         (JSON: Ready tasks on the longest chain that could split to finish sooner)
       estimate.py <path/to/WORK_QUEUE.md> --fit HOURS [--lean] [--with ID,ID] [--without ID,ID]
                                                            (JSON: the most Ready items one run finishes in HOURS)
       estimate.py --units N [--lean]                       (JSON: a planned run's weekly usage from its unit count: /wave's plan)
       estimate.py --selftest
Add --codex to any of these to price weekly usage from Codex runs (CODEX_RUN_PCT) instead of Claude's.

Reads every "### " entry under ## Ready, ## Waiting and ## Later (HTML comments ignored), then:
- size: the entry's own "(S · risk ..)" / "(M ..)" / "(L ..)" markers, summed when an
  entry has several sized slices; otherwise by how many files Touches names
  (<= 2 -> S, <= 6 -> M, more -> L), or, with no Touches, by how many sub-items it lists;
- can start now = every Ready item (that is exactly what /wave builds); everything = Ready +
  Waiting + Later;
- misfiled: a Ready item whose heading, Status or JIRA/Ticket line says BLOCKED, on hold or
  waiting on someone: it probably belongs in ## Waiting (reported, never moved);
- human: Type says human -> no agent time, listed separately;
- lanes: entries whose Touches share a file run one after another in one lane (union-find),
  except files three or more entries touch: /wave locks those instead of chaining the lanes;
- waves: at most MAX_LANES lanes per wave, longest lanes placed first; waves run in sequence;
- a wave's hours run from typing /wave to its handoff: run_hours() below.

ponytail: run_hours() is fit to the 11 full runs in CALIBRATION (refit 2026-10-20; times from each run's session
transcript, /wave typed to the wrap-up). Only runs since planning prototypes (2026-10-03 (2)) count: builds got much
faster, so older runs (09-25 to 10-02, 5-16h) would pull the fit up. Fixed part about 1.8h (planning 0.6-2h, then the
handoff); the lanes 0.40 of the longest chain. The selftest allows 35%, not 30: same-size runs differ by 2x (10-03 (2):
1.7h for 4 items; 10-13: 3.5h for 2), and no shape fits every run within 30 (best: 32-33%). fit()'s hours_range shows
the spread. A /wave plan run gets a firmer number from the planner, who knows the units and lanes.

ponytail: lean_run_hours() is fit to the six lean runs in LEAN_CALIBRATION the same way, within 40%. Lean runs are
noisier still (11 items took 1.6h on 10-08 and 16 took 3.8h on 10-02), and the chain barely predicts them. Left out:
friendslop 10-19 (6.4h with 2h of an agent stalled on an approval prompt).

ponytail: usage is priced from units, because cost follows the units the planner cuts, not the items: $9-17 a unit on
every project, while Salesfirst items split into 1.0-2.5 units and other projects' into about 1. unit_dollars() is fit
to the 16 Claude ledgers in UNIT_CALIBRATION (dollars from wave-cost.py), each within 30%. Full runs curve upward:
about $60, then $5 a unit plus $0.14 a unit squared, because a big run adds journeys and close-outs and runs under more
load ($10-12 a unit at 10-27 units, $16-17 at 49-54). A straight line misses the big runs by a third, the costly way.
The fit stops at 54 full units; past that it is extrapolated. Lean runs are a straight line: $45 + $6.5 a unit.
- /wave plan: unit_usage() (--units) prices the plan's own unit count.
- /queue promote: weekly_pct() guesses 1.5 units an item (lean 1.2) and prices that. Item counts predict cost badly
  (up to 61% off), so promote also gives usage_range(): the lowest and highest actual/estimate across the ledgers.
  Next step if that range is too wide: learn each project's units per item from its own ledgers.
Points are DOLLARS_PER_WEEKLY_POINT, measured once on Matt's plan; another plan needs its own (read /usage before and
after a run). Re-fit when /wave's handoff reports a miss: it adds every run to these tables and runs the selftest.

ponytail: --codex prices from CODEX_RUN_PCT instead. Codex logs the weekly percent itself, and wave/helpers/
codex-usage.py reads it for a run. The one data point so far is a paused lean run: 2026-10-07 (friendslop-game,
Matt's ChatGPT Pro Lite plan) built 33 of its 57 units (37 items, so about 21 items' worth) for 54% of the week.
That is about 2.5% an item lean, 7.2% full by LEAN_USAGE, with no fixed part (one run can't separate it), and 1.6% a
lean unit for --units (CODEX_LEAN_UNIT_PCT; full borrows Claude's full/lean ratio). Never borrow Claude's levels
across providers. Re-fit once a finished Codex run's Results give its percent.
"""
import json
import re
import sys

MINUTES = {'XS': 30, 'S': 45, 'M': 70, 'L': 110, 'XL': 180}
PLAN_H = 1.1           # typing /wave to the first lane: planning checks with prototypes, the go/no-go, Wave 0 (0.6-2h since 10-03)
LANE_FACTOR = 0.40     # the lanes phase, as a share of the longest chain's summed minutes
TAIL_H = 0.7           # after the last lane: close-outs and the handoff (the runner now does journeys and final gates)
ITEMS_PER_H = 2.5      # the fastest whole-run pace yet: parallel lanes aren't free
LEAN_PLAN_H = 1.0      # lean, typing /wave lean to the first lane: the checkers prototype every bullet, plus go and tickets
LEAN_LANE_FACTOR = 0.09  # lean lanes, as a share of the longest chain
LEAN_TAIL_H = 0.7      # lean, after the last lane: final gates, any gate fix, handoff
LEAN_ITEMS_PER_H = 7   # the fastest lean pace: 70 items in 7.4h (10-05)
DOLLARS_PER_WEEKLY_POINT = 29  # wave-cost.py's: measured 2026-10-03 on Opus 5.5 and Matt's plan
UNIT_DOLLARS = (60, 5.0, 0.14)  # a full run's $ from its units: fixed + per unit + per unit squared (docstring)
LEAN_UNIT_DOLLARS = (45, 6.5, 0)  # the same for a lean run: a straight line
UNITS_PER_ITEM = 1.5           # promote's guess at the units the planner cuts an item into (full runs: 1.0-2.5)
LEAN_UNITS_PER_ITEM = 1.2      # the same for lean runs (0.9-1.5)
LEAN_USAGE = 0.35              # Codex only: a lean run's share of a full run's usage (modelled, wave/SKILL.md)
CODEX_RUN_PCT = (0, 7.2)       # (weekly % fixed, weekly % an item) for a full Codex run: one paused lean run (docstring)
CODEX_LEAN_UNIT_PCT = 54 / 33  # weekly % a lean Codex unit: 2026-10-07 built 33 units for 54%
UNIT_CALIBRATION = [           # (wave, items, units, $ from its .cost.md ledger, lean)
    ('2026-10-03 (3) salesfirst', 11, 26, 278, False),
    ('2026-10-03 friendslop', 9, 10, 121, False),
    ('2026-10-05 salesfirst', 70, 108, 822, True),
    ('2026-10-06 salesfirst', 10, 14, 118, True),
    ('2026-10-08 jsonify', 4, 4, 89, False),
    ('2026-10-08 soulseek-auto', 10, 11, 105, False),
    ('2026-10-08 salesfirst', 11, 11, 99, True),
    ('2026-10-08 (2) salesfirst', 22, 19, 208, True),
    ('2026-10-09 salesfirst', 10, 12, 132, False),
    ('2026-10-10 salesfirst', 20, 49, 851, False),
    ('2026-10-11 salesfirst', 11, 21, 267, False),
    ('2026-10-13 salesfirst', 2, 2, 64, False),
    ('2026-10-14 salesfirst', 11, 27, 366, False),
    ('2026-10-14 (2) salesfirst', 9, 10, 173, False),
    ('2026-10-19 salesfirst', 32, 54, 898, False),
    ('2026-10-19 friendslop', 22, 32, 212, True),
    ('2026-10-23 friendslop', 20, 30, 280, False),
    ('2026-10-24 friendslop', 25, 44, 581, False),
    ('2026-10-28 friendslop', 20, 27, 294, False),
    ('2026-10-29 friendslop', 8, 11, 136, False),
]
CODEX = False                  # ponytail: set from --codex in main; a parameter through every caller if it ever matters
MAX_LANES = 21         # the most lanes a wave has run at once (16 agents at a time)
MARGIN = 0.8           # /queue fit plans to this share of the window (Matt, 2026-09-30)
PROMOTE_SLACK_H = 0.25  # /queue promote: the most an item may add to the next wave without an exempt reason
CALIBRATION = [        # (wave, longest lane h by this script on its .queue.md snapshot (in-scope items only), items, actual h)
    ('2026-10-03 (2) salesfirst', 1.17, 4, 1.72),
    ('2026-10-03 (3) salesfirst', 4.83, 11, 4.23),
    ('2026-10-08 jsonify', 4.17, 4, 4.78),
    ('2026-10-08 soulseek-auto', 5.83, 10, 3.28),
    ('2026-10-09 salesfirst', 2.33, 10, 3.47),
    ('2026-10-10 salesfirst', 15.67, 20, 11.88),
    ('2026-10-11 salesfirst', 5.5, 11, 4.75),
    ('2026-10-13 salesfirst', 1.83, 2, 3.48),
    ('2026-10-14 salesfirst', 18.33, 11, 6.97),
    ('2026-10-14 (2) salesfirst', 4.83, 9, 5.53),
    ('2026-10-19 salesfirst', 32.42, 32, 12.73),
    ('2026-10-23 friendslop', 9.92, 20, 6.4),
    ('2026-10-24 friendslop', 17.0, 25, 11.35),
    ('2026-10-28 friendslop', 4.17, 20, 6.68),
    ('2026-10-29 friendslop', 3.0, 8, 4.5),
    ('2026-11-02 salesfirst', 19.5, 29, 17.5),
]
LEAN_CALIBRATION = [   # the same shape, for /wave lean runs
    ('2026-10-02 salesfirst', 6.67, 16, 3.82),
    ('2026-10-03 salesfirst', 8.33, 12, 2.17),
    ('2026-10-05 salesfirst', 92.83, 70, 7.43),
    ('2026-10-06 salesfirst', 11.0, 10, 1.98),
    ('2026-10-08 salesfirst', 5.5, 11, 1.57),
    ('2026-10-08 (2) salesfirst', 33.5, 22, 3.83),
]


def run_hours(longest_lane_h, items):
    """Typing /wave to handoff for one wave: its longest chain, or its item count at the best pace seen, whichever is longer."""
    return max(PLAN_H + LANE_FACTOR * longest_lane_h + TAIL_H, items / ITEMS_PER_H)


def lean_run_hours(longest_lane_h, items):
    """Typing /wave lean to handoff: planning, building the longest chain, final gates and handoff (one calibration run)."""
    return max(LEAN_PLAN_H + LEAN_LANE_FACTOR * longest_lane_h + LEAN_TAIL_H, items / LEAN_ITEMS_PER_H)


def weekly_pct(items, lean=False):
    """One run's share of the weekly usage limit, in percent, before it is planned: items -> guessed units -> dollars."""
    if CODEX:
        fixed, per = CODEX_RUN_PCT
        return (fixed + per * items) * (LEAN_USAGE if lean else 1)
    return unit_dollars(items * (LEAN_UNITS_PER_ITEM if lean else UNITS_PER_ITEM), lean) / DOLLARS_PER_WEEKLY_POINT


def unit_dollars(units, lean=False):
    a, b, c = LEAN_UNIT_DOLLARS if lean else UNIT_DOLLARS
    return a + b * units + c * units * units


def unit_usage(units, lean=False):
    """/wave plan: a planned run's weekly usage from its unit count. Firmer than weekly_pct(): cost follows units."""
    if CODEX:  # ponytail: one lean Codex run; full borrows Claude's full/lean ratio until a full Codex run is measured
        pct = CODEX_LEAN_UNIT_PCT * units * (1 if lean else unit_dollars(units) / unit_dollars(units, True))
        return {'units': units, 'lean': lean, 'weekly_pct': round(pct, 1), 'usage_basis': usage_basis()}
    rows = [(u, d) for _, _, u, d, ln in UNIT_CALIBRATION if ln == lean]
    ratios = [d / unit_dollars(u, lean) for u, d in rows]
    dollars = unit_dollars(units, lean)
    return {'units': units, 'lean': lean, 'dollars': round(dollars),
            'weekly_pct': round(dollars / DOLLARS_PER_WEEKLY_POINT, 1),
            'weekly_pct_range': [round(dollars * min(ratios) / DOLLARS_PER_WEEKLY_POINT, 1), round(dollars * max(ratios) / DOLLARS_PER_WEEKLY_POINT, 1)],
            'usage_basis': usage_basis()}


def usage_range(lean=False):
    """What weekly_pct() is off by: the lowest and highest actual/estimate across the measured runs."""
    r = [d / (weekly_pct(n, ln) * DOLLARS_PER_WEEKLY_POINT) for _, n, _, d, ln in UNIT_CALIBRATION if ln == lean]
    return min(r), max(r)


def usage_basis():
    if CODEX:
        return 'one paused lean Codex run on a Pro Lite plan (rough; another plan reads differently)'
    return 'Claude runs, at $%d a weekly point (another plan reads differently)' % DOLLARS_PER_WEEKLY_POINT


RANGE = (min(a / run_hours(h, n) for _, h, n, a in CALIBRATION), max(a / run_hours(h, n) for _, h, n, a in CALIBRATION))
HOLD = re.compile(r'BLOCKED|🚧|\bon hold\b|\bheld\b|waiting on|waits on|\bhold\b', re.I)
SIZE = re.compile(r'\((XS|S|M|L|XL)(?:/[SMLX]+)?\s*[·)]')
# Model/effort tiers, cheapest first, as the app's picker names them. Haiku 4.5 is never offered for a wave
# (adversarial review with revert-proofs needs more, and its 200K context is too small); Fable 5.1 costs 2.5x Opus.
TIERS = [('Sonnet 5', 'high'), ('Sonnet 5', 'extra'), ('Opus 5.5', 'high'), ('Opus 5.5', 'extra'), ('Opus 5.5', 'max')]
RISK = {  # what a change touches, read from its title, Want and Done when only
    'pay math': r'\b(pay|payout|commission|income|comp[ -]plan|quota|money|currency|pricing)\b',
    'security or privacy': r'\b(auth|login|password|permission|privacy|security|secret)\b',
    'data or database': r'\b(migration|schema|purge|data integrity|backfill)\b',
    'background jobs': r'\b(temporal|workflow|activit(?:y|ies)|worker|concurren\w*|race)\b',
    "Linda's words or tools": r'\b(prompt|tool description|llm|eval)\b',
}
PATH = re.compile(r'(?<![\w./-])(?:[\w.\-{},]+(?:/[\w.\-{},*]+)+|[\w.\-]+\.(?:php|tsx?|jsx?|css|json|md|ya?ml|py|sh))\b')


def parse(text):
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    items = []
    for section in ('Ready', 'Waiting', 'Later'):
        m = re.search(r'\n## ' + section + r'\n(.*?)(?=\n## |\Z)', text, re.S)
        if not m:
            continue
        for block in re.split(r'\n(?=### )', '\n' + m.group(1)):
            block = block.strip()
            if not block.startswith('### '):
                continue
            heading = block.splitlines()[0][4:]
            item_id = heading.split(' — ')[0].split(' 🚧')[0].strip()
            fields = dict(re.findall(r'^- \*\*([^*:]+):?\*\*:?[ \t]*(.*)$', block, re.M))
            # Touches may continue on indented sub-bullets until the next top-level field.
            tm = re.search(r'^- \*\*Touches:?\*\*:?(.*?)(?=^- \*\*|\Z)', block, re.M | re.S)
            touches = tm.group(1) if tm else ''
            files = sorted({p.strip('`.,;') for p in PATH.findall(touches)})
            sizes = SIZE.findall(block)
            subitems = len(re.findall(r'^\s*- (?!\*\*[A-Za-z ]+:?\*\*)', block, re.M))
            if sizes:
                minutes, sized_by = sum(MINUTES[s] for s in sizes), 'entry'
            elif files:
                minutes, sized_by = (MINUTES['S'] if len(files) <= 2 else MINUTES['M'] if len(files) <= 6 else MINUTES['L']), 'touches'
            else:
                minutes, sized_by = (MINUTES['S'] if subitems <= 2 else MINUTES['M'] if subitems <= 5 else MINUTES['L']), 'sub-items'
            hold_text = ' '.join([heading, fields.get('Status', ''), fields.get('JIRA', ''), fields.get('Ticket', '')])
            items.append({'id': item_id, 'section': section, 'title': heading, 'files': files, 'minutes': minutes,
                          'text': block, 'layer': fields.get('Layer', '').strip().lower(),
                          'held': bool(HOLD.search(hold_text)), 'human': 'human' in fields.get('Type', '').lower(), 'sized_by': sized_by})
    return items


def lanes_of(items):
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    count = {}
    for it in items:
        for f in it['files']:
            count[f] = count.get(f, 0) + 1
    owner = {}
    for i, it in enumerate(items):
        for f in it['files']:
            if count[f] >= 3:  # a hot file: locked in /wave, so it doesn't chain lanes
                continue
            if f in owner:
                parent[find(i)] = find(owner[f])
            else:
                owner[f] = i
    groups = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(items[i])
    return sorted(groups.values(), key=lambda g: -sum(x['minutes'] for x in g))


def plan(items):
    if not items:
        return {'items': 0, 'lanes': 0, 'waves': [], 'hours': 0.0, 'lean_hours': 0.0, 'weekly_pct': 0.0, 'lean_weekly_pct': 0.0,
                'weekly_pct_range': [0.0, 0.0], 'lean_weekly_pct_range': [0.0, 0.0]}
    lanes = lanes_of(items)
    waves = []
    for lane in lanes:  # longest first, so the long chains spread across waves evenly
        target = next((w for w in waves if len(w) < MAX_LANES), None)
        if target is None:
            target = []
            waves.append(target)
        target.append(lane)
    out = []
    for w in waves:
        longest = max(sum(x['minutes'] for x in lane) for lane in w) / 60
        out.append({'lanes': len(w), 'items': sum(len(l) for l in w), 'longest_lane_h': round(longest, 2),
                    'hours': round(run_hours(longest, sum(len(l) for l in w)), 2),
                    'lean_hours': round(lean_run_hours(longest, sum(len(l) for l in w)), 2),
                    'weekly_pct': round(weekly_pct(sum(len(l) for l in w)), 1),
                    'lean_weekly_pct': round(weekly_pct(sum(len(l) for l in w), lean=True), 1),
                    'critical_path': [x['id'] for x in max(w, key=lambda l: sum(x['minutes'] for x in l))]})
    pct, lean_pct = sum(w['weekly_pct'] for w in out), sum(w['lean_weekly_pct'] for w in out)
    return {'items': len(items), 'lanes': len(lanes), 'waves': out, 'hours': round(sum(w['hours'] for w in out), 2),
            'lean_hours': round(sum(w['lean_hours'] for w in out), 2), 'weekly_pct': round(pct, 1), 'lean_weekly_pct': round(lean_pct, 1),
            'weekly_pct_range': None if CODEX else [round(pct * x, 1) for x in usage_range()],  # one Codex run: no spread yet
            'lean_weekly_pct_range': None if CODEX else [round(lean_pct * x, 1) for x in usage_range(True)]}


def estimate(text, with_ids=(), only=()):
    items = parse(text)
    agent_work = [i for i in items if not i['human']]
    now = [i for i in agent_work if (i['section'] == 'Ready' or i['id'] in with_ids) and (not only or i['id'] in only)]
    return {'items': items, 'ready_now': plan(now), 'everything': plan(agent_work),
            'misfiled': [i['id'] for i in items if i['section'] == 'Ready' and i['held']],
            'human': [i['id'] for i in items if i['human']], 'usage_basis': usage_basis()}


def candidates(text):
    """For each Later/Waiting item: the Ready items it shares files with, and what adding it to Ready costs."""
    items = parse(text)
    ready = [i for i in items if i['section'] == 'Ready' and not i['human']]
    base = plan(ready)
    ready_files = {}
    for r in ready:
        for f in r['files']:
            ready_files.setdefault(f, []).append(r['id'])
    out = []
    for i in items:
        if i['section'] == 'Ready':
            continue
        shares = sorted({rid for f in i['files'] for rid in ready_files.get(f, [])})
        with_it = plan(ready + [i]) if not i['human'] else base
        out.append({'id': i['id'], 'section': i['section'], 'size_minutes': i['minutes'], 'files': i['files'],
                    'shares_files_with_ready': shares, 'adds_hours': max(0.0, round(with_it['hours'] - base['hours'], 2)),  # a 3rd item on a file turns chaining into locking; never report a saving
                    'adds_lane': with_it['lanes'] > base['lanes'] and not shares, 'human': i['human'],
                    'migration': 'migration' in ' '.join(i['files']).lower() or 'migration' in i['title'].lower()})
    return {'ready_hours': base['hours'], 'ready_lanes': base['lanes'], 'max_lanes': MAX_LANES, 'candidates': out}


def fit(text, window_h, with_ids=(), without_ids=(), lean=False):
    """The most Ready items one /wave run finishes inside MARGIN of window_h hours: smallest first, and
    higher in Ready breaks ties (sorted() is stable). with_ids go in first; without_ids stay out. lean = a /wave lean run.
    ponytail: greedy, not an exact search; a small item on a long chain costs that whole chain, so it's skipped."""
    ready = [i for i in parse(text) if i['section'] == 'Ready' and not i['human']]
    unknown = sorted((set(with_ids) | set(without_ids)) - {i['id'] for i in ready})
    if unknown:
        raise ValueError('not an agent item in Ready: ' + ', '.join(unknown))
    budget = round(window_h * MARGIN, 2)
    key = 'lean_hours' if lean else 'hours'
    pick = [i for i in ready if i['id'] in with_ids]
    for i in sorted(ready, key=lambda x: x['minutes']):
        if i not in pick and i['id'] not in without_ids and plan(pick + [i])[key] <= budget:
            pick.append(i)
    pick.sort(key=ready.index)
    left = [i for i in ready if i not in pick]
    hours, left_hours, all_hours = plan(pick)[key], plan(left)[key], plan(ready)[key]
    return {'mode': 'lean' if lean else 'full', 'window_hours': window_h, 'budget_hours': budget, 'picked': [i['id'] for i in pick], 'hours': hours,
            'hours_range': None if lean else [round(hours * RANGE[0], 1), round(hours * RANGE[1], 1)], 'over_budget': hours > budget,  # no lean run measured yet
            'looks_blocked': [i['id'] for i in pick if i['held']],
            'left': [i['id'] for i in left], 'left_hours': left_hours, 'everything_fits': not left,
            'all_hours': all_hours, 'split_cost_hours': round(hours + left_hours - all_hours, 2),
            'shortest_run_hours': min((plan([i])[key] for i in ready), default=0.0)}


def promote(text, order, exempt=()):
    """/queue promote step 4: add Later items to Ready one at a time, in the given order. Skip one that makes Ready
    more than one wave (MAX_LANES lanes) or adds more than PROMOTE_SLACK_H to it, unless it's exempt."""
    items = parse(text)
    later = {i['id']: i for i in items if i['section'] == 'Later'}
    unknown = sorted((set(order) | set(exempt)) - set(later))
    if unknown:
        raise ValueError('not an item in Later: ' + ', '.join(unknown))
    ready = [i for i in items if i['section'] == 'Ready' and not i['human']]
    was = now = plan(ready)
    taken, skipped = [], []
    for x in order:
        if later[x]['human']:
            skipped.append({'id': x, 'why': 'human-only'})
            continue
        p = plan(ready + [later[x]])
        adds = max(0.0, round(p['hours'] - now['hours'], 2))
        why = None if x in exempt else 'makes Ready more than one wave' if p['lanes'] > MAX_LANES else \
            f'adds {adds}h, over {int(PROMOTE_SLACK_H * 60)} min' if adds > PROMOTE_SLACK_H else None
        if why:
            skipped.append({'id': x, 'adds_hours': adds, 'why': why})
            continue
        ready.append(later[x])
        now = p
        taken.append({'id': x, 'adds_hours': adds})
    return {'taken': taken, 'skipped': skipped, 'was_hours': was['hours'], 'usage_basis': usage_basis(),
            **{k: now[k] for k in ('items', 'lanes', 'hours', 'weekly_pct', 'weekly_pct_range', 'lean_hours', 'lean_weekly_pct', 'lean_weekly_pct_range')}}


def profile(text, only=()):
    """Per Ready task: the least model and effort that should build it, from signals in its entry.
    The overall pick is the highest tier any task needs, because every agent in a wave runs on one setting."""
    items = [i for i in parse(text) if i['section'] == 'Ready' and not i['human'] and (not only or i['id'] in only)]
    count = {}
    for it in items:
        for f in it['files']:
            count[f] = count.get(f, 0) + 1
    tasks = []
    for it in items:
        spec = ' '.join([it['title']] + re.findall(r'^- \*\*(?:Want|Done when)[^*]*\*\*:?(.*(?:\n(?!- \*\*).*)*)', it['text'], re.M))
        risk = [name for name, rx in RISK.items() if re.search(rx, spec, re.I)]
        paths = ' '.join(it['files'])  # file names are signals too: LindaChatActivities.php hides the word 'activity'
        if re.search(r'Activities|Workflow|Temporal', paths) and 'background jobs' not in risk:
            risk.append('background jobs')
        migration = any('migration' in f.lower() for f in it['files']) or 'migration' in it['title'].lower()
        hot = [f for f in it['files'] if count[f] >= 3]
        size = 'S' if it['minutes'] <= 45 else 'M' if it['minutes'] <= 75 else 'L'
        cross = it['layer'] == 'both' or len(it['files']) > 6 or size == 'L' or bool(hot)
        if risk or migration:  # 'max' is never pre-scored: only a reviewer who read the entry assigns it
            tier, why = 3, 'sensitive: ' + ', '.join(risk or ['data or database'])
        elif cross:
            tier, why = 2, 'cross-cutting: ' + ', '.join(x for x in [
                'frontend and backend' if it['layer'] == 'both' else '', f"{len(it['files'])} files" if len(it['files']) > 6 else '',
                'large' if size == 'L' else '', f"shares {len(hot)} busy file(s)" if hot else ''] if x)
        elif len(it['files']) > 3 or size == 'M':
            tier, why = 1, f"multi-file ({len(it['files'])} files), one area"
        else:
            tier, why = 0, f"small and local ({len(it['files'])} files)"
        lower = {'high': 'medium', 'extra': 'high', 'max': 'extra'}[TIERS[tier][1]]
        why_not_lower = {
            0: 'medium can cut corners on the test-first loop; every wave task must show a failing test first and survive a review that reverts the fix, which needs at least high',
            1: 'several files have to change together; high tends to stop at the first file that passes, and extra keeps checking the others before it commits',
            2: 'medium is for simple, low-stakes work; this spans ' + why.split(': ', 1)[-1] + ' and needs every caller traced, not just the one the entry names',
            3: 'high would build it; extra spends more on checking the result, which pays off here because a subtle mistake in ' + ', '.join(risk or ['data or database']) + ' misleads people or loses data without failing a test',
            4: 'extra covers one sensitive area; this is large, cross-cutting and sensitive at once, so it gets the deepest checking',
        }[tier]
        tasks.append({'id': it['id'], 'model': TIERS[tier][0], 'effort': TIERS[tier][1], 'tier': tier, 'why': why,
                      'next_lower': lower, 'why_not_lower': why_not_lower,
                      'size': size, 'files': len(it['files']), 'risk_words': risk, 'migration': migration, 'hot_files': hot})
    top = max((t['tier'] for t in tasks), default=0)
    return {'overall': {'model': TIERS[top][0], 'effort': TIERS[top][1],
                        'driven_by': [t['id'] for t in tasks if t['tier'] == top]},
            'counts': {f"{m} · {e}": sum(1 for t in tasks if (t['model'], t['effort']) == (m, e)) for m, e in TIERS},
            'tasks': tasks}


def splits(text):
    """Ready tasks on the next wave's longest chain whose own files (not shared with the rest of the chain)
    could become a separate task in its own lane. Saving = the chain's time minus the moved share of that task,
    floored at the next-longest lane. File share stands in for work share: a reviewer must confirm the split."""
    ready = [i for i in parse(text) if i['section'] == 'Ready' and not i['human']]
    if not ready:
        return {'chain': [], 'hours': 0.0, 'suggestions': []}
    lanes = lanes_of(ready)  # longest first
    chain = lanes[0]
    others = max((sum(x['minutes'] for x in l) for l in lanes[1:]), default=0)
    chain_min = sum(x['minutes'] for x in chain)
    out = []
    for it in chain:
        rest = {f for x in chain if x is not it for f in x['files']}
        own = [f for f in it['files'] if f not in rest]
        shared = [f for f in it['files'] if f in rest]
        if not own or not shared:  # nothing to peel off, or the whole task already stands alone
            continue
        moved = it['minutes'] * len(own) / len(it['files'])
        new_chain = max(chain_min - moved, others, moved)
        saved = round(LANE_FACTOR * (chain_min - new_chain) / 60, 2)
        if saved >= 0.5:
            out.append({'id': it['id'], 'split_off_files': own, 'stays_on_chain': shared, 'saves_hours': saved})
    return {'chain': [x['id'] for x in chain], 'hours': round(LANE_FACTOR * chain_min / 60, 2), 'suggestions': out}


def selftest():
    q = """# Work Queue
<!--
### AREA-1 — template, ignored
- **Touches:** a/b.ts
-->
---
## Wave protocol
### Setup
- **Touches:** not/an/item.ts
---
## Ready
### A-1 — first
- **Touches:** src/x.ts, src/x.test.ts
- **Want (M · risk 2):** thing
### A-2 — shares x with A-1
- **Touches:** src/x.ts
### B-1 — held one 🚧 BLOCKED
- **Touches:** src/y.ts
- **Notes:** waiting on Ed
## Later
### C-1 — two slices
- **Touches:** app/Z.php, app/W.php, app/V.php
- **Want:** Slice 1 (S · risk 1) then Slice 2 (L · risk 3)
## Awaiting answers
"""
    e = estimate(q)
    ids = [i['id'] for i in e['items']]
    assert ids == ['A-1', 'A-2', 'B-1', 'C-1'], ids
    by = {i['id']: i for i in e['items']}
    assert by['A-1']['minutes'] == 70 and by['A-2']['minutes'] == 45 and by['C-1']['minutes'] == 155, by
    assert e['misfiled'] == ['B-1'], e['misfiled']                 # BLOCKED in Ready: reported, still counted as Ready
    now = e['ready_now']
    assert now['items'] == 3 and now['lanes'] == 2, now          # A-1 + A-2 share src/x.ts; B-1 alone
    moved = q.replace('## Later', '## Waiting\n### W-1 — waits on legal\n- **Waiting on:** legal\n- **Touches:** src/w.ts\n## Later')
    w = estimate(moved)
    assert [i['id'] for i in w['items'] if i['section'] == 'Waiting'] == ['W-1'] and w['ready_now']['items'] == 3, w['ready_now']
    assert w['everything']['items'] == 5, w['everything']
    notes = estimate('# Q\n\n## Ready\n### N-1 — x\n- **Touches:** a/b.ts\n- **Notes:** shares a file with NARROW-2 (on hold)\n')
    assert notes['misfiled'] == [], notes['misfiled']            # a hold mentioned only in Notes is about another item
    hub = q.replace('## Later', '### D-1 — also on x\n- **Touches:** src/x.ts\n### E-1 — human\n- **Type:** chore (human)\n## Later')
    e2 = estimate(hub)
    assert e2['everything']['lanes'] == 5, e2['everything']        # A-1, A-2, D-1 all touch src/x.ts: hot, locked, not chained
    assert e2['human'] == ['E-1'] and 'E-1' not in [x for w in e2['everything']['waves'] for x in w['critical_path']]
    bundle = estimate('# Q\n\n## Later\n### F-1 — bundle\n- **Type:** bug\n- one\n- two\n- three\n- four\n')
    assert bundle['items'][0]['minutes'] == 70 and bundle['items'][0]['sized_by'] == 'sub-items', bundle['items']
    multi = estimate('# Q\n\n## Ready\n### G-1 — multi-line touches\n- **Type:** bug\n- **Touches:**\n  - resources/js/a.tsx and its test resources/js/a.test.tsx\n  - app/Http/B.php\n  - lib/c.ts\n- **Want:** x\n')
    g = multi['items'][0]
    assert g['files'] == ['app/Http/B.php', 'lib/c.ts', 'resources/js/a.test.tsx', 'resources/js/a.tsx'], g['files']
    assert g['minutes'] == 70, g
    frag = estimate('# Q\n\n## Ready\n### H-1 — x\n- **Touches:** foo.test.tsx, bar.tsx\n')
    assert frag['items'][0]['files'] == ['bar.tsx', 'foo.test.tsx'], frag['items'][0]['files']
    c = candidates(q)
    byc = {x['id']: x for x in c['candidates']}
    assert byc['C-1']['shares_files_with_ready'] == [] and abs(byc['C-1']['adds_hours'] - LANE_FACTOR * 40 / 60) < 0.015, byc['C-1']  # 155m lane outruns the 115m A lane by 40m
    slack = candidates(q.replace('- **Want:** Slice 1 (S · risk 1) then Slice 2 (L · risk 3)', '- **Want:** one small fix'))
    assert {x['id']: x for x in slack['candidates']}['C-1']['adds_hours'] == 0.0   # a 70m lane beside the 115m A lane: fits in the slack
    pair = candidates(q.replace('- **Touches:** app/Z.php, app/W.php, app/V.php', '- **Touches:** src/x.ts'))
    assert {x['id']: x for x in pair['candidates']}['C-1']['shares_files_with_ready'] == ['A-1', 'A-2']
    w = estimate(q, with_ids=['C-1'])
    assert w['ready_now']['items'] == 4, w['ready_now']
    pq = '# Q\n\n## Ready\n' + ''.join([
        '### P-1 — copy tweak\n- **Layer:** frontend\n- **Touches:** src/a.tsx\n- **Want:** reword the label\n',
        '### P-2 — multi-file ui\n- **Layer:** frontend\n- **Touches:** src/b.tsx, src/c.tsx, src/d.tsx, src/e.tsx\n- **Want:** restyle cards\n',
        '### P-3 — both layers\n- **Layer:** both\n- **Touches:** app/X.php, src/f.tsx\n- **Want:** add a field\n',
        '### P-4 — pay math\n- **Layer:** backend\n- **Touches:** app/Pay.php\n- **Want:** the commission rate rounds correctly\n',
        '### P-5 — the risk word appears only in Notes\n- **Layer:** frontend\n- **Touches:** src/g.tsx\n- **Want:** move the button\n- **Notes:** unrelated to the commission bug\n'])
    pr = profile(pq)
    t = {x['id']: (x['model'], x['effort']) for x in pr['tasks']}
    assert t == {'P-1': ('Sonnet 5', 'high'), 'P-2': ('Sonnet 5', 'extra'), 'P-3': ('Opus 5.5', 'high'),
                 'P-4': ('Opus 5.5', 'extra'), 'P-5': ('Sonnet 5', 'high')}, t
    assert pr['overall'] == {'model': 'Opus 5.5', 'effort': 'extra', 'driven_by': ['P-4']}, pr['overall']
    lows = {x['id']: x['next_lower'] for x in pr['tasks']}
    assert lows == {'P-1': 'medium', 'P-2': 'high', 'P-3': 'medium', 'P-4': 'high', 'P-5': 'medium'}, lows
    assert all(x['why_not_lower'] for x in pr['tasks'])
    bg = profile('# Q\n\n## Ready\n### R-1 — greeting timing\n- **Touches:** app/Activities/LindaChatActivities.php\n- **Want:** greet once\n')
    assert bg['tasks'][0]['effort'] == 'extra' and 'background jobs' in bg['tasks'][0]['why'], bg['tasks']
    only_small = profile('# Q\n\n## Ready\n### Q-1 — tweak\n- **Touches:** src/a.tsx\n- **Want:** x\n')
    assert only_small['overall']['model'] == 'Sonnet 5' and only_small['overall']['effort'] == 'high'
    sq = '# Q\n\n## Ready\n' + ''.join([
        '### S-1 — first\n- **Touches:** src/shared.ts\n- **Want:** x (L · risk 2)\n',
        '### S-2 — second, half its files are its own\n- **Touches:** src/shared.ts, src/own1.ts, src/own2.ts, src/own3.ts\n- **Want:** y (L · risk 2)\n',
        '### S-3 — elsewhere\n- **Touches:** src/other.ts\n- **Want:** z\n'])
    sp = splits(sq)
    assert sp['chain'] == ['S-1', 'S-2'] and len(sp['suggestions']) == 1, sp
    g = sp['suggestions'][0]
    assert g['id'] == 'S-2' and g['split_off_files'] == ['src/own1.ts', 'src/own2.ts', 'src/own3.ts'] and g['saves_hours'] == round(LANE_FACTOR * 82.5 / 60, 2), g
    for name, longest, n, actual in CALIBRATION:  # every past run lands within 35% of what it really took (docstring: why not 30)
        assert abs(run_hours(longest, n) - actual) / actual <= 0.35, (name, run_hours(longest, n), actual)
    assert RANGE[0] < 1 < RANGE[1], RANGE
    for name, longest, n, actual in CALIBRATION:  # a lean run (/wave lean) is always under the full run
        assert lean_run_hours(longest, n) < run_hours(longest, n), (name, lean_run_hours(longest, n))
    assert lean_run_hours(10, 5) == LEAN_PLAN_H + LEAN_LANE_FACTOR * 10 + LEAN_TAIL_H and lean_run_hours(1, 44) == 44 / LEAN_ITEMS_PER_H
    for name, longest, n, actual in LEAN_CALIBRATION:  # every lean run lands within 40% of what it really took
        assert abs(lean_run_hours(longest, n) - actual) / actual <= 0.40, (name, lean_run_hours(longest, n), actual)
    for p in (e['ready_now'], e['everything'], e2['everything']):
        assert 0 < p['lean_hours'] < p['hours'] and p['lean_hours'] == round(sum(w['lean_hours'] for w in p['waves']), 2), p
    fq = '# Q\n\n## Ready\n' + ''.join([
        '### F-1 — chain head\n- **Touches:** src/a.ts\n- **Want:** x (L · risk 2)\n',
        '### F-2 — on the same chain\n- **Touches:** src/a.ts\n- **Want:** x (L · risk 2)\n',
        '### F-3 — small\n- **Touches:** src/b.ts\n- **Want:** x\n',
        '### F-4 — small\n- **Touches:** src/c.ts\n- **Want:** x\n',
        '### F-5 — medium\n- **Touches:** src/d.ts\n- **Want:** x (M · risk 1)\n',
        '### F-6 — human\n- **Type:** chore (human)\n- **Touches:** src/e.ts\n'])
    h = lambda minutes, n: round(run_hours(minutes / 60, n), 2)  # windows below derive from the model, so a refit keeps them testing the same choice
    three, four, every, one = h(70, 3), h(110, 4), h(220, 5), h(45, 1)  # F-3..F-5 (the M lane is longest); plus F-1; all five; one S item
    W = (three + four) / 2 / MARGIN                                 # a budget F-3, F-4, F-5 fit in, and adding F-1 doesn't
    f = fit(fq, W)
    assert f['picked'] == ['F-3', 'F-4', 'F-5'] and f['hours'] == three, f
    assert f['hours'] <= f['budget_hours'] and f['left'] == ['F-1', 'F-2'] and not f['everything_fits'], f
    assert f['hours_range'][0] < f['hours'] < f['hours_range'][1] and not f['over_budget'], f
    assert 'F-6' not in f['picked'] + f['left'], f                  # human work is never picked
    assert f['all_hours'] == every and abs(f['split_cost_hours'] - three) < 0.01, f  # the F-1/F-2 chain sets both one run and the rest, so all of this run is extra
    big = every / MARGIN + 0.5
    assert fit(fq, big)['everything_fits'] and fit(fq, big)['left'] == [] and fit(fq, big)['split_cost_hours'] == 0, fit(fq, big)
    none = fit(fq, (one - 0.2) / MARGIN)                            # a budget under the shortest run
    assert none['picked'] == [] and none['hours'] == 0 and none['shortest_run_hours'] == one, none
    assert none['split_cost_hours'] == 0, none                      # nothing picked: no split
    forced = fit(fq, (four + 0.05) / MARGIN, with_ids=['F-2'])      # F-2 goes in, so its chain-mate F-1 can't
    assert forced['picked'] == ['F-2', 'F-3', 'F-4', 'F-5'], forced
    dropped = fit(fq, W, without_ids=['F-5'])
    assert dropped['picked'] == ['F-3', 'F-4'] and dropped['left'] == ['F-1', 'F-2', 'F-5'], dropped
    assert fit(fq, W, with_ids=['F-1', 'F-2'])['over_budget']       # a forced pair that doesn't fit says so
    lean_one = round(lean_run_hours(45 / 60, 1), 2)
    assert lean_one < one, (lean_one, one)
    LW = (lean_one + one) / 2 / MARGIN                              # no full run fits, a lean run does
    lean_fit = fit(fq, LW, lean=True)
    assert lean_fit['picked'] and lean_fit['hours'] <= lean_fit['budget_hours'] and lean_fit['hours_range'] is None and lean_fit['mode'] == 'lean', lean_fit
    assert not fit(fq, LW)['picked'] and fit(fq, LW)['mode'] == 'full' and lean_fit['shortest_run_hours'] < none['shortest_run_hours'], lean_fit
    try:
        fit(fq, W, with_ids=['F-9'])
        raise AssertionError('an unknown ID must be refused')
    except ValueError:
        pass
    tq = '# Q\n\n## Ready\n### T-1 — x\n- **Touches:** src/p.ts, src/s.ts\n- **Want:** x (M · risk 1)\n### T-2 — y\n- **Touches:** src/q.ts, src/s.ts\n- **Want:** y (M · risk 1)\n'
    TW = (h(70, 1) + h(140, 2)) / 2 / MARGIN                       # one M fits, the two-M chain doesn't
    assert fit(tq, TW)['picked'] == ['T-1'], fit(tq, TW)            # same size, one chain: higher in Ready wins
    swapped = tq.replace('### T-1', '### T-X').replace('### T-2', '### T-1').replace('### T-X', '### T-2')
    assert fit(swapped, TW)['picked'] == ['T-2'] and fit(swapped, TW)['left'] == ['T-1'], fit(swapped, TW)
    oq = '# Q\n\n## Ready\n' + ''.join([
        '### E — medium, own file\n- **Touches:** src/e.ts\n- **Want:** x (M · risk 1)\n',
        '### B — big, joins C and D into one chain\n- **Touches:** src/s1.ts, src/s2.ts\n- **Want:** x (L · risk 2)\n',
        '### C — small\n- **Touches:** src/s1.ts\n',
        '### D — small\n- **Touches:** src/s2.ts\n'])
    OW = (h(110, 1) + h(200, 4)) / 2 / MARGIN                      # B alone fits; B chained with C and D doesn't
    assert fit(oq, OW)['picked'] == ['E', 'C', 'D'], fit(oq, OW)    # taking B first would cost C and D; output in Ready order
    hq = '# Q\n\n## Ready\n### H-1 — x 🚧 BLOCKED\n- **Touches:** src/h.ts\n### H-2 — y\n- **Touches:** src/i.ts\n'
    assert fit(hq, 7)['looks_blocked'] == ['H-1'] and fit(hq, 7)['picked'] == ['H-1', 'H-2'], fit(hq, 7)  # flagged for a read, still picked
    many = '# Q\n\n## Ready\n' + ''.join(f'### K-{n} — x\n- **Touches:** src/k{n}.ts\n' for n in range(20))
    assert len(fit(many, 7)['picked']) == 14, fit(many, 7)          # 20 one-file fixes, no shared files: 14 items is 5.6h at 2.5 an hour
    assert len(fit(many, 7.5)['picked']) == 15, fit(many, 7.5)      # 15 lanes still make one wave (MAX_LANES 21)
    mq = '# Q\n\n## Ready\n### A-1 — x\n- **Touches:** src/a.ts\n- **Want:** x (M · risk 1)\n## Later\n' + ''.join([
        '### L-1 — small, own file\n- **Touches:** src/l1.ts\n',
        '### L-2 — extra large, own file\n- **Touches:** src/l2.ts\n- **Want:** x (XL · risk 2)\n',
        '### L-3 — extra large, exempt\n- **Touches:** src/l3.ts\n- **Want:** x (XL · risk 2)\n',
        '### L-4 — human\n- **Type:** chore (human)\n- **Touches:** src/l4.ts\n'])
    m = promote(mq, ['L-1', 'L-2', 'L-3', 'L-4'], exempt=['L-3'])
    adds = round(h(180, 3) - h(70, 2), 2)                           # an XL lane outruns A-1's 70m
    assert adds > PROMOTE_SLACK_H and m['taken'] == [{'id': 'L-1', 'adds_hours': 0.0}, {'id': 'L-3', 'adds_hours': adds}], m  # L-1 fits in the slack
    assert [(x['id'], x.get('adds_hours')) for x in m['skipped']] == [('L-2', adds), ('L-4', None)], m  # L-2 is the same size, but not exempt
    assert m['was_hours'] == h(70, 1) and m['hours'] == h(180, 3) and m['items'] == 3 and 0 < m['lean_hours'] < m['hours'], m
    assert m['weekly_pct_range'][0] < m['weekly_pct'] < m['weekly_pct_range'][1], m
    wide = '# Q\n\n## Ready\n' + ''.join(f'### K-{n} — x\n- **Touches:** src/k{n}.ts\n' for n in range(21)) + '## Later\n### M-1 — x\n- **Touches:** src/m.ts\n'
    assert promote(wide, ['M-1'])['skipped'][0]['why'] == 'makes Ready more than one wave', promote(wide, ['M-1'])  # a 22nd lane
    assert promote(wide, ['M-1'], exempt=['M-1'])['taken'][0]['id'] == 'M-1'
    for bad in (['K-1'], ['Z-9']):  # a Ready item or an unknown ID is refused
        try:
            promote(wide, bad)
            raise AssertionError('promote must refuse ' + bad[0])
        except ValueError:
            pass
    po = profile(pq, only=['P-1', 'P-4'])
    assert [x['id'] for x in po['tasks']] == ['P-1', 'P-4'] and po['overall']['driven_by'] == ['P-4'], po
    assert 0 < e['ready_now']['lean_weekly_pct'] < e['ready_now']['weekly_pct'], e['ready_now']
    assert plan([])['weekly_pct'] == 0 and 'Claude' in estimate('')['usage_basis']
    global CODEX
    CODEX = True  # Codex prices from its own run, never Claude's
    assert round(weekly_pct(10), 1) == 72.0 and 'Codex' in estimate('')['usage_basis'], weekly_pct(10)
    CODEX = False
    for name, n, u, dollars, ln in UNIT_CALIBRATION:  # from its unit count, every ledger lands within 30% of its run's real cost
        assert abs(unit_dollars(u, ln) - dollars) / dollars <= 0.30, (name, unit_dollars(u, ln), dollars)
        lo, hi = (weekly_pct(n, ln) * x * DOLLARS_PER_WEEKLY_POINT for x in usage_range(ln))
        assert lo - 0.5 <= dollars <= hi + 0.5, (name, lo, hi, dollars)  # from its item count, inside promote's range
    big, small = unit_usage(54), unit_usage(10)
    assert big['weekly_pct_range'][0] < big['weekly_pct'] < big['weekly_pct_range'][1], big
    assert big['dollars'] / 54 > small['dollars'] / 10, (big, small)  # a big run costs more a unit: more journeys and close-outs
    assert unit_usage(54, lean=True)['weekly_pct'] < big['weekly_pct']
    CODEX = True
    assert unit_usage(33, lean=True)['weekly_pct'] == 54.0 and unit_usage(33)['weekly_pct'] > 54, unit_usage(33)
    CODEX = False
    print('selftest ok')


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        selftest()
        sys.exit(0)
    if '--units' in sys.argv:  # needs no queue file
        CODEX = '--codex' in sys.argv
        print(json.dumps(unit_usage(int(sys.argv[sys.argv.index('--units') + 1]), '--lean' in sys.argv), indent=1))
        sys.exit(0)
    if not sys.argv[1:]:
        print(__doc__)
        sys.exit(2)
    text = open(sys.argv[1], encoding='utf-8').read()
    CODEX = '--codex' in sys.argv

    def ids(flag):
        value = sys.argv[sys.argv.index(flag) + 1:][:1] if flag in sys.argv else []
        return [x.strip() for x in value[0].split(',') if x.strip()] if value and not value[0].startswith('--') else []
    if '--fit' in sys.argv:
        try:
            print(json.dumps(fit(text, float(sys.argv[sys.argv.index('--fit') + 1]), ids('--with'), ids('--without'), '--lean' in sys.argv), ensure_ascii=False, indent=1))
        except ValueError as err:
            sys.exit(f'estimate.py: {err}')
        sys.exit(0)
    if '--promote' in sys.argv:
        try:
            print(json.dumps(promote(text, ids('--promote'), ids('--exempt')), ensure_ascii=False, indent=1))
        except ValueError as err:
            sys.exit(f'estimate.py: {err}')
        sys.exit(0)
    if '--profile' in sys.argv:
        print(json.dumps(profile(text, ids('--only')), ensure_ascii=False, indent=1))
        sys.exit(0)
    if '--splits' in sys.argv:
        print(json.dumps(splits(text), ensure_ascii=False, indent=1))
        sys.exit(0)
    if '--candidates' in sys.argv:
        print(json.dumps(candidates(text), ensure_ascii=False, indent=1))
        sys.exit(0)
    result = estimate(text, ids('--with'), ids('--only'))
    if '--json' in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        for i in result['items']:
            tag = 'HUMAN' if i['human'] else 'HELD ' if i['held'] else '     '
            print(f"{i['section']:7}  {i['id']:18} {i['minutes']:4}m  {tag} {len(i['files'])} files  {i['title'][:70]}")
        print(f"\nweekly usage from {result['usage_basis']}")
        for k in ('ready_now', 'everything'):
            p = result[k]
            rng = lambda r: f" ({r[0]}-{r[1]}%)" if r else ''
            print(f"\n{k}: {p['items']} items, {p['lanes']} lanes, {len(p['waves'])} wave(s), about {p['hours']}h full (~{p['weekly_pct']}% weekly{rng(p['weekly_pct_range'])}) · about {p['lean_hours']}h lean (~{p['lean_weekly_pct']}% weekly{rng(p['lean_weekly_pct_range'])})")
            for n, w in enumerate(p['waves'], 1):
                print(f"  wave {n}: {w['items']} items in {w['lanes']} lanes, longest lane {w['longest_lane_h']}h, about {w['hours']}h full · {w['lean_hours']}h lean; critical path {' -> '.join(w['critical_path'])}")
