// Run: node ~/.agents/skills/wave/codex-host.check.mjs  (a stub codex; proves the host after any edit)
import { mkdtempSync, writeFileSync, readFileSync, chmodSync, existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HOST = fileURLToPath(new URL('./codex-host.mjs', import.meta.url))   // .pathname would keep [ ] as %5B %5D
const T = mkdtempSync(join(tmpdir(), 'codex-host-check-'))
const repo = join(T, 'repo'), sp = join(T, 'sp')
spawnSync('git', ['init', '-q', repo]); spawnSync('mkdir', ['-p', sp])

// Stub codex: logs its argv and lifetime, answers by the LABEL= in its prompt.
writeFileSync(join(T, 'codex'), `#!/usr/bin/env node
const fs = require('fs'), a = process.argv.slice(2), at = f => a[a.indexOf(f) + 1]
const prompt = fs.readFileSync(0, 'utf8'), label = prompt.match(/LABEL=(\\S+)/)[1]
fs.appendFileSync(${JSON.stringify(join(T, 'events'))}, '+' + label + '\\n')
fs.appendFileSync(${JSON.stringify(join(T, 'calls.jsonl'))}, JSON.stringify({ label, argv: a, prompt }) + '\\n')
setTimeout(() => {
  fs.appendFileSync(${JSON.stringify(join(T, 'events'))}, '-' + label + '\\n')
  if (label === 'fail') process.exit(1)
  fs.writeFileSync(at('-o'), a.includes('--output-schema') ? JSON.stringify({ label, ok: true, nested: { x: 'y' } }) : 'plain:' + label)
}, label.startsWith('slow') ? 300 : 10)
`)
chmodSync(join(T, 'codex'), 0o755)

writeFileSync(join(T, 'flow.js'), `export const meta = { name: 'check' }
phase('One')
const S = { type: 'object', properties: { label: { type: 'string' }, ok: { type: 'boolean' }, nested: { type: 'object', properties: { x: { type: 'string' } } } }, required: ['label', 'ok'] }
return parallel([
  () => agent('LABEL=a', { label: 'a', schema: S, effort: 'max', agentType: 'wave-builder' }),
  () => agent('LABEL=fail', { label: 'fail', schema: S }),
  () => agent('LABEL=plain', { label: 'plain' }),
  ...['slow1', 'slow2', 'slow3', 'slow4'].map(l => () => agent('LABEL=' + l, { label: l, effort: 'low' })),
])`)
writeFileSync(join(T, 'args.json'), JSON.stringify({ repo, sp }))
const env = { ...process.env, CODEX_BIN: join(T, 'codex'), WAVE_CODEX_MAX: '2', WAVE_STALL_MIN: '0.002' }
const host = (...extra) => spawnSync('node', [HOST, join(T, 'flow.js'), ...extra], { env, encoding: 'utf8' })
const calls = () => readFileSync(join(T, 'calls.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l))
const assert = (c, m) => { if (!c) { console.log('FAIL', m); process.exitCode = 1 } else console.log('ok  ', m) }

const r1 = host(join(T, 'args.json'))
assert(r1.status === 0, 'host exits 0' + (r1.status ? ' (' + (r1.stderr || '').slice(-300) + ')' : ''))
const RUN = join(T, 'args.run')
const out = existsSync(join(RUN, 'result.json')) ? JSON.parse(readFileSync(join(RUN, 'result.json'), 'utf8')) : []
assert(out[0] && out[0].label === 'a' && out[0].ok === true, 'a schema agent returns the parsed JSON')
assert(out[1] === null && out[2] === 'plain:plain', 'a failed agent returns null without stopping the others; no schema returns text')
const c = existsSync(join(T, 'calls.jsonl')) ? calls() : []
const by = l => c.find(x => x.label === l) || { argv: [], prompt: '' }
const flag = (x, f) => x.argv.includes(f) ? x.argv[x.argv.indexOf(f) + 1] : undefined
assert(flag(by('a'), '-c') === 'model_reasoning_effort="xhigh"' && flag(by('slow1'), '-c') === 'model_reasoning_effort="low"' && flag(by('plain'), '-c') === undefined, 'effort max maps to xhigh, others pass through, none sets nothing')
const schema = flag(by('a'), '--output-schema') ? JSON.parse(readFileSync(flag(by('a'), '--output-schema'), 'utf8')) : {}
assert(schema.additionalProperties === false && schema.required.join() === 'label,ok,nested' && schema.properties.nested.additionalProperties === false && schema.properties.nested.required.join() === 'x', 'schemas are made strict, nested objects included')
assert(by('a').prompt.includes('StructuredOutput') && !by('plain').prompt.includes('StructuredOutput'), 'schema prompts say what "return through StructuredOutput" means')
assert(flag(by('a'), '-C') === repo && flag(by('a'), '-s') === 'danger-full-access' && !by('a').argv.includes('--add-dir'), 'agents run in args.repo with full access by default')
let n = 0, peak = 0
for (const e of readFileSync(join(T, 'events'), 'utf8').trim().split('\n')) { n += e[0] === '+' ? 1 : -1; peak = Math.max(peak, n) }
assert(peak === 2, 'WAVE_CODEX_MAX caps the agents running at once (peak ' + peak + ')')
const journal = existsSync(join(RUN, 'journal.jsonl')) ? readFileSync(join(RUN, 'journal.jsonl'), 'utf8').trim().split('\n') : []
assert(journal.length === 7, 'every finished agent is journaled, failures included')
assert(existsSync(join(RUN, 'host.log')) && readFileSync(join(RUN, 'host.log'), 'utf8').includes('STALL'), 'the watchdog logs STALL when no agent finishes in time')

const r2 = host(join(T, 'args.json'))
assert(r2.status !== 0 && /--resume/.test(r2.stderr), 'a second run over an existing journal is refused without --resume')
const before = c.length
const r3 = host(join(T, 'args.json'), '--resume')
const rerun = calls().slice(before).map(x => x.label)
assert(r3.status === 0 && rerun.join() === 'fail', '--resume seeds every journaled result and re-runs only the failed agent (' + rerun.join() + ')')

writeFileSync(join(T, 'ws.json'), JSON.stringify({ repo, sp, codexSandbox: 'workspace-write' }))
writeFileSync(join(T, 'ws.js'), `return agent('LABEL=ws', { label: 'ws' })`)
const r4 = spawnSync('node', [HOST, join(T, 'ws.js'), join(T, 'ws.json')], { env, encoding: 'utf8' })
const ws = calls().find(x => x.label === 'ws') || { argv: [] }
const dirs = ws.argv.flatMap((v, i) => v === '--add-dir' ? [ws.argv[i + 1]] : [])
assert(r4.status === 0 && flag(ws, '-s') === 'workspace-write' && dirs.includes(sp) && dirs.some(d => d.endsWith('/repo/.git')), 'workspace-write adds the scratchpad and the git dir as writable (' + dirs.join(' ') + ')')
