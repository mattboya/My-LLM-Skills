#!/usr/bin/env python3
"""Estimate how long a WORK_QUEUE.md takes to finish in parallel /wave runs.

Usage: estimate.py <path/to/WORK_QUEUE.md> [--json] [--with ID,ID]
       estimate.py <path/to/WORK_QUEUE.md> --candidates     (JSON: each Later/Waiting item vs Ready)
       estimate.py <path/to/WORK_QUEUE.md> --promote ID,ID [--exempt ID,ID]  (JSON: which Later items fit the next wave, added in that order)
       estimate.py <path/to/WORK_QUEUE.md> --profile [--only ID,ID]  (JSON: the model and effort each Ready task needs)
       estimate.py <path/to/WORK_QUEUE.md> --splits         (JSON: Ready tasks on the longest chain that could split to finish sooner)
       estimate.py <path/to/WORK_QUEUE.md> --fit HOURS [--lean] [--with ID,ID] [--without ID,ID]
                                                            (JSON: the most Ready items one run finishes in HOURS)
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

ponytail: run_hours() is fit to the five runs in CALIBRATION (2026-09-30, from each wave doc's
Results plus its transcript times). Measured phases: planning to the first lane about 40 min; the
lanes 0.35-0.54 of the longest chain's summed minutes (the planner cuts items into finer units and
more lanes than file-sharing does); after the last lane 3-6h (journeys, close-outs, gates, about
50 min of handoff). None of the five was a short run, so short-run estimates are extrapolated.
Re-fit after new Results: add the run to CALIBRATION; selftest keeps every row within 30%.

ponytail: lean_run_hours() (/wave lean: test-first builders, one final-gates run, no reviews) is fit to TWO runs
(LEAN_CALIBRATION: 2026-10-02 3.9h for 16 items on a 6.7h chain; 2026-10-03 2.3h for 12 items on an 8.3h chain).
The chain barely predicts a lean run (the planner splits lanes finer than file-sharing does), so the fit is mostly
fixed cost: about 2.3-2.9h either way. A third lean run (2026-10-05: 70 items, 7.7h, 92.8h chain) lands within 26% without a refit; its planning took 2.4h, so LEAN_PLAN_H under-reads big waves (planning scales with items) while LEAN_LANE_FACTOR over-reads a huge chain. Refit both once a fourth run shows the pattern. Before that it was a model: in wave 2026-10-01 (2) building was about a quarter of each unit's lane time (builders 28 min
vs reviews 77 min a unit), so its lanes take ~0.10 of the chain, and the 3-6h back half becomes final
gates + a smaller handoff (~1h). Calibrate it the same way once a lean run's Results say `Mode: lean`.

ponytail: weekly_pct() (the share of a week's usage limit one run takes) is a line through the three Claude runs
in USAGE_CALIBRATION (dollars from wave-cost.py), so a run costs about $75 before its first item and $4 an item:
planning, journeys and gates dominate. Points are DOLLARS_PER_WEEKLY_POINT, measured once on Matt's plan; another
plan needs its own (read /usage before and after a run). Lean has no ledger yet: LEAN_USAGE is wave/SKILL.md's
"about a third". Re-fit after new Results: add the run to USAGE_CALIBRATION; selftest keeps every row within 30%.

ponytail: --codex prices from CODEX_RUN_PCT instead. Codex logs the weekly percent itself, and wave/helpers/
codex-usage.py reads it for a run. The one data point so far is a paused lean run: 2026-10-07 (friendslop-game,
Matt's ChatGPT Pro Lite plan) built 33 of its 57 units (37 items, so about 21 items' worth) for 54% of the week.
That is about 2.5% an item lean, 7.2% full by LEAN_USAGE, with no fixed part (one run can't separate it). Claude's
line would have said 2%: never borrow across providers. Re-fit once a finished Codex run's Results give its percent.
"""
import json
import re
import sys

MINUTES = {'XS': 30, 'S': 45, 'M': 70, 'L': 110, 'XL': 180}
PLAN_H = 0.65          # typing /wave to the first lane: planning checks, the go/no-go, Wave 0
LANE_FACTOR = 0.42     # the lanes phase, as a share of the longest chain's summed minutes
TAIL_H = 4.2           # after the last lane: journeys, close-outs, final gates, handoff
ITEMS_PER_H = 2.5      # the fastest whole-run pace yet (25 items in 10.2h): parallel lanes aren't free
LEAN_PLAN_H = 1.0      # lean, typing /wave lean to the first lane: the planning check is the only adversarial look,
                       # so checkers reproduce and prototype every bullet (60 min on 2026-10-02, 41 on 2026-10-03) plus go and tickets
LEAN_LANE_FACTOR = 0.08  # lean lanes, as a share of the longest chain: 1h26m on a 6.7h chain (10-02), 53m on 8.3h (10-03)
LEAN_TAIL_H = 1.25     # lean, after the last lane: final gates (11 min), the CI-faithful run, any gate fix, handoff (~25-60 min)
LEAN_ITEMS_PER_H = 11  # ITEMS_PER_H with reviews removed (~2 units an item, 16 builders at once)
DOLLARS_PER_WEEKLY_POINT = 29  # wave-cost.py's: measured 2026-10-03 on Opus 5.5 and Matt's plan
RUN_DOLLARS = (75, 3.9)        # a full run's API-list dollars: fixed, then per item (fit to USAGE_CALIBRATION)
LEAN_USAGE = 0.35              # a lean run's share of a full run's usage (modelled: wave/SKILL.md, no lean ledger yet)
CODEX_RUN_PCT = (0, 7.2)       # (weekly % fixed, weekly % an item) for a full Codex run: one paused lean run (docstring)
USAGE_CALIBRATION = [          # (wave, items, $ from its .cost.md ledger)
    ('2026-10-03 fun-loop', 9, 121),   # its Results: weekly usage 91% -> 95%, the ledger said ~4 points
    ('2026-10-08 jsonify', 4, 89),
    ('2026-10-08 soulseek-auto', 10, 105),
]
CODEX = False                  # ponytail: set from --codex in main; a parameter through every caller if it ever matters
MAX_LANES = 21         # the most lanes a wave has run at once (16 agents at a time)
MARGIN = 0.8           # /queue fit plans to this share of the window (Matt, 2026-09-30)
PROMOTE_SLACK_H = 0.25  # /queue promote: the most an item may add to the next wave without an exempt reason
CALIBRATION = [        # (wave, longest lane h by this script on its .queue.md snapshot, items, actual h)
    ('2026-09-25', 6.75, 17, 7.5),
    ('2026-09-27', 6.67, 8, 7.3),
    ('2026-09-28', 7.33, 14, 6.3),
    ('2026-09-28 (2)', 9.67, 25, 10.2),  # 48-min usage pause excluded
    ('2026-09-29', 7.33, 8, 10.6),
]
LEAN_CALIBRATION = [   # the same shape, for /wave lean runs
    ('2026-10-02 (lean)', 6.7, 16, 3.9),
    ('2026-10-03 (lean)', 8.33, 12, 2.3),
    ('2026-10-05 (lean)', 92.83, 70, 7.7),  # 70 items, 108 units; planning 2.4h (26 checkers), builders 3.7h, gates 27 min, handoff ~40 min
]


def run_hours(longest_lane_h, items):
    """Typing /wave to handoff for one wave: its longest chain, or its item count at the best pace seen, whichever is longer."""
    return max(PLAN_H + LANE_FACTOR * longest_lane_h + TAIL_H, items / ITEMS_PER_H)


def lean_run_hours(longest_lane_h, items):
    """Typing /wave lean to handoff: planning, building the longest chain, final gates and handoff (one calibration run)."""
    return max(LEAN_PLAN_H + LEAN_LANE_FACTOR * longest_lane_h + LEAN_TAIL_H, items / LEAN_ITEMS_PER_H)


def weekly_pct(items, lean=False):
    """One run's share of the weekly usage limit, in percent."""
    fixed, per = CODEX_RUN_PCT if CODEX else [d / DOLLARS_PER_WEEKLY_POINT for d in RUN_DOLLARS]
    return (fixed + per * items) * (LEAN_USAGE if lean else 1)


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
        return {'items': 0, 'lanes': 0, 'waves': [], 'hours': 0.0, 'lean_hours': 0.0, 'weekly_pct': 0.0, 'lean_weekly_pct': 0.0}
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
    return {'items': len(items), 'lanes': len(lanes), 'waves': out, 'hours': round(sum(w['hours'] for w in out), 2),
            'lean_hours': round(sum(w['lean_hours'] for w in out), 2),
            'weekly_pct': round(sum(w['weekly_pct'] for w in out), 1), 'lean_weekly_pct': round(sum(w['lean_weekly_pct'] for w in out), 1)}


def estimate(text, with_ids=()):
    items = parse(text)
    agent_work = [i for i in items if not i['human']]
    now = [i for i in agent_work if i['section'] == 'Ready' or i['id'] in with_ids]
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
            **{k: now[k] for k in ('items', 'lanes', 'hours', 'weekly_pct', 'lean_hours', 'lean_weekly_pct')}}


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
    assert byc['C-1']['shares_files_with_ready'] == [] and abs(byc['C-1']['adds_hours'] - 0.28) < 0.02, byc['C-1']  # 155m lane outruns the 115m A lane by 40m; lanes run at 0.42
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
    for name, longest, n, actual in CALIBRATION:  # every past run lands within 30% of what it really took
        assert abs(run_hours(longest, n) - actual) / actual <= 0.30, (name, run_hours(longest, n), actual)
    assert RANGE[0] < 1 < RANGE[1], RANGE
    for name, longest, n, actual in CALIBRATION:  # a lean run (/wave lean) is always well under the full run
        assert lean_run_hours(longest, n) < 0.5 * run_hours(longest, n), (name, lean_run_hours(longest, n))
    assert lean_run_hours(10, 5) == LEAN_PLAN_H + LEAN_LANE_FACTOR * 10 + LEAN_TAIL_H and lean_run_hours(1, 44) == 44 / LEAN_ITEMS_PER_H
    for name, longest, n, actual in LEAN_CALIBRATION:  # every lean run lands within 30% of what it really took
        assert abs(lean_run_hours(longest, n) - actual) / actual <= 0.30, (name, lean_run_hours(longest, n), actual)
    for p in (e['ready_now'], e['everything'], e2['everything']):
        assert 0 < p['lean_hours'] < p['hours'] and p['lean_hours'] == round(sum(w['lean_hours'] for w in p['waves']), 2), p
    fq = '# Q\n\n## Ready\n' + ''.join([
        '### F-1 — chain head\n- **Touches:** src/a.ts\n- **Want:** x (L · risk 2)\n',
        '### F-2 — on the same chain\n- **Touches:** src/a.ts\n- **Want:** x (L · risk 2)\n',
        '### F-3 — small\n- **Touches:** src/b.ts\n- **Want:** x\n',
        '### F-4 — small\n- **Touches:** src/c.ts\n- **Want:** x\n',
        '### F-5 — medium\n- **Touches:** src/d.ts\n- **Want:** x (M · risk 1)\n',
        '### F-6 — human\n- **Type:** chore (human)\n- **Touches:** src/e.ts\n'])
    f = fit(fq, 7)  # budget 5.6h: F-3, F-4, F-5 fit (5.34h); F-1 alone makes the chain 110m (5.62h)
    assert f['budget_hours'] == 5.6 and f['picked'] == ['F-3', 'F-4', 'F-5'], f
    assert f['hours'] <= f['budget_hours'] and f['left'] == ['F-1', 'F-2'] and not f['everything_fits'], f
    assert f['hours_range'][0] < f['hours'] < f['hours_range'][1] and not f['over_budget'], f
    assert 'F-6' not in f['picked'] + f['left'], f                  # human work is never picked
    assert f['all_hours'] == 6.39 and abs(f['split_cost_hours'] - 5.34) < 0.01, f  # the F-1/F-2 chain sets both one run and the rest, so all 5.34h is extra
    assert fit(fq, 9)['everything_fits'] and fit(fq, 9)['left'] == [] and fit(fq, 9)['split_cost_hours'] == 0, fit(fq, 9)
    none = fit(fq, 6)                                               # budget 4.8h, under the 5.17h shortest run
    assert none['picked'] == [] and none['hours'] == 0 and abs(none['shortest_run_hours'] - 5.17) < 0.02, none
    assert none['split_cost_hours'] == 0, none                      # nothing picked: no split
    forced = fit(fq, 7.1, with_ids=['F-2'])                         # F-2 goes in, so its chain-mate F-1 can't
    assert forced['picked'] == ['F-2', 'F-3', 'F-4', 'F-5'], forced
    dropped = fit(fq, 7, without_ids=['F-5'])
    assert dropped['picked'] == ['F-3', 'F-4'] and dropped['left'] == ['F-1', 'F-2', 'F-5'], dropped
    assert fit(fq, 7, with_ids=['F-1', 'F-2'])['over_budget']       # a forced pair that doesn't fit says so
    lean_fit = fit(fq, 4, lean=True)                                # 3.2h budget: no full run fits, a lean run does
    assert lean_fit['picked'] and lean_fit['hours'] <= lean_fit['budget_hours'] and lean_fit['hours_range'] is None and lean_fit['mode'] == 'lean', lean_fit
    assert not fit(fq, 4)['picked'] and fit(fq, 4)['mode'] == 'full' and lean_fit['shortest_run_hours'] < none['shortest_run_hours'], lean_fit
    try:
        fit(fq, 7, with_ids=['F-9'])
        raise AssertionError('an unknown ID must be refused')
    except ValueError:
        pass
    tq = '# Q\n\n## Ready\n### T-1 — x\n- **Touches:** src/p.ts, src/s.ts\n- **Want:** x (M · risk 1)\n### T-2 — y\n- **Touches:** src/q.ts, src/s.ts\n- **Want:** y (M · risk 1)\n'
    assert fit(tq, 7)['picked'] == ['T-1'], fit(tq, 7)              # same size, one chain: higher in Ready wins
    swapped = tq.replace('### T-1', '### T-X').replace('### T-2', '### T-1').replace('### T-X', '### T-2')
    assert fit(swapped, 7)['picked'] == ['T-2'] and fit(swapped, 7)['left'] == ['T-1'], fit(swapped, 7)
    oq = '# Q\n\n## Ready\n' + ''.join([
        '### E — medium, own file\n- **Touches:** src/e.ts\n- **Want:** x (M · risk 1)\n',
        '### B — big, joins C and D into one chain\n- **Touches:** src/s1.ts, src/s2.ts\n- **Want:** x (L · risk 2)\n',
        '### C — small\n- **Touches:** src/s1.ts\n',
        '### D — small\n- **Touches:** src/s2.ts\n'])
    assert fit(oq, 7.2)['picked'] == ['E', 'C', 'D'], fit(oq, 7.2)  # B alone fits, but taking it first would cost C and D; output in Ready order
    hq = '# Q\n\n## Ready\n### H-1 — x 🚧 BLOCKED\n- **Touches:** src/h.ts\n### H-2 — y\n- **Touches:** src/i.ts\n'
    assert fit(hq, 7)['looks_blocked'] == ['H-1'] and fit(hq, 7)['picked'] == ['H-1', 'H-2'], fit(hq, 7)  # flagged for a read, still picked
    many = '# Q\n\n## Ready\n' + ''.join(f'### K-{n} — x\n- **Touches:** src/k{n}.ts\n' for n in range(20))
    assert len(fit(many, 7)['picked']) == 14, fit(many, 7)          # 20 one-file fixes, no shared files: 14 items is 5.6h at 2.5 an hour
    assert len(fit(many, 7.5)['picked']) == 15, fit(many, 7.5)      # 15 lanes still make one wave (MAX_LANES 21)
    mq = '# Q\n\n## Ready\n### A-1 — x\n- **Touches:** src/a.ts\n- **Want:** x (M · risk 1)\n## Later\n' + ''.join([
        '### L-1 — small, own file\n- **Touches:** src/l1.ts\n',
        '### L-2 — large, own file\n- **Touches:** src/l2.ts\n- **Want:** x (L · risk 2)\n',
        '### L-3 — large, exempt\n- **Touches:** src/l3.ts\n- **Want:** x (L · risk 2)\n',
        '### L-4 — human\n- **Type:** chore (human)\n- **Touches:** src/l4.ts\n'])
    m = promote(mq, ['L-1', 'L-2', 'L-3', 'L-4'], exempt=['L-3'])
    assert m['taken'] == [{'id': 'L-1', 'adds_hours': 0.0}, {'id': 'L-3', 'adds_hours': 0.28}], m  # L-1 fits in the slack; L-3's 110m lane outruns A-1's 70m
    assert [(x['id'], x.get('adds_hours')) for x in m['skipped']] == [('L-2', 0.28), ('L-4', None)], m  # L-2 is the same size, but not exempt
    assert m['was_hours'] == 5.34 and m['hours'] == 5.62 and m['items'] == 3 and 0 < m['lean_hours'] < m['hours'], m
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
    for name, n, dollars in USAGE_CALIBRATION:  # every measured run lands within 30% of what it really used
        assert abs(weekly_pct(n) - dollars / DOLLARS_PER_WEEKLY_POINT) / (dollars / DOLLARS_PER_WEEKLY_POINT) <= 0.30, (name, weekly_pct(n))
    assert 0 < e['ready_now']['lean_weekly_pct'] < e['ready_now']['weekly_pct'], e['ready_now']
    assert plan([])['weekly_pct'] == 0 and 'Claude' in estimate('')['usage_basis']
    global CODEX
    CODEX = True  # Codex prices from its own run, never Claude's
    assert round(weekly_pct(10), 1) == 72.0 and 'Codex' in estimate('')['usage_basis'], weekly_pct(10)
    CODEX = False
    print('selftest ok')


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        selftest()
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
    result = estimate(text, ids('--with'))
    if '--json' in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        for i in result['items']:
            tag = 'HUMAN' if i['human'] else 'HELD ' if i['held'] else '     '
            print(f"{i['section']:7}  {i['id']:18} {i['minutes']:4}m  {tag} {len(i['files'])} files  {i['title'][:70]}")
        print(f"\nweekly usage from {result['usage_basis']}")
        for k in ('ready_now', 'everything'):
            p = result[k]
            print(f"\n{k}: {p['items']} items, {p['lanes']} lanes, {len(p['waves'])} wave(s), about {p['hours']}h full (~{p['weekly_pct']}% weekly) · about {p['lean_hours']}h lean (~{p['lean_weekly_pct']}% weekly)")
            for n, w in enumerate(p['waves'], 1):
                print(f"  wave {n}: {w['items']} items in {w['lanes']} lanes, longest lane {w['longest_lane_h']}h, about {w['hours']}h full · {w['lean_hours']}h lean; critical path {' -> '.join(w['critical_path'])}")
