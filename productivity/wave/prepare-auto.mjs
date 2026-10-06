// Capture current work into an isolated auto checkout without changing the source index or branch.
// Usage: node prepare-auto.mjs <spec.json>
// spec: { repo, checkout, manifest, copy?: ['WORK_QUEUE.md', ...] }
import { spawnSync } from 'node:child_process'
import { readFileSync, writeFileSync, renameSync, mkdirSync, mkdtempSync, rmSync, existsSync, cpSync, realpathSync, lstatSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve, relative, isAbsolute } from 'node:path'
import { randomUUID } from 'node:crypto'
import { fileURLToPath } from 'node:url'

const read = path => JSON.parse(readFileSync(path, 'utf8'))
const debug = message => { if (process.env.WAVE_AUTO_DEBUG === '1') console.error(`[wave auto debug] ${message}`) }
function git(repo, argv, env = {}, input) {
  const out = spawnSync('git', ['-C', repo, ...argv], { encoding: 'utf8', input, env: { ...process.env, GIT_OPTIONAL_LOCKS: '0', ...env }, maxBuffer: 32 * 1024 * 1024 })
  if (out.status !== 0) throw new Error(`git ${argv[0]} failed: ${out.stderr.trim() || out.error || out.status}`)
  return out.stdout
}
function write(path, value) {
  mkdirSync(dirname(path), { recursive: true })
  const temp = `${path}.${randomUUID()}.tmp`
  writeFileSync(temp, JSON.stringify(value, null, 2) + '\n')
  renameSync(temp, path)
}
function outside(repo, target) {
  const rel = relative(repo, target)
  if (!rel || (!rel.startsWith('..' + '/') && rel !== '..' && !isAbsolute(rel))) throw new Error('checkout and manifest must be outside the source working tree')
}

export function prepare(spec) {
  const repo = realpathSync(git(resolve(spec.repo), ['rev-parse', '--show-toplevel']).trim())
  const checkout = resolve(spec.checkout), manifestPath = resolve(spec.manifest)
  // Resolve existing ancestors to catch a destination symlink back into the source.
  for (const target of [checkout, manifestPath]) {
    let parent = dirname(target)
    while (!existsSync(parent)) parent = dirname(parent)
    outside(repo, resolve(realpathSync(parent), relative(parent, target)))
  }
  const copiedPaths = ['WORK_QUEUE.md', ...(spec.copy || [])]
  for (const path of copiedPaths) {
    const rel = relative(repo, resolve(repo, path))
    if (!rel || rel === '..' || rel.startsWith('../') || isAbsolute(rel) || rel.split('/').includes('.git')) throw new Error(`invalid copy path: ${path}`)
  }
  if (existsSync(manifestPath)) {
    const saved = read(manifestPath)
    if (saved.sourceRepo !== repo || saved.checkout !== checkout) throw new Error('manifest belongs to another auto checkout')
    if (existsSync(join(checkout, '.git'))) {
      const branch = git(checkout, ['symbolic-ref', '--short', 'HEAD']).trim()
      if (branch !== saved.branch) throw new Error('auto checkout branch changed; reconcile the existing run')
      git(checkout, ['merge-base', '--is-ancestor', saved.checkpoint, 'HEAD'])
      if (saved.state !== 'ready') { copyInputs(checkout, saved.inputs); saved.state = 'ready'; write(manifestPath, saved) }
      return { ...saved, manifest: manifestPath, reused: true }
    }
    if (saved.state === 'ready') throw new Error('saved auto checkout is missing; preserve its recorded run before recreating anything')
    // Resume a preparation interrupted after checkpointing, using that exact checkpoint.
    git(repo, ['cat-file', '-e', `${saved.checkpoint}^{commit}`])
    createCheckout(repo, saved)
    copyInputs(checkout, saved.inputs)
    saved.state = 'ready'; write(manifestPath, saved)
    return { ...saved, manifest: manifestPath, reused: true }
  }
  if (existsSync(checkout)) throw new Error('checkout destination already exists; choose an unused destination')
  const scratch = mkdtempSync(join(tmpdir(), 'wave-auto-index-'))
  try {
    const index = join(scratch, 'index')
    const env = { GIT_INDEX_FILE: index }
    let base, tree, sourceStatus, sourceBranch
    // Verify a stable capture. Any concurrent source writer remains untouched.
    for (let attempt = 0; attempt < 3; attempt++) {
      base = git(repo, ['rev-parse', 'HEAD']).trim()
      sourceBranch = git(repo, ['rev-parse', '--abbrev-ref', 'HEAD']).trim()
      sourceStatus = git(repo, ['status', '--porcelain=v1', '-z', '--untracked-files=all'])
      // Rebuild from the source's tracked path set, including newly force-added ignored files.
      // Index-info also works with split indexes and preserves conflict stages until add resolves the snapshot.
      git(repo, ['read-tree', '--empty'], env)
      git(repo, ['update-index', '-z', '--index-info'], env, git(repo, ['ls-files', '--stage', '-z']))
      const sparsePaths = git(repo, ['ls-files', '-v', '-z']).split('\0').filter(line => line.startsWith('S ')).map(line => line.slice(2))
      if (sparsePaths.length) git(repo, ['update-index', '--skip-worktree', '-z', '--stdin'], env, sparsePaths.join('\0') + '\0')
      git(repo, ['add', '--all', '--', '.'], env)
      tree = git(repo, ['write-tree'], env).trim()
      git(repo, ['add', '--all', '--', '.'], env)
      const verifiedTree = git(repo, ['write-tree'], env).trim()
      if (base === git(repo, ['rev-parse', 'HEAD']).trim() && tree === verifiedTree && sourceStatus === git(repo, ['status', '--porcelain=v1', '-z', '--untracked-files=all'])) break
      if (attempt === 2) throw new Error('source work changed throughout three snapshot attempts; existing work is untouched')
      debug('source changed during capture; retrying')
    }
    // Submodule work cannot be represented by the superproject's tree alone.
    const nestedDirty = git(repo, ['submodule', 'foreach', '--quiet', '--recursive', 'test -z "$(git status --porcelain)"'])
    debug(`stable capture ${base.slice(0, 10)}; submodule check ${nestedDirty.length ? 'reported output' : 'passed'}`)
    const checkpoint = git(repo, ['-c', 'user.name=Wave auto snapshot', '-c', 'user.email=wave-auto@localhost',
      'commit-tree', tree, '-p', base, '-m', 'Wave auto: preserve pre-existing working-tree content'], env).trim()
    const inputs = captureInputs(repo, manifestPath, copiedPaths)
    const saved = { state: 'captured', sourceRepo: repo, sourceBranch, sourceBase: base, sourceStatus, inputs,
      checkout, branch: `codex/wave-auto-${randomUUID().slice(0, 8)}`, checkpoint, capturedAt: new Date().toISOString() }
    write(manifestPath, saved)
    mkdirSync(dirname(checkout), { recursive: true })
    createCheckout(repo, saved)
    copyInputs(checkout, inputs)
    const status = git(checkout, ['status', '--porcelain=v1', '--untracked-files=all']).trim()
    if (status) throw new Error('copied run inputs are not ignored; record them in a local setup commit before dispatch')
    saved.state = 'ready'; write(manifestPath, saved)
    return { ...saved, manifest: manifestPath, reused: false }
  } finally {
    rmSync(scratch, { recursive: true, force: true })
  }
}

function createCheckout(repo, saved) {
  const ref = `refs/heads/${saved.branch}`
  const found = spawnSync('git', ['-C', repo, 'show-ref', '--verify', '--quiet', ref])
  if (found.status === 0) {
    if (git(repo, ['rev-parse', ref]).trim() !== saved.checkpoint) throw new Error('prepared branch advanced without its checkout; preserve and reconcile that existing work')
    const entries = git(repo, ['worktree', 'list', '--porcelain', '-z']).split('\0\0').map(entry => entry.split('\0'))
    for (const entry of entries) if (entry.includes(`branch ${ref}`)) {
      const registered = entry.find(field => field.startsWith('worktree ')).slice(9)
      // A partial creation can leave only registration metadata. Remove just that missing checkout's registration.
      let parent = dirname(saved.checkout)
      while (!existsSync(parent)) parent = dirname(parent)
      const canonical = resolve(realpathSync(parent), relative(parent, saved.checkout))
      if (registered !== canonical || existsSync(registered)) throw new Error('prepared branch is attached to another existing checkout')
      git(repo, ['worktree', 'remove', '--force', registered])
    }
    git(repo, ['worktree', 'add', saved.checkout, saved.branch])
  } else if (found.status === 1) git(repo, ['worktree', 'add', '-b', saved.branch, saved.checkout, saved.checkpoint])
  else throw new Error('could not inspect the prepared branch')
}

function captureInputs(repo, manifestPath, paths) {
  const inputs = []
  for (const path of paths) {
    const source = resolve(repo, path)
    if (!existsSync(source) || git(repo, ['ls-files', '--', path]).trim()) continue
    // Only copy explicitly named ignored control files. Dependencies/config are handled by the protocol.
    const ignored = spawnSync('git', ['-C', repo, 'check-ignore', '-q', '--', path])
    if (ignored.status !== 0) continue
    if (!lstatSync(source).isFile()) throw new Error(`ignored control input must be a regular file: ${path}`)
    const target = resolve(`${manifestPath}.inputs`, relative(repo, source))
    mkdirSync(dirname(target), { recursive: true })
    cpSync(source, target)
    inputs.push({ path: relative(repo, source), backup: target })
  }
  return inputs
}

function copyInputs(checkout, inputs = []) {
  for (const input of inputs) {
    const target = resolve(checkout, input.path)
    if (existsSync(target)) {
      if (!readFileSync(target).equals(readFileSync(input.backup))) throw new Error(`captured control input changed before preparation completed: ${input.path}`)
      continue
    }
    mkdirSync(dirname(target), { recursive: true })
    cpSync(input.backup, target, { errorOnExist: true, force: false })
  }
}

if (existsSync(process.argv[1] ?? '') && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url))) {   // realpath: SKILL.md runs us through a symlinked dir
  try {
    if (!process.argv[2]) throw new Error('usage: prepare-auto.mjs <spec.json>')
    console.log(JSON.stringify(prepare(read(process.argv[2])), null, 2))
  } catch (error) { console.error(String(error)); process.exit(1) }
}
