// File-protocol integration checks. Native agent dispatch is simulated; no model calls or repository edits.
import { mkdtempSync, writeFileSync, readFileSync, rmSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawn, spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import { status, update, validate } from './native-host.mjs'

const HOST = fileURLToPath(new URL('./native-host.mjs', import.meta.url))
const T = mkdtempSync(join(tmpdir(), 'wave-native-check-'))
const children = []
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
const json = path => JSON.parse(readFileSync(path, 'utf8'))
const save = (path, value) => writeFileSync(path, JSON.stringify(value))
async function until(fn) {
  const start = Date.now()
  while (Date.now() - start < 5000) {
    const value = fn()
    if (value) return value
    await pause(20)
  }
  throw new Error('timed out waiting for host')
}
function start(script, args, resume = false) {
  const child = spawn(process.execPath, [HOST, 'serve', script, args, ...(resume ? ['--resume'] : [])], { stdio: ['ignore', 'pipe', 'pipe'] })
  children.push(child)
  child.errors = ''
  child.stderr.on('data', chunk => { child.errors += chunk })
  child.done = new Promise(resolve => child.on('exit', (code, signal) => resolve({ code, signal })))
  return child
}
function job(args, label) { return status(args).jobs.find(j => j.label === label) }
function report(args, label, agentId, result) {
  const file = join(T, `report-${label.replace(/[^\w]/g, '_')}.json`)
  save(file, { agentId, result })
  return update(args, job(args, label).id, 'complete', file)
}
function bind(args, label, agentId = label) { return update(args, job(args, label).id, 'bind', agentId, `task_${label}`) }
function fixture(name, script, args = {}) {
  const scriptPath = join(T, `${name}.js`), argsPath = join(T, `${name}.json`)
  writeFileSync(scriptPath, script); save(argsPath, args)
  return { scriptPath, argsPath }
}
const schema = { type: 'object', properties: { ok: { type: 'boolean' }, results: { type: 'array', items: { type: 'string', enum: ['red', 'green'] } } }, required: ['ok', 'results'] }
const good = { ok: true, results: ['red', 'green'] }

try {
  assert.throws(() => validate({ ok: true }, schema), /required/)
  assert.throws(() => validate({ ok: true, results: ['blue'] }, schema), /outside enum/)
  assert.throws(() => validate({ ok: 'yes', results: [] }, schema), /expected boolean/)
  const f = fixture('ordering', `
const s = ${JSON.stringify(schema)}
const results = await parallel([
  () => agent('build A', { label: 'a', phase: 'Lanes', schema: s }),
  () => agent('build B', { label: 'b', schema: s, effort: 'high' }),
])
const review = await agent('review both: ' + JSON.stringify(results), { label: 'review', schema: s })
return { results, review }
`)
  let host = start(f.scriptPath, f.argsPath)
  await until(() => existsSync(join(T, 'ordering.native.run', 'state.json')) && status(f.argsPath).jobs.length === 2)
  assert(!job(f.argsPath, 'review'), 'dependent review cannot be dispatched early')
  assert.equal(job(f.argsPath, 'b').effort, 'high')
  const duplicate = spawnSync(process.execPath, [HOST, 'serve', f.scriptPath, f.argsPath, '--resume'], { encoding: 'utf8' })
  assert.notEqual(duplicate.status, 0)
  assert.match(duplicate.stderr, /already running/)
  assert.equal(status(f.argsPath).state, 'running')
  bind(f.argsPath, 'a', 'native-a'); bind(f.argsPath, 'b', 'native-b')
  assert.throws(() => bind(f.argsPath, 'a', 'another-agent'), /ready job/)
  assert.throws(() => update(f.argsPath, '../oops', 'bind', 'x', 'x'), /invalid job id/)
  assert.throws(() => report(f.argsPath, 'a', 'wrong-agent', good), /agentId/)
  assert.throws(() => report(f.argsPath, 'a', 'native-a', { ok: true }), /required/)
  assert.equal(job(f.argsPath, 'a').state, 'running')
  report(f.argsPath, 'a', 'native-a', good)
  // Interrupt before the host's next poll: even a completed report not yet journaled must survive.
  host.kill('SIGTERM')
  assert.equal((await host.done).code, 130)
  assert.equal(status(f.argsPath).state, 'interrupted')
  assert.equal(job(f.argsPath, 'b').agentId, 'native-b')
  const refused = spawnSync(process.execPath, [HOST, 'serve', f.scriptPath, f.argsPath], { encoding: 'utf8' })
  assert.match(refused.stderr, /--resume/)
  save(f.argsPath, { changed: true })
  const changed = spawnSync(process.execPath, [HOST, 'serve', f.scriptPath, f.argsPath, '--resume'], { encoding: 'utf8' })
  assert.match(changed.stderr, /changed/)
  save(f.argsPath, {})
  host = start(f.scriptPath, f.argsPath, true)
  await until(() => status(f.argsPath).state === 'running')
  assert.equal(job(f.argsPath, 'b').state, 'running')
  assert.equal(job(f.argsPath, 'b').agentId, 'native-b', 'reachable native agent is reused')
  assert(!job(f.argsPath, 'review'))
  report(f.argsPath, 'b', 'native-b', good)
  await until(() => job(f.argsPath, 'review'))
  bind(f.argsPath, 'review', 'native-review')
  report(f.argsPath, 'review', 'native-review', good)
  assert.equal((await host.done).code, 0, host.errors)
  assert.equal(status(f.argsPath).state, 'finished')
  assert.deepEqual(json(join(T, 'ordering.native.run', 'result.json')), { results: [good, good], review: good })
  const entries = readFileSync(join(T, 'ordering.native.run', 'journal.jsonl'), 'utf8').trim().split('\n').map(JSON.parse)
  assert.equal(entries.filter(e => e.label === 'a').length, 1, 'completed work is never replayed')
  assert.equal(entries.find(e => e.label === 'b').agentId, 'native-b')
  assert.throws(() => update(f.argsPath, job(f.argsPath, 'a').id, 'fail', 'late'), /not running/)
  console.log('ok native dispatch: independent jobs, dependency waits, report validation, identity, duplicate host and recovery')

  const failed = fixture('failed', `await agent('first', { label: 'first', schema: ${JSON.stringify(schema)} }); return agent('must not start', { label: 'second' })`)
  host = start(failed.scriptPath, failed.argsPath)
  await until(() => existsSync(join(T, 'failed.native.run', 'state.json')) && job(failed.argsPath, 'first'))
  bind(failed.argsPath, 'first', 'stopped-native-agent')
  update(failed.argsPath, job(failed.argsPath, 'first').id, 'fail', 'agent stopped')
  assert.equal((await host.done).code, 1)
  assert.equal(status(failed.argsPath).state, 'failed')
  assert(!job(failed.argsPath, 'second'), 'failure cannot release a dependent job')
  host = start(failed.scriptPath, failed.argsPath, true)
  await until(() => job(failed.argsPath, 'first').state === 'ready')
  const failedAttempt = JSON.parse(readFileSync(join(T, 'failed.native.run', 'attempts.jsonl'), 'utf8').trim())
  assert.equal(failedAttempt.agentId, 'stopped-native-agent')
  assert.equal(failedAttempt.error, 'agent stopped')
  bind(failed.argsPath, 'first', 'replacement-agent')
  assert.throws(() => report(failed.argsPath, 'first', 'stopped-native-agent', good), /agentId/, 'stale report rejected')
  report(failed.argsPath, 'first', 'replacement-agent', good)
  await until(() => job(failed.argsPath, 'second'))
  bind(failed.argsPath, 'second', 'second-agent')
  report(failed.argsPath, 'second', 'second-agent', { done: true })
  assert.equal((await host.done).code, 0, host.errors)
  console.log('ok native failure: abort, explicit resume, replacement binding and stale-report rejection')

  // Exercise the actual shared lane runner in lean mode through the bridge.
  const lanes = fixture('lanes', '', {
    wave: 'Native bridge check', repo: T, sp: T, base: 'base', waveDoc: join(T, 'wave.md'), coAuthor: 'test',
    tickets: { A: 'T-A', B: 'T-B' }, protocol: { shared: 'shared', gates: 'gates', snapshot: 'snapshot' }, lean: true,
    units: [{ id: 'U1', lane: 'L1', title: 'first', items: ['A'], files: ['a'], brief: 'first' },
      { id: 'U2', lane: 'L2', title: 'dependent', items: ['B'], deps: ['U1'], files: ['b'], brief: 'second' }],
    lanes: [['U1'], ['U2']], journeys: [],
  })
  host = start(fileURLToPath(new URL('./lane-runner.js', import.meta.url)), lanes.argsPath)
  await until(() => existsSync(join(T, 'lanes.native.run', 'state.json')) && job(lanes.argsPath, 'impl:U1'))
  assert(!job(lanes.argsPath, 'impl:U2'))
  const impl = { status: 'complete', commits: [{ sha: 'abc123', ticket: 'T-A', subject: 'test' }], filesTouched: ['a'], summary: 'test', userFacingChange: 'test',
    testsAdded: [{ file: 'test', what: 'behavior', sawRedFirst: true, redOutputFile: 'red.txt' }], decisions: [], deviationsFromBrief: [], pendingHumanSteps: [], openQuestions: [], crossLaneNotes: [], reviewPlan: [], laterItems: [], incomplete: [] }
  for (const label of ['impl:U1', 'impl:U2']) {
    await until(() => job(lanes.argsPath, label))
    const request = json(job(lanes.argsPath, label).jobPath)
    assert(request.prompt.includes('TEST-DRIVEN DEVELOPMENT') && request.prompt.includes('RED:'), 'shared TDD prompt preserved')
    bind(lanes.argsPath, label)
    report(lanes.argsPath, label, label, impl)
  }
  await until(() => job(lanes.argsPath, 'final-gates'))
  bind(lanes.argsPath, 'final-gates')
  report(lanes.argsPath, 'final-gates', 'final-gates', { gates: [], allGreen: true, failuresFixed: [], remainingFailures: [], flaky: [], notes: '' })
  assert.equal((await host.done).code, 0, host.errors)
  const result = json(join(T, 'lanes.native.run', 'result.json'))
  assert.equal(result.units.length, 2)
  assert.equal(result.gates.allGreen, true)
  assert.deepEqual(status(lanes.argsPath).jobs.map(j => j.label).sort(), ['final-gates', 'impl:U1', 'impl:U2'])
  console.log('ok shared lane runner: native bridge preserves unit deps, TDD prompts, lean mode and final gates')

  for (const [name, broken] of [
    ['blocked', { ...impl, status: 'blocked', commits: [] }],
    ['partial', { ...impl, status: 'partial' }],
    ['no_commits', { ...impl, commits: [] }],
    ['no_tests', { ...impl, testsAdded: [] }],
    ['not_red_first', { ...impl, testsAdded: [{ ...impl.testsAdded[0], sawRedFirst: false }] }],
  ]) {
    const stopped = fixture(name, `await agent('build', { label: 'impl:U1', schema: ${JSON.stringify(json(job(lanes.argsPath, 'impl:U1').jobPath).schema)} }); return agent('dependent must not start', { label: 'impl:U2' })`)
    host = start(stopped.scriptPath, stopped.argsPath)
    await until(() => existsSync(join(T, `${name}.native.run`, 'state.json')) && job(stopped.argsPath, 'impl:U1'))
    bind(stopped.argsPath, 'impl:U1')
    report(stopped.argsPath, 'impl:U1', 'impl:U1', broken)
    assert.equal((await host.done).code, 1, name)
    assert.equal(job(stopped.argsPath, 'impl:U1').state, 'failed')
    assert.deepEqual(json(job(stopped.argsPath, 'impl:U1').jobPath).result, broken, 'actual report preserved')
    assert(!job(stopped.argsPath, 'impl:U2'), `${name} must not release dependent work`)
    if (name === 'partial') {
      host = start(stopped.scriptPath, stopped.argsPath, true)
      await until(() => job(stopped.argsPath, 'impl:U1').state === 'ready')
      const archived = JSON.parse(readFileSync(join(T, 'partial.native.run', 'attempts.jsonl'), 'utf8').trim())
      assert.deepEqual(archived.result, broken, 'partial report, commits and evidence survive resume')
      assert.equal(archived.agentId, 'impl:U1')
      host.kill('SIGTERM'); assert.equal((await host.done).code, 130)
    }
  }
  console.log('ok native guard: incomplete builders and missing red-first reports cannot release dependents')
} finally {
  for (const child of children) if (child.exitCode === null && child.signalCode === null) { child.kill('SIGKILL'); await child.done }
  rmSync(T, { recursive: true, force: true })
}
