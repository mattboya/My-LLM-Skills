// Real-Git integration checks in disposable repositories; no edits to the user's checkout.
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync, unlinkSync, symlinkSync, readlinkSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import { prepare } from './prepare-auto.mjs'

const root = mkdtempSync(join(tmpdir(), 'wave-auto-check-'))
const repo = join(root, 'source [with spaces]')
mkdirSync(repo)
function git(dir, ...argv) {
  const out = spawnSync('git', ['-C', dir, ...argv], { encoding: 'utf8', env: { ...process.env, GIT_OPTIONAL_LOCKS: '0' } })
  assert.equal(out.status, 0, out.stderr)
  return out.stdout
}
function save(path, value) { writeFileSync(path, typeof value === 'string' || Buffer.isBuffer(value) ? value : JSON.stringify(value)) }
try {
  git(repo, 'init', '-q', '-b', 'feature/in-progress')
  git(repo, 'config', 'user.name', 'Fixture User'); git(repo, 'config', 'user.email', 'fixture@localhost')
  save(join(repo, '.gitignore'), 'WORK_QUEUE.md\n*.queue.md\n*.wave.md\nignored-secret\nforced.local\n')
  save(join(repo, 'mixed.txt'), 'base\n'); save(join(repo, 'deleted.txt'), 'delete me\n')
  save(join(repo, 'renamed.txt'), 'rename me\n')
  git(repo, 'add', '--all'); git(repo, 'commit', '-qm', 'fixture base')
  save(join(repo, 'mixed.txt'), 'staged version\n'); git(repo, 'add', 'mixed.txt')
  save(join(repo, 'mixed.txt'), 'unstaged latest version\n')
  unlinkSync(join(repo, 'deleted.txt'))
  git(repo, 'mv', 'renamed.txt', 'renamed new.txt')
  save(join(repo, 'new binary.bin'), Buffer.from([0, 1, 2, 255]))
  symlinkSync('mixed.txt', join(repo, 'new link'))
  save(join(repo, 'WORK_QUEUE.md'), '## Ready\n### A\nWant: finish it\n')
  save(join(repo, 'saved.wave.md'), '**Status:** PLANNED\n')
  save(join(repo, 'ignored-secret'), 'must remain local\n')
  save(join(repo, 'forced.local'), 'staged ignored file\n'); git(repo, 'add', '-f', 'forced.local')
  save(join(repo, 'forced.local'), 'latest ignored-but-tracked content\n')
  git(repo, 'update-index', '--split-index')
  const sourceHead = git(repo, 'rev-parse', 'HEAD').trim()
  const sourceBranch = git(repo, 'symbolic-ref', '--short', 'HEAD').trim()
  const staged = git(repo, 'diff', '--cached', '--binary')
  const unstaged = git(repo, 'diff', '--binary')
  const sourceStatus = git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
  const index = readFileSync(join(repo, '.git', 'index'))
  const spec = { repo, checkout: join(root, 'run checkout'), manifest: join(root, 'run.json'), copy: ['saved.wave.md'] }
  const manifest = prepare(spec)
  assert.equal(manifest.state, 'ready')
  assert.equal(manifest.reused, false)
  assert(manifest.branch.startsWith('codex/wave-auto-'))
  assert.equal(git(spec.checkout, 'status', '--porcelain=v1').trim(), '')
  assert.equal(readFileSync(join(spec.checkout, 'mixed.txt'), 'utf8'), 'unstaged latest version\n')
  assert(!existsSync(join(spec.checkout, 'deleted.txt')))
  assert(existsSync(join(spec.checkout, 'renamed new.txt')))
  assert.deepEqual(readFileSync(join(spec.checkout, 'new binary.bin')), Buffer.from([0, 1, 2, 255]))
  assert.equal(readlinkSync(join(spec.checkout, 'new link')), 'mixed.txt')
  assert.equal(readFileSync(join(spec.checkout, 'WORK_QUEUE.md'), 'utf8'), readFileSync(join(repo, 'WORK_QUEUE.md'), 'utf8'))
  assert.equal(readFileSync(join(spec.checkout, 'saved.wave.md'), 'utf8'), '**Status:** PLANNED\n')
  assert(!existsSync(join(spec.checkout, 'ignored-secret')))
  assert.equal(readFileSync(join(spec.checkout, 'forced.local'), 'utf8'), 'latest ignored-but-tracked content\n')
  assert.equal(git(repo, 'rev-parse', 'HEAD').trim(), sourceHead)
  assert.equal(git(repo, 'symbolic-ref', '--short', 'HEAD').trim(), sourceBranch)
  assert.equal(git(repo, 'diff', '--cached', '--binary'), staged)
  assert.equal(git(repo, 'diff', '--binary'), unstaged)
  assert.equal(git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all'), sourceStatus)
  assert.deepEqual(readFileSync(join(repo, '.git', 'index')), index)
  console.log('ok dirty startup: staged/unstaged changes, deletions, renames, binary and symlink files captured; source index, files and branch preserved')

  // A Wave commit and interrupted writes must survive preparation being called again.
  save(join(spec.checkout, 'wave-result.txt'), 'completed local work\n')
  git(spec.checkout, 'add', 'wave-result.txt'); git(spec.checkout, 'commit', '-qm', 'wave implementation')
  const waveHead = git(spec.checkout, 'rev-parse', 'HEAD').trim()
  save(join(spec.checkout, 'in-flight.txt'), 'writer has not committed yet\n')
  save(join(repo, 'WORK_QUEUE.md'), 'source queue changed while run was active\n')
  const resumed = prepare(spec)
  assert.equal(resumed.reused, true)
  assert.equal(git(spec.checkout, 'rev-parse', 'HEAD').trim(), waveHead)
  assert.equal(readFileSync(join(spec.checkout, 'in-flight.txt'), 'utf8'), 'writer has not committed yet\n')
  assert.match(readFileSync(join(spec.checkout, 'WORK_QUEUE.md'), 'utf8'), /## Ready/)
  assert.equal(git(repo, 'rev-parse', 'HEAD').trim(), sourceHead)
  console.log('ok resume: reuses the same branch, completed commits, captured queue and uncommitted agent work')

  // Recover when preparation was interrupted after worktree creation, before copying ignored inputs.
  const saved = JSON.parse(readFileSync(spec.manifest, 'utf8'))
  saved.state = 'captured'; save(spec.manifest, saved)
  unlinkSync(join(spec.checkout, 'WORK_QUEUE.md'))
  unlinkSync(join(spec.checkout, 'saved.wave.md'))
  prepare(spec)
  assert.match(readFileSync(join(spec.checkout, 'WORK_QUEUE.md'), 'utf8'), /## Ready/, 'recovery uses captured input, not subsequently edited source')
  console.log('ok preparation recovery: captured control inputs restored from durable copies')

  // Capture metadata/branch exists, but worktree creation was interrupted before any dispatch.
  const missingSpec = { repo, checkout: join(root, 'missing checkout'), manifest: join(root, 'missing.json') }
  const missing = { ...manifest, state: 'captured', checkout: missingSpec.checkout, branch: 'codex/wave-auto-existing-branch' }
  git(repo, 'branch', missing.branch, missing.checkpoint)
  save(missingSpec.manifest, missing)
  const recovered = prepare(missingSpec)
  assert.equal(recovered.state, 'ready')
  assert.equal(git(missingSpec.checkout, 'rev-parse', 'HEAD').trim(), missing.checkpoint)
  assert.match(readFileSync(join(missingSpec.checkout, 'WORK_QUEUE.md'), 'utf8'), /## Ready/)
  console.log('ok recovery: attaches an existing checkpoint branch when its checkout is missing')

  // A killed worktree creation can leave a branch and registration but no directory.
  const staleSpec = { repo, checkout: join(root, 'stale checkout'), manifest: join(root, 'stale.json') }
  const stale = { ...manifest, state: 'captured', checkout: staleSpec.checkout, branch: 'codex/wave-auto-stale-registration' }
  git(repo, 'worktree', 'add', '-b', stale.branch, stale.checkout, stale.checkpoint)
  rmSync(stale.checkout, { recursive: true })
  save(staleSpec.manifest, stale)
  prepare(staleSpec)
  assert.equal(git(stale.checkout, 'rev-parse', 'HEAD').trim(), stale.checkpoint)
  assert.match(readFileSync(join(stale.checkout, 'WORK_QUEUE.md'), 'utf8'), /## Ready/)
  assert(existsSync(join(spec.checkout, 'in-flight.txt')), 'other run checkout remains intact')
  console.log('ok recovery: repairs only its own missing worktree registration and retains other checkouts')

  assert.throws(() => prepare({ ...spec, checkout: join(repo, 'unsafe') }), /outside/)
  assert.throws(() => prepare({ ...spec, copy: ['../outside'] }), /invalid copy/)
  assert.throws(() => prepare({ ...spec, manifest: join(root, 'other.json') }), /already exists/)
  console.log('ok destination guards: no nested checkout, path escape or overwrite')

  // SKILL.md runs the script as ~/.claude/skills/wave/prepare-auto.mjs, a symlinked directory.
  const skillLink = join(root, 'skill link')
  symlinkSync(dirname(fileURLToPath(import.meta.url)), skillLink)
  const cliSpec = join(root, 'cli spec.json')
  save(cliSpec, { repo, checkout: join(root, 'cli checkout'), manifest: join(root, 'cli.json') })
  const cli = spawnSync(process.execPath, [join(skillLink, 'prepare-auto.mjs'), cliSpec], { encoding: 'utf8' })
  assert.equal(cli.status, 0, cli.stderr)
  assert.equal(JSON.parse(cli.stdout).state, 'ready', 'run through a symlink, the script prints its manifest')
  console.log('ok symlinked invocation: runs and prints its JSON')
} finally {
  rmSync(root, { recursive: true, force: true })
}
