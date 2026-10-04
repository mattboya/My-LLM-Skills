// Runs a Workflow-tool script (lane-runner.js, or a planning script written the same way) under Codex.
// Each agent() is one `codex exec`; parallel, pipeline, log and phase behave like the Workflow tool's.
//   node codex-host.mjs <script.js> <args.json> [--resume]
// Everything lands in <args.json minus .json>.run/: journal.jsonl, host.log, agents/<label>.*, result.json.
// --resume seeds every non-null journaled result, so only unfinished or failed agents run again.
// args.repo is every agent's working root; args.codexSandbox picks the sandbox (default danger-full-access,
// like a Claude wave in bypass mode; workspace-write adds args.sp and the git dir as writable).
// Env: CODEX_BIN (default: codex on PATH, else the one inside ChatGPT.app), WAVE_CODEX_MAX (16), WAVE_STALL_MIN (30).
import { readFileSync, writeFileSync, appendFileSync, mkdirSync, existsSync, openSync, closeSync } from 'node:fs'
import { spawn, spawnSync } from 'node:child_process'
import { join } from 'node:path'

const [scriptPath, argsPath, ...flags] = process.argv.slice(2)
if (!scriptPath || !argsPath) { console.error('usage: node codex-host.mjs <script.js> <args.json> [--resume]'); process.exit(2) }
const args = JSON.parse(readFileSync(argsPath, 'utf8'))
const RUN = argsPath.replace(/\.json$/, '') + '.run'
const JOURNAL = join(RUN, 'journal.jsonl')
if (existsSync(JOURNAL) && !flags.includes('--resume')) { console.error(`${RUN} already has a journal: pass --resume to continue that run, or delete the folder to start over`); process.exit(2) }
mkdirSync(join(RUN, 'agents'), { recursive: true })
args.seeds = { ...args.seeds }
if (existsSync(JOURNAL)) for (const line of readFileSync(JOURNAL, 'utf8').split('\n').filter(Boolean)) {
  const { label, result } = JSON.parse(line)
  if (result != null) args.seeds[label] = result
}

const APP = '/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex'
const CODEX = process.env.CODEX_BIN || (spawnSync('which', ['codex']).status === 0 ? 'codex' : APP)
const MAX = Number(process.env.WAVE_CODEX_MAX || 16)   // ponytail: the runner's prompts promise "up to 16 agents"
const STALL_MS = Number(process.env.WAVE_STALL_MIN || 30) * 60000
const REPO = args.repo || process.cwd()
const SANDBOX = args.codexSandbox || 'danger-full-access'
const GIT_DIR = spawnSync('git', ['-C', REPO, 'rev-parse', '--path-format=absolute', '--git-common-dir'], { encoding: 'utf8' }).stdout.trim()

function log(m) { const line = `${new Date().toISOString()} ${m}`; console.error(line); appendFileSync(join(RUN, 'host.log'), line + '\n') }
const phase = title => log(`== ${title}`)
const parallel = thunks => Promise.all(thunks.map(t => t().catch(e => { log(`parallel: ${e}`); return null })))
const pipeline = (items, ...stages) => parallel(items.map(x => async () => { let v = x; for (const s of stages) v = await s(v); return v }))

// Codex's --output-schema is OpenAI strict mode: every object closed, every property required.
function strict(s) {
  if (Array.isArray(s)) return s.map(strict)
  if (!s || typeof s !== 'object') return s
  const o = Object.fromEntries(Object.entries(s).map(([k, v]) => [k, strict(v)]))
  if (o.type === 'object' && o.properties) { o.additionalProperties = false; o.required = Object.keys(o.properties) }
  return o
}

// A finished agent hands its slot straight to the next waiter, so the cap never overshoots.
let active = 0, lastProgress = Date.now(), n = 0
const waiting = []
const slot = () => active < MAX ? (active++, Promise.resolve()) : new Promise(r => waiting.push(r))
const release = () => { const next = waiting.shift(); if (next) next(); else active-- }
setInterval(() => {
  if (active && Date.now() - lastProgress > STALL_MS) { log(`STALL: no agent has finished for ${Math.round((Date.now() - lastProgress) / 60000)} min; ${active} running`); lastProgress = Date.now() }
}, Math.min(60000, STALL_MS)).unref()

async function agent(prompt, opts = {}) {
  const label = opts.label || `agent-${++n}`
  if (args.seeds[label] !== undefined) { log(`${label}: seeded`); return args.seeds[label] }
  await slot()
  const f = join(RUN, 'agents', label.replace(/[^\w.#-]/g, '_'))
  const argv = ['exec', '-C', REPO, '-s', SANDBOX, '-o', f + '.out']
  if (SANDBOX === 'workspace-write') for (const d of [args.sp, GIT_DIR].filter(Boolean)) argv.push('--add-dir', d)
  const effort = opts.effort === 'max' ? 'xhigh' : opts.effort   // Codex tops out at xhigh
  if (effort) argv.push('-c', `model_reasoning_effort="${effort}"`)
  let text = prompt
  if (opts.schema) {
    writeFileSync(f + '.schema.json', JSON.stringify(strict(opts.schema)))
    argv.push('--output-schema', f + '.schema.json')
    text += '\n\n(Codex: "return through StructuredOutput" means your final message is only the JSON object your output schema describes.)'
  }
  argv.push('-')
  writeFileSync(f + '.prompt.txt', text)
  log(`${label}: started`)
  let code = -1, result = null
  try {
    const out = openSync(f + '.log', 'w')
    code = await new Promise(res => {
      const p = spawn(CODEX, argv, { cwd: REPO, stdio: ['pipe', out, out] })
      p.on('error', () => res(-1)); p.on('close', res)
      p.stdin.on('error', () => {}); p.stdin.end(text)
    })
    closeSync(out)
    if (code === 0 && existsSync(f + '.out')) { const raw = readFileSync(f + '.out', 'utf8'); result = opts.schema ? JSON.parse(raw) : raw }
  } catch (e) { log(`${label}: ${e}`) }
  release()
  lastProgress = Date.now()
  appendFileSync(JOURNAL, JSON.stringify({ label, result }) + '\n')
  log(`${label}: ${result == null ? `FAILED (exit ${code}), see ${f}.log` : 'done'}`)
  return result
}

const src = readFileSync(scriptPath, 'utf8').replace(/^export const meta/m, 'const meta')
const body = new Function('args', 'agent', 'parallel', 'pipeline', 'log', 'phase', `return (async () => {\n${src}\n})()`)
const result = await body(args, agent, parallel, pipeline, log, phase)
writeFileSync(join(RUN, 'result.json'), JSON.stringify(result, null, 1))
log(`finished: ${join(RUN, 'result.json')}`)
