#!/usr/bin/env python3
"""What a /wave run cost and where its time went, from the session's own transcripts.

Usage: wave-cost.py --session <id> [--project-dir DIR] [--prev LAST.cost.md] [--ledger OUT.cost.md]
  --session      the run's session id (the UUID in the run's scratchpad path)
  --project-dir  ~/.claude/projects/<slug>; default: derived from the current directory
  --prev         the previous run's ledger: adds a change column and flags roles that got dearer
  --ledger       write this report plus its numbers (a json block) for the next run to compare against;
                 name it <wave doc stem>.cost.md so the wave-doc ignore pattern covers it

Dollars are API list prices (cache reads included), so they compare runs and roles; they are not a bill.
A role is an agent label's first word (impl, review, journey, plan, handoff...). Per unit = per builder.
"""
import argparse, glob, json, os, re
from collections import defaultdict
from datetime import datetime, timedelta

# $ per million tokens: input, output, cache read. Cache writes: 1.25x input (5 min), 2x input (1 h).
PRICES = {'opus-5-5': (4, 20, 0.20), 'sonnet-5-5': (2, 10, 0.20), 'sonnet-5': (2, 10, 0.20), 'fable-5-1': (10, 50, 0.25),
          'opus-5': (5, 25, 0.50), 'haiku-4-5': (1, 5, 0.10)}
DOLLARS_PER_WEEKLY_POINT = 29   # measured 2026-10-03 on Opus 5.5; re-measure if the kick-off model changes
FLAG_RISE = 0.30                # a role whose $/unit rose more than this...
FLAG_MIN = 0.50                 # ...and by at least this many dollars a unit gets flagged
                                # (only between runs of 10+ units: small runs read high per unit, their fixed costs dominate)


def ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def price(model):
    for key, p in PRICES.items():
        if key in (model or ''):
            return p
    return PRICES['opus-5-5']


def scan(path):
    seen, times, first_ctx = {}, [], None
    for line in open(path):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get('timestamp'):
            times.append(ts(e['timestamp']))
        m = e.get('message') or {}
        if e.get('type') == 'assistant' and isinstance(m, dict) and m.get('usage') and m.get('id'):
            seen[m['id']] = (m['usage'], m.get('model', ''))
    cost = 0.0
    for i, (u, model) in enumerate(seen.values()):
        pin, pout, pread = price(model)
        cc = u.get('cache_creation') or {}
        w5, w1 = cc.get('ephemeral_5m_input_tokens'), cc.get('ephemeral_1h_input_tokens')
        if w5 is None and w1 is None:
            w5, w1 = u.get('cache_creation_input_tokens', 0), 0
        cost += (u.get('input_tokens', 0) * pin + u.get('output_tokens', 0) * pout + u.get('cache_read_input_tokens', 0) * pread
                 + (w5 or 0) * pin * 1.25 + (w1 or 0) * pin * 2) / 1e6
        if i == 0:
            first_ctx = u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0) + u.get('cache_creation_input_tokens', 0)
    return {'cost': cost, 'turns': len(seen), 'start': min(times) if times else None, 'end': max(times) if times else None, 'ctx0': first_ctx or 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--session', required=True)
    ap.add_argument('--project-dir', default=os.path.expanduser('~/.claude/projects/') + re.sub(r'[^A-Za-z0-9]', '-', os.getcwd()))
    ap.add_argument('--prev')
    ap.add_argument('--ledger')
    a = ap.parse_args()
    sd = os.path.join(a.project_dir, a.session)
    main_s = scan(sd + '.jsonl')
    agents, flows = [], defaultdict(list)
    for meta in glob.glob(os.path.join(sd, 'subagents', '**', '*.meta.json'), recursive=True):
        j = meta[:-len('.meta.json')] + '.jsonl'
        if not os.path.exists(j):
            continue
        label = json.load(open(meta)).get('description', '')
        r = scan(j)
        r['label'], r['role'] = label, re.split(r'[:\s]', label)[0] or '?'
        agents.append(r)
        flows[os.path.basename(os.path.dirname(meta))].append(r)
    units = sum(1 for r in agents if r['role'] == 'impl') or 1
    total = main_s['cost'] + sum(r['cost'] for r in agents)
    roles = defaultdict(lambda: {'n': 0, 'cost': 0.0, 'mins': 0.0, 'turns': 0, 'ctx0': 0})
    roles['main session'] = {'n': 1, 'cost': main_s['cost'], 'mins': 0.0, 'turns': main_s['turns'], 'ctx0': main_s['ctx0']}
    for r in agents:
        b = roles[r['role']]
        b['n'] += 1; b['cost'] += r['cost']; b['turns'] += r['turns']; b['ctx0'] += r['ctx0']
        if r['start']:
            b['mins'] += (r['end'] - r['start']).total_seconds() / 60
    prev = json.loads(open(a.prev).read().split('```json\n')[1].split('\n```')[0]) if a.prev else None
    out = []

    out.append(f'**Run cost:** about ${total:.0f} at API list prices (≈ {total / DOLLARS_PER_WEEKLY_POINT:.0f} weekly points), '
          f'{units} units, ${total / units:.1f} a unit, {len(agents)} agents.' +
          (f' Last run: ${prev["perUnit"]:.1f} a unit.' if prev else ''))
    out.append('')
    head = '| Role | Agents | $ | Share | $ a unit | Minutes an agent | Turns an agent | Start context (k tokens) |' + (' $ a unit last run |' if prev else '')
    out.append(head)
    out.append('|' + '|'.join(['---'] * (head.count('|') - 1)) + '|')
    flags = []
    for k, b in sorted(roles.items(), key=lambda x: -x[1]['cost']):
        n = b['n']
        mins = '—' if k == 'main session' else f"{b['mins'] / n:.1f}"
        row = f"| {k} | {n} | {b['cost']:.0f} | {100 * b['cost'] / total:.0f}% | {b['cost'] / units:.2f} | {mins} | {b['turns'] / n:.0f} | {b['ctx0'] / n / 1000:.0f} |"
        if prev:
            was = (prev['roles'].get(k) or {}).get('perUnit')
            row += f" {was:.2f} |" if was is not None else ' new |'
            now = b['cost'] / units
            if was is not None and k != 'main session' and min(units, prev['units']) >= 10 and now > was * (1 + FLAG_RISE) and now - was >= FLAG_MIN:
                flags.append(f'{k}: ${was:.2f} → ${now:.2f} a unit')
        out.append(row)
    out.append('')
    for name, rs in sorted(flows.items(), key=lambda x: min(r['start'] for r in x[1] if r['start'])):
        rs = [r for r in rs if r['start']]
        st, en = min(r['start'] for r in rs), max(r['end'] for r in rs)
        conc, t = [], st
        while t < en:
            conc.append(sum(1 for r in rs if r['start'] <= t < r['end']))
            t += timedelta(minutes=1)
        kinds = ', '.join(sorted({r['role'] for r in rs}))
        tail = sorted(rs, key=lambda r: r['end'])[-3:]
        out.append(f"- {kinds}: {(en - st).total_seconds() / 60:.0f} min, {len(rs)} agents, at most {max(conc or [0])} at once; "
              f"last to finish: {', '.join(r['label'] + ' ' + str(round((r['end'] - r['start']).total_seconds() / 60)) + ' min' for r in tail)}")
    if flags:
        out.append('')
        out.append('**Got dearer since the last run:** ' + '; '.join(flags))
    print('\n'.join(out))
    if a.ledger:
        numbers = {'session': a.session, 'total': total, 'units': units, 'perUnit': total / units, 'agents': len(agents),
                   'roles': {k: {'n': b['n'], 'cost': b['cost'], 'perUnit': b['cost'] / units} for k, b in roles.items()}}
        open(a.ledger, 'w').write('\n'.join(out) + '\n\n```json\n' + json.dumps(numbers, indent=1) + '\n```\n')


if __name__ == '__main__':
    main()
