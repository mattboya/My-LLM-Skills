// Job bridge for Codex and Antigravity: the shared runner schedules jobs; the parent chat (Codex) or antigravity-host.py runs them.
// No model calls or child processes are launched here. See references/codex-native.md.
import { readFileSync, writeFileSync, renameSync, mkdirSync, existsSync, readdirSync, appendFileSync, unlinkSync, openSync, closeSync, realpathSync } from 'node:fs'
import { createHash, randomUUID } from 'node:crypto'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const read = path => JSON.parse(readFileSync(path, 'utf8'))
const hash = value => createHash('sha256').update(value).digest('hex')
const runPath = argsPath => resolve(argsPath).replace(/\.json$/, '') + '.native.run'
const debug = message => { if (process.env.WAVE_NATIVE_DEBUG === '1') console.error(`[wave native debug] ${message}`) }
function write(path, value) {
  const temp = `${path}.${randomUUID()}.tmp`
  writeFileSync(temp, JSON.stringify(value, null, 2) + '\n')
  renameSync(temp, path)
}

// The runner uses only this JSON Schema subset. Reject a malformed report before releasing dependencies.
export function validate(value, schema, path = '$') {
  if (!schema) return
  const type = Array.isArray(value) ? 'array' : value === null ? 'null' : typeof value
  if (schema.type && type !== schema.type) throw new Error(`${path}: expected ${schema.type}, got ${type}`)
  if (schema.enum && !schema.enum.includes(value)) throw new Error(`${path}: value is outside enum`)
  if (type === 'object') {
    for (const key of schema.required || []) if (!(key in value)) throw new Error(`${path}.${key}: required`)
    for (const [key, spec] of Object.entries(schema.properties || {})) if (key in value) validate(value[key], spec, `${path}.${key}`)
  }
  if (type === 'array') value.forEach((item, i) => validate(item, schema.items, `${path}[${i}]`))
}

export function status(argsPath) {
  const run = runPath(argsPath)
  const jobs = existsSync(join(run, 'jobs')) ? readdirSync(join(run, 'jobs')).filter(f => f.endsWith('.json')).map(f => {
    const jobPath = join(run, 'jobs', f)
    const { id, label, state, agentId, taskName, phase, effort } = read(jobPath)
    return { id, label, state, agentId, taskName, phase, effort, jobPath }
  }) : []
  return { run, ...read(join(run, 'state.json')), jobs }
}

export function update(argsPath, id, action, value, taskName) {
  const run = runPath(argsPath)
  if (read(join(run, 'state.json')).state !== 'running') throw new Error('host is not running; reconcile agents before --resume')
  if (!/^[a-f0-9]{64}$/.test(id)) throw new Error('invalid job id')
  const path = join(run, 'jobs', `${id}.json`)
  const job = read(path)
  if (action === 'bind') {
    if (job.state !== 'ready' || !value || !taskName) throw new Error('bind needs a ready job, agent ID and task name')
    Object.assign(job, { state: 'running', agentId: value, taskName })
  } else {
    if (job.state !== 'running') throw new Error('only a bound running job can return a report')
    if (action === 'complete') {
      const report = read(value)
      if (report.agentId !== job.agentId) throw new Error('report agentId does not match the bound agent')
      validate(report.result, job.schema)
      if (report.result === null || report.result === undefined) throw new Error('empty result')
      Object.assign(job, { state: 'completed', result: report.result })
      // The shared runner resolves dependency promises even for incomplete builders.
      // In native Codex runs, stop before those reports can release downstream work.
      if (job.label.startsWith('impl:')) {
        const built = report.result.status === 'complete' && report.result.commits?.length > 0
        const redFirst = report.result.testsAdded?.length > 0 && report.result.testsAdded.every(test => test.sawRedFirst === true && test.redOutputFile)
        if (!built || !redFirst) Object.assign(job, { state: 'failed', error: !built ? 'builder incomplete or produced no commits; reconcile before resuming' : 'builder missing red-first test evidence; reconcile before resuming' })
      }
    } else if (action === 'fail') {
      Object.assign(job, { state: 'failed', error: value || 'native agent failed' })
    } else throw new Error(`unknown action ${action}`)
  }
  write(path, job)
  debug(`${action} ${job.label}: ${job.state}`)
  return { id, label: job.label, state: job.state }
}

export async function serve(scriptPath, argsPath, resume = false) {
  const run = runPath(argsPath)
  mkdirSync(join(run, 'jobs'), { recursive: true })
  const lock = join(run, 'host.lock')
  if (existsSync(lock)) {
    const pid = read(lock).pid
    try { process.kill(pid, 0); throw new Error(`host already running (pid ${pid})`) }
    catch (error) { if (error.code !== 'ESRCH') throw error }
    unlinkSync(lock)
  }
  const fd = openSync(lock, 'wx')
  writeFileSync(fd, JSON.stringify({ pid: process.pid }))
  closeSync(fd)
  const statePath = join(run, 'state.json')
  let timer
  const release = () => { if (existsSync(lock) && read(lock).pid === process.pid) unlinkSync(lock) }
  const interrupt = () => {
    write(statePath, { ...read(statePath), state: 'interrupted' })
    release()
    process.exit(130)
  }
  try {
    const args = read(argsPath)
    const src = readFileSync(scriptPath, 'utf8').replace(/^export const meta/m, 'const meta')
    const fingerprint = hash(src + JSON.stringify(args))
    const previous = existsSync(statePath) ? read(statePath) : null
    if (previous && !resume) throw new Error('existing run: use --resume after reconciling native agents')
    if (previous && previous.fingerprint !== fingerprint) throw new Error('script or args changed; resume requires the original inputs')
    if (previous?.state === 'finished') throw new Error('run already finished; read result.json')
    const seeds = { ...args.seeds }
    const journal = join(run, 'journal.jsonl')
    if (existsSync(journal)) for (const line of readFileSync(journal, 'utf8').split('\n').filter(Boolean)) {
      const entry = JSON.parse(line)
      if (entry.result != null) seeds[entry.label] = entry.result
    }
    args.seeds = seeds
    write(statePath, { state: 'running', fingerprint, pid: process.pid, startedAt: previous?.startedAt || new Date().toISOString() })
    process.on('SIGINT', interrupt); process.on('SIGTERM', interrupt)
    let lastProgress = Date.now(), sequence = 0
    const log = message => appendFileSync(join(run, 'host.log'), `${new Date().toISOString()} ${message}\n`)
    const phase = title => log(`== ${title}`)
    let rejectFailure
    let failedRun
    const failure = new Promise((_, reject) => { rejectFailure = reject })
    const abort = error => { failedRun = error; rejectFailure(error); throw error }
    const agent = async (prompt, opts = {}) => {
      if (failedRun) throw failedRun
      const label = opts.label || `agent-${++sequence}`
      if (seeds[label] !== undefined) return seeds[label]
      const id = hash(label)
      const path = join(run, 'jobs', `${id}.json`)
      let job = existsSync(path) ? read(path) : null
      if (job && (job.prompt !== prompt || JSON.stringify(job.schema) !== JSON.stringify(opts.schema))) abort(new Error(`${label}: changed request during resume`))
      if (!job || job.state === 'failed') {
        if (job) appendFileSync(join(run, 'attempts.jsonl'), JSON.stringify({ ...job, archivedAt: new Date().toISOString() }) + '\n')
        job = { id, label, state: 'ready', prompt, schema: opts.schema, phase: opts.phase, effort: opts.effort }
        write(path, job)
        log(`${label}: ready for native dispatch`)
        debug(`published ${label} (${id})`)
      }
      // Running bindings and unjournaled completed reports survive a host interruption.
      while (true) {
        job = read(path)
        if (job.state === 'completed') {
          validate(job.result, opts.schema)
          appendFileSync(journal, JSON.stringify({ label, agentId: job.agentId, taskName: job.taskName, result: job.result }) + '\n')
          log(`${label}: done (${job.agentId})`)
          lastProgress = Date.now()
          return job.result
        }
        if (job.state === 'failed') {
          const error = new Error(`${label}: ${job.error}`)
          abort(error)
        }
        await new Promise(resolve => setTimeout(resolve, 100))
      }
    }
    const parallel = thunks => Promise.all(thunks.map(t => t()))
    const pipeline = (items, ...stages) => parallel(items.map(item => async () => {
      let value = item
      for (const stage of stages) value = await stage(value)
      return value
    }))
    timer = setInterval(() => {
      if (Date.now() - lastProgress >= 30 * 60000) { log('STALL: no native agent report for 30 minutes'); lastProgress = Date.now() }
    }, 60000)
    const body = new Function('args', 'agent', 'parallel', 'pipeline', 'log', 'phase', `return (async () => {\n${src}\n})()`)
    const result = await Promise.race([body(args, agent, parallel, pipeline, log, phase), failure])
    write(join(run, 'result.json'), result)
    write(statePath, { ...read(statePath), state: 'finished' })
    log('finished: result.json')
    return result
  } catch (error) {
    // A refused duplicate/resume must not corrupt the existing run's state.
    if (existsSync(statePath) && read(statePath).pid === process.pid) write(statePath, { ...read(statePath), state: 'failed', error: String(error) })
    throw error
  } finally {
    clearInterval(timer)
    process.off('SIGINT', interrupt); process.off('SIGTERM', interrupt)
    release()
  }
}

if (existsSync(process.argv[1] ?? '') && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url))) {   // realpath: SKILL.md runs us through a symlinked dir
  const [action, ...params] = process.argv.slice(2)
  try {
    if (action === 'serve' && params[0] && params[1]) {
      await serve(params[0], params[1], params.includes('--resume'))
      process.exit(0)
    } else if (action === 'status' && params[0]) console.log(JSON.stringify(status(params[0]), null, 2))
    else if (['bind', 'complete', 'fail'].includes(action) && params[0] && params[1]) console.log(JSON.stringify(update(params[0], params[1], action, params[2], params[3])))
    else throw new Error('usage: native-host.mjs serve <script.js> <args.json> [--resume] | status <args.json> | bind <args.json> <job-id> <agent-id> <task-name> | complete <args.json> <job-id> <report.json> | fail <args.json> <job-id> <reason>')
  } catch (error) { console.error(String(error)); process.exit(1) }
}
