export const meta = {
  name: 'wave-lanes',
  description: 'Run a planned wave: test-first lanes with adversarial review, rolling cross-lane journeys, close open items, final gates',
  phases: [
    { title: 'Lanes', detail: 'each unit: test-first implement, adversarial review with revert-proofs, up to 2 fix rounds' },
    { title: 'Journeys', detail: 'cross-lane reviews start as soon as the lanes they cover land; a skeptic re-reproduces every finding; high and medium are fixed, lows go to Later' },
    { title: 'Close open items', detail: 'whatever the fix-round caps left; each starts once the lanes have landed and its own journeys are done' },
    { title: 'Final gates', detail: 'full gates on the quiet tree' },
  ],
}

// Generic runner for /wave. Everything project- or wave-specific arrives in `args`:
// {
//   wave: 'Wave 2026-09-25', repo, sp (run scratchpad), base (sha), waveDoc (path),
//   tickets: { 'DEAL-11': 'PROT-901', ... },            // one key per queue item
//   coAuthor: 'Co-Authored-By: ...',                    // last line of every commit
//   protocol: { shared, hot, method, snapshot, gates, reviewGates? }, // text blocks from the project's "## Wave protocol"
//     reviewGates (optional): per-unit reviews run these targeted gates instead of the full ones, and each lane
//     gets one full-gates run (lane-gates:<first unit>) after its last unit; a red one becomes an open item.
//   units: [{ id, lane, title, items: [...], deps: [...], implDeps: [...], files: [...], brief }],
//   lanes: [['U1a', 'U1b'], ['U2'], ...],               // units in a lane run in order
//   journeys: [{ key, title, units: [...], focus }],
//   seeds: { '<agent label>': <result> },               // continuation: labels already done return instantly
//   lean: true,                                          // /wave lean: test-first builders, then final gates; no reviews, lane gates,
//                                                        // journeys, close-outs or gate verifier (open items are reported, not closed)
//   units[].lean: true,     // risk-tiered run: a low-risk unit skips its own review; lane gates, journeys and final gates still cover it
//   units[].effort: 'max',  // this unit's builder, reviews and fixes run at this effort instead of the session's
//   units[].proto: path,    // a planning checker's prototype patch: the builder lands it test-first instead of re-deriving the fix
//   agentTypes: { builder: 'wave-builder', checker: 'wave-checker' },  // slim subagent types; absent → the default subagent
// }
// Per-agent values (ports) derive from the label, never from call order, so a continuation reproduces prompts.

const A = args
const REPO = A.repo
const SP = A.sp
const P = A.protocol
const T = A.tickets
const SEEDS = A.seeds || {}
const LEAN = !!A.lean

function port(label) {
  let h = 0
  for (const ch of label) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return 8100 + (h % 900)
}
// Agents that write code get the builder type; everyone else only reproduces, reviews or runs gates.
const BUILDER_ROLES = new Set(['impl', 'fix', 'jfix', 'close', 'final-gates'])
const ROLE_EFFORT = { 'lane-gates': 'medium' }   // runs the gates and sorts failures by lane: no design judgment
function run(label, prompt, opts) {
  if (SEEDS[label] !== undefined) { log(`${label}: seeded from an earlier run`); return Promise.resolve(SEEDS[label]) }
  const role = label.split(':')[0]
  const agentType = A.agentTypes && A.agentTypes[BUILDER_ROLES.has(role) ? 'builder' : 'checker']
  const effort = opts.effort || ROLE_EFFORT[role]
  return agent(`YOUR LABEL: ${label}. Use it, character for character, as your lock owner name and in every file name the rules ask you to create.\n\n${prompt}`, { ...opts, label, ...(agentType ? { agentType } : {}), ...(effort ? { effort } : {}) })
}

const QUOTE_RULE = `SHELL SAFETY (this run is unattended; one command stuck on a safety prompt deadlocks the whole wave): ALWAYS double-quote variables in rm/cp/mv paths ("$D/x.tsx", "\${VAR:?}"), prefer literal absolute paths, and never run a command that needs interactive approval. NEVER put rm, cp or mv inside a for/while loop or a pipeline, even with quoted "\${VAR:?}" paths: the safety check still stops a loop for approval, and nobody is awake to give it (two agents stalled 40-77 minutes on 2026-09-28, one of them on its final cleanup). Delete each snapshot with its own single command (\`rm -rf "\${SNAP:?}"\`), tear e2e snapshots down with e2e-snapshot.sh down, and refresh a snapshot by making a new one with snapshot.sh rather than syncing files into an old one.`

const TDD = `TEST-DRIVEN DEVELOPMENT (required for every slice; the reviewer fails a unit without the evidence):
1. RED: write the test first. Run it against the current code and SEE IT FAIL for the right reason (the behaviour is missing or wrong, not a typo, import or setup error). Save that output to ${SP}/tdd/<your label>-<slice>-red.txt.
2. GREEN: write the smallest production change that makes it pass. Save the passing output to ${SP}/tdd/<your label>-<slice>-green.txt.
3. REFACTOR with the tests green.
Tests call production code (never restate the production predicate inside the test), must fail when the fix is reverted, and every new constant or branch has a real consumer (no dead code that looks wired). Report every test in testsAdded with sawRedFirst and its red-output file.`

const DECIDE = `DECISIONS: whenever you must choose, decide and DOCUMENT it in the commit body and your report as the top two options and why you picked one. Do not stop to ask. If it truly needs a person, take the safe default, document it and add it to openQuestions. Mark product, design or wording decisions productFlavour=true: they go on the batch page for stakeholders.
If an instruction is impossible or wrong in the current code, do the closest correct thing and record the reasoned disagreement in deviationsFromBrief. That is a finding, not a failure.`

const COMMITS = `COMMIT MESSAGES (the user reads them): line 1 \`<TICKET>: <what changes for the user, plain words>\` (<= 72 chars). Blank line. Body: problem and root cause; what changed; the tests that prove it and that you saw them red first; decisions (top two options + why); what you deliberately left alone; pending human steps. Last line exactly: \`${A.coAuthor}\`. One commit per slice; key each commit to the ticket of the item it implements.
reviewPlan = numbered steps a human can follow in the running app: where to go, what to do, what they should see, what counts as a failure, regressions tests can't cover, anything deliberately left as-is. Say the code is on the local branch, unpushed, and name any prerequisite.`

const DEC = { type: 'object', properties: { question: { type: 'string' }, optionA: { type: 'string' }, optionB: { type: 'string' }, picked: { type: 'string' }, why: { type: 'string' }, productFlavour: { type: 'boolean' } }, required: ['question', 'optionA', 'optionB', 'picked', 'why', 'productFlavour'] }
const COMMIT = { type: 'object', properties: { sha: { type: 'string' }, ticket: { type: 'string' }, subject: { type: 'string' } }, required: ['sha', 'ticket', 'subject'] }
const GATE = { type: 'object', properties: { name: { type: 'string' }, exitCode: { type: 'string' }, summary: { type: 'string' } }, required: ['name', 'exitCode', 'summary'] }
const IMPL = { type: 'object', properties: {
  status: { type: 'string', enum: ['complete', 'partial', 'blocked'] },
  commits: { type: 'array', items: COMMIT },
  filesTouched: { type: 'array', items: { type: 'string' } },
  summary: { type: 'string' },
  userFacingChange: { type: 'string' },
  testsAdded: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, what: { type: 'string' }, sawRedFirst: { type: 'boolean' }, redOutputFile: { type: 'string' } }, required: ['file', 'what', 'sawRedFirst', 'redOutputFile'] } },
  decisions: { type: 'array', items: DEC },
  deviationsFromBrief: { type: 'array', items: { type: 'string' } },
  pendingHumanSteps: { type: 'array', items: { type: 'string' } },
  openQuestions: { type: 'array', items: { type: 'string' } },
  crossLaneNotes: { type: 'array', items: { type: 'string' } },
  reviewPlan: { type: 'array', items: { type: 'string' } },
  laterItems: { type: 'array', items: { type: 'string' } },
  incomplete: { type: 'array', items: { type: 'string' } },
}, required: ['status', 'commits', 'filesTouched', 'summary', 'userFacingChange', 'testsAdded', 'decisions', 'deviationsFromBrief', 'pendingHumanSteps', 'openQuestions', 'crossLaneNotes', 'reviewPlan', 'laterItems', 'incomplete'] }
const REVIEW = { type: 'object', properties: {
  verdict: { type: 'string', enum: ['pass', 'fail'] },
  mustFix: { type: 'array', items: { type: 'object', properties: { title: { type: 'string' }, file: { type: 'string' }, detail: { type: 'string' }, howToVerify: { type: 'string' } }, required: ['title', 'file', 'detail', 'howToVerify'] } },
  shouldFix: { type: 'array', items: { type: 'object', properties: { title: { type: 'string' }, detail: { type: 'string' } }, required: ['title', 'detail'] } },
  tddEvidence: { type: 'object', properties: { ok: { type: 'boolean' }, detail: { type: 'string' } }, required: ['ok', 'detail'] },
  revertProofs: { type: 'array', items: { type: 'object', properties: { test: { type: 'string' }, fixReverted: { type: 'string' }, wentRed: { type: 'boolean' }, note: { type: 'string' } }, required: ['test', 'fixReverted', 'wentRed', 'note'] } },
  reproduced: { type: 'array', items: { type: 'string' } },
  gates: { type: 'array', items: GATE },
  notes: { type: 'string' },
}, required: ['verdict', 'mustFix', 'shouldFix', 'tddEvidence', 'revertProofs', 'reproduced', 'gates', 'notes'] }
const FIX = { type: 'object', properties: {
  commits: { type: 'array', items: COMMIT },
  fixed: { type: 'array', items: { type: 'object', properties: { title: { type: 'string' }, how: { type: 'string' }, redOutputFile: { type: 'string' } }, required: ['title', 'how', 'redOutputFile'] } },
  notFixed: { type: 'array', items: { type: 'object', properties: { title: { type: 'string' }, why: { type: 'string' } }, required: ['title', 'why'] } },
  decisions: { type: 'array', items: DEC },
  reviewPlanAdditions: { type: 'array', items: { type: 'object', properties: { ticket: { type: 'string' }, step: { type: 'string' } }, required: ['ticket', 'step'] } },
  summary: { type: 'string' },
}, required: ['commits', 'fixed', 'notFixed', 'decisions', 'reviewPlanAdditions', 'summary'] }
const FINDINGS = { type: 'object', properties: {
  findings: { type: 'array', items: { type: 'object', properties: {
    title: { type: 'string' }, severity: { type: 'string', enum: ['high', 'medium', 'low'] }, ticket: { type: 'string' },
    files: { type: 'array', items: { type: 'string' } }, evidence: { type: 'string' }, reproduction: { type: 'string' }, suggestedFix: { type: 'string' },
  }, required: ['title', 'severity', 'ticket', 'files', 'evidence', 'reproduction', 'suggestedFix'] } },
  checkedAndFine: { type: 'array', items: { type: 'string' } },
}, required: ['findings', 'checkedAndFine'] }
const VERDICT = { type: 'object', properties: { real: { type: 'boolean' }, severity: { type: 'string', enum: ['high', 'medium', 'low'] }, reproducedHow: { type: 'string' }, reasoning: { type: 'string' } }, required: ['real', 'severity', 'reproducedHow', 'reasoning'] }
const VERIFY = { type: 'object', properties: {
  resolved: { type: 'boolean' },
  remaining: { type: 'array', items: { type: 'object', properties: { title: { type: 'string' }, detail: { type: 'string' }, severity: { type: 'string', enum: ['high', 'medium', 'low'] }, productCall: { type: 'boolean' } }, required: ['title', 'detail', 'severity', 'productCall'] } },
  revertProof: { type: 'string' }, gates: { type: 'array', items: GATE }, notes: { type: 'string' },
}, required: ['resolved', 'remaining', 'revertProof', 'gates', 'notes'] }
const GATES = { type: 'object', properties: {
  gates: { type: 'array', items: GATE }, allGreen: { type: 'boolean' },
  failuresFixed: { type: 'array', items: { type: 'object', properties: { what: { type: 'string' }, commit: { type: 'string' } }, required: ['what', 'commit'] } },
  remainingFailures: { type: 'array', items: { type: 'string' } }, notes: { type: 'string' },
}, required: ['gates', 'allGreen', 'failuresFixed', 'remainingFailures', 'notes'] }

const UNIT = {}
for (const u of A.units) UNIT[u.id] = { deps: [], implDeps: [], files: [], ...u }
// Refuse to start on a typo: an unknown ID would silently start a unit early or never review a lane.
const problems = []
const inLanes = A.lanes.flat()
for (const id of inLanes) if (!UNIT[id]) problems.push(`lane lists unknown unit ${id}`)
for (const u of Object.values(UNIT)) {
  if (!inLanes.includes(u.id)) problems.push(`unit ${u.id} is in no lane`)
  if (inLanes.filter(x => x === u.id).length > 1) problems.push(`unit ${u.id} is in more than one lane`)
  for (const d of u.deps.concat(u.implDeps)) if (!UNIT[d]) problems.push(`unit ${u.id} waits on unknown unit ${d}`)
  for (const i of u.items) if (!T[i]) problems.push(`unit ${u.id} item ${i} has no entry in tickets`)
}
for (const j of A.journeys || []) for (const id of j.units) if (!UNIT[id]) problems.push(`journey ${j.key} covers unknown unit ${id}`)
// A unit waits on its lane predecessor and on its deps; a cycle would hang the run forever.
const waitsOn = {}
for (const id of Object.keys(UNIT)) waitsOn[id] = UNIT[id].deps.concat(UNIT[id].implDeps).filter(d => UNIT[d])
for (const lane of A.lanes) lane.forEach((id, k) => { if (k > 0 && waitsOn[id]) waitsOn[id].push(lane[k - 1]) })
const state = {}
function visit(id, path) {
  if (state[id] === 2) return
  if (state[id] === 1) { problems.push(`dependency cycle: ${path.concat(id).join(' -> ')}`); return }
  state[id] = 1
  for (const d of waitsOn[id] || []) visit(d, path.concat(id))
  state[id] = 2
}
for (const id of Object.keys(UNIT)) visit(id, [])
if (problems.length) throw new Error('wave args invalid:\n- ' + problems.join('\n- '))
function deferred() { let r; const p = new Promise(res => { r = res }); return { p, r } }
const done = {}
const implDone = {}
for (const id of Object.keys(UNIT)) { done[id] = deferred(); implDone[id] = deferred() }
const leftovers = []
const jDone = {}
for (const j of A.journeys || []) jDone[j.key] = deferred()
const lanesLanded = deferred()
const closing = []
function openItem(item) {
  leftovers.push(item)
  if (!LEAN) closing.push(closeOut(item).catch(e => ({ item, error: String(e) })))
}
// Lows and product calls never hold a fix loop open: lows become ## Later entries, product calls go on the batch page.
const later = []
const productCalls = []
const blocking = v => ((v && v.remaining) || []).filter(r => !r.productCall && r.severity !== 'low')
const settled = v => !!v && (v.resolved || ((v.remaining || []).length > 0 && blocking(v).length === 0))
function harvest(v, source) {
  const unsettled = !settled(v)
  for (const r of (v && v.remaining) || []) {
    if (unsettled && !r.productCall && r.severity !== 'low') continue
    const to = r.productCall ? productCalls : later
    if (!to.some(x => x.title === r.title)) to.push({ source, ...r })
  }
}
const REMAINING = `List in remaining everything still wrong or newly broken, each with: severity (high, medium or low, graded honestly); productCall = true when it needs a product, design or wording decision from a person rather than a code fix; detail = how to reproduce it. Missing red-first evidence or a red gate is a high item. A low or a product call never makes resolved false: the runner queues lows for a later wave and puts product calls on the batch page.`
// Verifiers after a fix run the targeted gates when the protocol has them; the final gates run the full suite once at the end.
const VERIFY_GATES = P.reviewGates ? 'Run the REVIEW GATES below (targeted to what the fix touched; the final gates run the full suite at the end) in the snapshot and quote exit codes.' : 'Run the full gates in the snapshot and quote exit codes.'
const VGATES = P.reviewGates || P.gates

function ticketsOf(u) { return u.items.map(i => `${i} = ${T[i] || '(no ticket)'}`).join(', ') }
function brief(u) {
  return `UNIT ${u.id} (lane ${u.lane}): ${u.title}\nTickets: ${ticketsOf(u)}. Queue entries: ${u.items.map(i => `"### ${i} — ..."`).join(', ')} in ${REPO}/WORK_QUEUE.md (READ-ONLY).\nBRIEF AND BINDING CALLS:\n${u.brief}`
}
function protoNote(u) {
  return u.proto ? `\nPROTOTYPE: a planning checker already built and ran a candidate fix for this unit: ${u.proto} (a git diff against the plan's base, tests included). Land it rather than re-deriving it: apply only its test files first (git apply --include=<each test path>), run them and save YOUR red output, then apply the rest and go green. If it no longer applies cleanly, port it by hand. It is a head start, not the spec: the queue entry and the binding calls win, and every anchor still gets verified.\n` : ''
}
function history(results) {
  const lines = results.filter(Boolean).map(r => {
    const commits = [].concat(r.impl ? r.impl.commits : [], ...(r.fixes || []).filter(Boolean).map(f => f.commits || []))
    return `- ${r.unit} (${r.title}): ${r.impl ? r.impl.summary : 'implementer returned nothing'}\n  commits: ${commits.map(c => c.sha.slice(0, 10) + ' ' + c.subject).join(' | ')}`
  })
  return lines.length ? lines.join('\n') : '(none)'
}

function implPrompt(u, laneHist, depHist, label) {
  return `You are implementing one unit of ${A.wave} in ${REPO}, as one of up to 16 agents working IN PARALLEL in the SAME checkout. The user kicked this wave off with /wave: ultracode quality, test-driven development, no shortcuts.

${brief(u)}
${protoNote(u)}
EARLIER UNITS IN YOUR LANE (already committed):
${laneHist}

UNITS YOU WAITED ON (already committed):
${depHist}

Read ${A.waveDoc} first: its protocol, your lane's row and your lane's calls. The calls are BINDING. Your spec is the queue entry named above (Now / Want / Done when / By hand / Notes / any 🔴 Decision open, built with its recommended answer). Verify every anchor against the code; a named symbol can be wrong.

${P.shared}

${P.hot || ''}

${P.method || ''}

${TDD}

${DECIDE}

${COMMITS}

Your port, if you need one: ${port(label)}. If it is in use, pick any free port between 8100 and 8999.

${QUOTE_RULE}

When finished, return through StructuredOutput.`
}

function reviewPrompt(u, impl, shas, round, prevReview, fixes) {
  const prior = prevReview ? `\nTHIS IS VERIFICATION ROUND ${round}. The previous mustFix list was:\n${JSON.stringify(prevReview.mustFix, null, 1)}\nThe fixer reported:\n${JSON.stringify((fixes || []).filter(Boolean).map(f => ({ fixed: f.fixed, notFixed: f.notFixed, commits: f.commits })), null, 1)}\nConfirm each item is truly resolved (reproduce it, revert-proof every new test) and look for regressions the fix introduced. New mustFix only for real defects.\n` : ''
  return `You are the ADVERSARIAL REVIEWER for one unit of ${A.wave}. You did NOT write this code. Find what is wrong by REPRODUCING it, not by reading it: in past waves 10-15 of every 26 units failed their first review while their tests were green.

${brief(u)}

COMMITS UNDER REVIEW (local, unpushed): ${shas.join(', ')}
IMPLEMENTER'S REPORT: ${JSON.stringify({ status: impl.status, summary: impl.summary, userFacingChange: impl.userFacingChange, testsAdded: impl.testsAdded, decisions: impl.decisions, deviationsFromBrief: impl.deviationsFromBrief, incomplete: impl.incomplete }, null, 1)}
${prior}
DO ALL OF THIS:
1. TDD EVIDENCE: for every test in testsAdded, and every fixer's fixed[].redOutputFile, read the red-output file under ${SP}/tdd/ and confirm it failed for the RIGHT reason before the fix. Missing or wrong-reason red output is a mustFix ("show the test failing against the pre-fix code"). Set tddEvidence.
2. REVERT-PROOF: in your snapshot, revert each production fix, prove its test goes red, then restore.
3. REPRODUCE the user-visible behaviour the entry describes, end to end, and trace each fix to what the user sees.
4. Check the two shapes we keep writing: a test that restates the production predicate instead of calling it, and dead code that looks wired.
5. ${P.reviewGates ? 'Run the REVIEW GATES below (targeted to this unit; the full gates run once per lane and again at the end)' : 'Run the full gates'} in your snapshot, each redirected to a file, and quote exit codes.

${P.snapshot}

${P.reviewGates || P.gates}

${QUOTE_RULE}

verdict = fail only for real defects (mustFix). Return through StructuredOutput.`
}

function laneGatesPrompt(ids, results) {
  return `${CONTEXT}\n\nYou are the LANE GATE KEEPER for lane ${UNIT[ids[0]].lane} (units ${ids.join(', ')}). Each unit's review ran targeted tests only; you run the FULL gates once for the whole lane. Do not fix or commit anything.\n\nTHIS LANE'S COMMITS:\n${history(results)}\n\nMake a snapshot of HEAD and run every gate below, each redirected to a file, quoting exit codes and totals. For each failure, find its cause. A failure this lane's commits caused is a high item in remaining, with the failing test and the commit. A failure outside this lane's files is probably another lane mid-edit: re-run it once in a fresh snapshot of the then-HEAD and report it only if it still fails, naming the commit that broke it. resolved = true only if every gate is green, or every remaining failure is another lane's work in flight. ${REMAINING}\n\n${P.snapshot}\n\n${P.gates}\n\n${QUOTE_RULE}\n\nReturn through StructuredOutput.`
}

function fixPrompt(u, impl, review, round) {
  return `You are the FIXER for one unit of ${A.wave}, working in the SHARED checkout ${REPO} alongside other agents. An adversarial reviewer found defects. Fix every mustFix item at its ROOT, where all callers route, with a test that goes red without the fix.

${brief(u)}

IMPLEMENTER'S COMMITS: ${impl.commits.map(c => c.sha.slice(0, 10) + ' ' + c.subject).join(' | ')}
REVIEW (round ${round}), mustFix:
${JSON.stringify(review.mustFix, null, 1)}
shouldFix (only if cheap and clearly right):
${JSON.stringify(review.shouldFix, null, 1)}
Reviewer notes: ${review.notes}

${P.shared}

${P.hot || ''}

${TDD}

${DECIDE}

${COMMITS}

${QUOTE_RULE}

Return through StructuredOutput.`
}

async function runUnit(u, laneResults) {
  const implDeps = await Promise.all(u.implDeps.filter(d => implDone[d]).map(d => implDone[d].p))
  const deps = await Promise.all(u.deps.filter(d => done[d]).map(d => done[d].p))
  log(`${u.id} starting: ${u.title}`)
  const phaseName = 'Lanes'
  const eff = u.effort ? { effort: u.effort } : {}
  const implLabel = `impl:${u.id}`
  const impl = await run(implLabel, implPrompt(u, history(laneResults), history(deps.concat(implDeps)), implLabel), { phase: phaseName, schema: IMPL, ...eff })
  const result = { unit: u.id, title: u.title, items: u.items, lane: u.lane, impl, reviews: [], fixes: [] }
  implDone[u.id].r(result)
  if (!impl || !impl.commits || impl.commits.length === 0) {
    log(`${u.id}: implementer produced no commits (${impl ? impl.status : 'null'})`)
    openItem({ unit: u.id, items: u.items, tickets: u.items.map(i => T[i]), kind: 'no-commits', detail: impl ? (impl.incomplete || []).concat(impl.deviationsFromBrief || []) : ['implementer returned nothing'], files: u.files })
    return result
  }
  if (LEAN || u.lean) { log(`${u.id} built (lean: no review)`); return result }
  let shas = impl.commits.map(c => c.sha)
  let review = await run(`review:${u.id}`, reviewPrompt(u, impl, shas, 1, null, null), { phase: phaseName, schema: REVIEW, ...eff })
  result.reviews.push(review)
  let round = 1
  while (review && review.verdict === 'fail' && review.mustFix.length > 0 && round <= 2) {
    const fix = await run(`fix:${u.id}#${round}`, fixPrompt(u, impl, review, round), { phase: phaseName, schema: FIX, ...eff })
    result.fixes.push(fix)
    if (fix && fix.commits) shas = shas.concat(fix.commits.map(c => c.sha))
    round++
    const prev = review
    review = await run(`verify:${u.id}#${round}`, reviewPrompt(u, impl, shas, round, prev, result.fixes), { phase: phaseName, schema: REVIEW, ...eff })
    result.reviews.push(review)
  }
  const final = result.reviews[result.reviews.length - 1]
  if (final && final.verdict === 'fail' && final.mustFix.length) {
    openItem({ unit: u.id, items: u.items, tickets: u.items.map(i => T[i]), kind: 'review-cap', mustFix: final.mustFix, notes: final.notes, shas, files: u.files })
  }
  log(`${u.id} done: review ${final ? final.verdict : 'n/a'} after ${result.reviews.length} review(s), ${result.fixes.length} fix pass(es)`)
  return result
}

async function runLane(ids) {
  const out = []
  for (const id of ids) {
    let r = null
    try { r = await runUnit(UNIT[id], out) } catch (e) {
      r = { unit: id, title: UNIT[id].title, items: UNIT[id].items, error: String(e) }
      implDone[id].r(r)
      openItem({ unit: id, items: UNIT[id].items, tickets: UNIT[id].items.map(i => T[i]), kind: 'error', detail: [String(e)], files: UNIT[id].files })
    }
    done[id].r(r)
    out.push(r)
  }
  if (P.reviewGates && !LEAN) {
    const key = ids[0]
    const ver = await run(`lane-gates:${key}`, laneGatesPrompt(ids, out), { phase: 'Lanes', schema: VERIFY })
    harvest(ver, key)
    if (!settled(ver)) {
      const items = ids.flatMap(id => UNIT[id].items)
      openItem({ unit: key, items, tickets: items.map(i => T[i]), kind: 'lane-gates', mustFix: (ver ? blocking(ver) : [{ title: 'lane gates did not report', detail: 'the lane gate keeper returned nothing' }]).map(r => ({ title: r.title, file: '', detail: r.detail, howToVerify: '' })), files: ids.flatMap(id => UNIT[id].files) })
    }
  }
  return out
}

// A fix batch claims its files so two fixers never write the same file at once.
const held = new Map()
async function withFiles(files, fn) {
  const fs = Array.from(new Set((files || []).filter(Boolean)))
  while (true) {
    const busy = fs.filter(f => held.has(f))
    if (!busy.length) break
    await Promise.race(busy.map(f => held.get(f)))
  }
  let release
  const p = new Promise(r => { release = r })
  fs.forEach(f => held.set(f, p))
  try { return await fn() } finally { fs.forEach(f => held.delete(f)); release() }
}
function ownersOf(files) {
  const owners = new Set()
  for (const f of files) for (const u of Object.values(UNIT)) if (u.files.some(k => f.includes(k))) owners.add(u.id)
  return Array.from(owners)
}

const CONTEXT = `CONTEXT: ${A.wave} is landing on the LOCAL branch (unpushed) in ${REPO} since ${A.base}; \`git -C ${REPO} log --oneline ${A.base}..HEAD\` lists every commit, and each message documents its change and decisions. Tickets: ${Object.keys(T).map(k => `${k}=${T[k]}`).join(', ')}. Plan and binding calls: ${A.waveDoc}. Specs: the matching "### <ID>" entries in ${REPO}/WORK_QUEUE.md (READ-ONLY). Other lanes may still be committing while you work.`
const FIX_RULES = `RULES FOR WRITING IN THE SHARED CHECKOUT:
${P.shared}
${P.hot || ''}
Before editing a file, check it for uncommitted changes you did not make; if it has some, another agent is mid-edit: leave it and list the item in notFixed as "owned by a running lane: <file>".
${TDD}
${DECIDE}
${COMMITS}
${QUOTE_RULE}`

function jPrompt(j) {
  return `${CONTEXT}\n\nYou are a CROSS-LANE ADVERSARIAL REVIEWER for journey ${j.key} "${j.title}". Each unit was already reviewed on its own; your job is the defects that appear where lanes COMPOSE, plus anything the per-unit reviews missed. In past waves this pass found 34-39 real defects each time. Find real user-visible or data-integrity defects, not style.\n\nFOCUS:\n${j.focus}\n\n${P.snapshot}\n\nREPRODUCE every finding (a throwaway test, a browser script in an isolated snapshot, or a precise trace through production code when a test is impractical). List what you checked and found fine.\n\n${QUOTE_RULE}\n\nReturn through StructuredOutput.`
}
function skepticPrompt(f, j) {
  return `${CONTEXT}\n\nYou are a SKEPTICAL VERIFIER. A cross-lane reviewer (journey ${j.key} "${j.title}") reported the finding below. Try to REFUTE it: reproduce it yourself from scratch against current code. real = true only if you reproduced the harm yourself. Re-grade severity honestly. Default to real = false when you cannot reproduce it.\n\nFINDING:\n${JSON.stringify(f, null, 1)}\n\n${P.snapshot}\n\n${QUOTE_RULE}\n\nReturn through StructuredOutput.`
}
function jFixPrompt(j, confirmed, round, prevVerify) {
  return `${CONTEXT}\n\nYou are the FIXER for confirmed cross-lane defects from journey ${j.key} "${j.title}". Each was reproduced by a reviewer AND independently by a skeptic, and each is high or medium. Fix every one at its root with a test that goes red without the fix. Lows from this journey are queued for a later wave: do not fix them here.\n${prevVerify ? `\nThis is fix round ${round}; the verifier says:\n${JSON.stringify(prevVerify, null, 1)}\n` : ''}\nCONFIRMED FINDINGS:\n${JSON.stringify(confirmed.map(f => ({ title: f.title, severity: f.verdict.severity, ticket: f.ticket, files: f.files, evidence: f.evidence, reproduction: f.reproduction, suggestedFix: f.suggestedFix })), null, 1)}\n\n${FIX_RULES}\n\nReturn through StructuredOutput.`
}
function jVerifyPrompt(j, confirmed, fix) {
  return `${CONTEXT}\n\nYou are an INDEPENDENT VERIFIER for cross-lane fixes from journey ${j.key} "${j.title}". For each finding, reproduce the original scenario against the new code and confirm the harm is gone by every path you can find; read each fixer's red-output file (fixed[].redOutputFile) and confirm it failed for the right reason; revert-proof each new test in your snapshot. Missing red-first evidence means resolved = false. ${VERIFY_GATES} resolved = true only if every finding is gone and nothing high or medium regressed. ${REMAINING}\n\nFINDINGS:\n${JSON.stringify(confirmed.map(f => ({ title: f.title, reproduction: f.reproduction })), null, 1)}\nFIXER'S REPORT:\n${JSON.stringify(fix, null, 1)}\n\n${P.snapshot}\n\n${VGATES}\n\n${QUOTE_RULE}\n\nReturn through StructuredOutput.`
}

async function runJourney(j) {
  await Promise.all(j.units.filter(id => done[id]).map(id => done[id].p))
  log(`${j.key} ${j.title}: its lanes have landed, starting the journey review`)
  const found = await run(`journey:${j.key}`, jPrompt(j), { phase: 'Journeys', schema: FINDINGS })
  const findings = (found && found.findings) || []
  const verdicts = await parallel(findings.map((f, i) => () => run(`skeptic:${j.key}#${i + 1}`, skepticPrompt(f, j), { phase: 'Journeys', schema: VERDICT }).then(v => ({ ...f, journey: j.key, verdict: v }))))
  const judged = verdicts.filter(Boolean)
  const real = judged.filter(f => f.verdict && f.verdict.real)
  const confirmed = real.filter(f => f.verdict.severity !== 'low')
  for (const f of real) if (f.verdict.severity === 'low') later.push({ source: j.key, title: f.title, severity: 'low', productCall: false, ticket: f.ticket, detail: `${f.reproduction}\nEvidence: ${f.evidence}\nFiles: ${(f.files || []).join(', ')}\nSuggested fix: ${f.suggestedFix}` })
  log(`${j.key}: ${findings.length} findings, ${real.length} confirmed by a skeptic, ${confirmed.length} high or medium to fix now`)
  const out = { journey: j.key, title: j.title, checkedAndFine: (found && found.checkedAndFine) || [], findings: judged, fixes: [], verifies: [] }
  if (!confirmed.length) return out
  const files = confirmed.flatMap(f => f.files || [])
  const owners = ownersOf(files).filter(id => !j.units.includes(id))
  if (owners.length) { log(`${j.key}: fix waits for lanes still owning its files: ${owners.join(', ')}`); await Promise.all(owners.map(id => done[id].p)) }
  let ver = null
  for (let round = 1; round <= 2; round++) {
    const fix = await withFiles(files, () => run(`jfix:${j.key}#${round}`, jFixPrompt(j, confirmed, round, ver && { ...ver, remaining: blocking(ver) }), { phase: 'Journeys', schema: FIX }))
    out.fixes.push(fix)
    ver = await run(`jverify:${j.key}#${round}`, jVerifyPrompt(j, confirmed, fix), { phase: 'Journeys', schema: VERIFY })
    out.verifies.push(ver)
    if (settled(ver)) break
  }
  harvest(ver, j.key)
  if (!settled(ver)) {
    openItem({ unit: j.key, items: [], tickets: Array.from(new Set(confirmed.map(f => f.ticket))), kind: 'journey', mustFix: blocking(ver).map(r => ({ title: r.title, file: '', detail: r.detail, howToVerify: '' })), files })
  }
  return out
}

// A close-out starts as soon as its item exists, once every lane has landed and every journey covering its unit is done.
// withFiles keeps it off files a journey fixer or another close-out is writing.
async function closeOut(item) {
  await lanesLanded.p
  await Promise.all((A.journeys || []).filter(j => j.units.includes(item.unit)).map(j => jDone[j.key].p))
  return withFiles(item.files || [], async () => {
    const fixes = []
    let ver = null
    for (let round = 1; round <= 2; round++) {
      const fix = await run(`close:${item.unit}:${item.kind}#${round}`, `${CONTEXT}\n\nEvery lane has landed. Journey fixers and other close-out fixers may still be committing, never on this item's files. Close this OPEN ITEM (kind: ${item.kind}) at the ROOT, with a test that reproduces the exact scenario through production code, red first.\n\nOPEN ITEM:\n${JSON.stringify(item, null, 1)}\n${ver ? `\nYour previous round did not resolve it. The verifier says:\n${JSON.stringify({ ...ver, remaining: blocking(ver) }, null, 1)}\n` : ''}\n${FIX_RULES}\n\nReturn through StructuredOutput.`, { phase: 'Close open items', schema: FIX })
      fixes.push(fix)
      ver = await run(`close-verify:${item.unit}:${item.kind}#${round}`, `${CONTEXT}\n\nYou are an INDEPENDENT VERIFIER. An open item was reported fixed; prove or disprove it by REPRODUCING the scenario against the new code, read the fixer's red-output files and confirm each failed for the right reason, and revert-proof each new test in a snapshot. Missing red-first evidence means resolved = false. ${VERIFY_GATES}\n\nOPEN ITEM:\n${JSON.stringify(item, null, 1)}\nFIXER'S REPORT:\n${JSON.stringify(fix, null, 1)}\n\n${P.snapshot}\n\n${VGATES}\n\n${QUOTE_RULE}\n\nresolved = true only if the high and medium harm is gone by every path you can find. ${REMAINING} Return through StructuredOutput.`, { phase: 'Close open items', schema: VERIFY })
      if (settled(ver)) break
    }
    harvest(ver, item.unit)
    return { item, fixes, verdict: ver }
  })
}

phase('Lanes')
const lanePromise = parallel(A.lanes.map(ids => () => runLane(ids)))
const journeyPromise = parallel((LEAN ? [] : A.journeys || []).map(j => () => runJourney(j).finally(() => jDone[j.key].r())))
const laneResults = (await lanePromise).filter(Boolean).flat()
lanesLanded.r()
const journeyResults = (await journeyPromise).filter(Boolean)

phase('Close open items')
if (leftovers.length) log(`${leftovers.length} open items left after the review caps; each close-out started as soon as it could`)
const closeResults = await Promise.all(closing)

phase('Final gates')
const gates = await run('final-gates', `${CONTEXT}\n\nEvery lane, journey and close-out fix has finished. You are the FINAL GATE KEEPER; no other agent is writing now.\n1. \`git -C ${REPO} status --porcelain\`: report anything uncommitted. If a stray file obviously belongs to one of this wave's commits, add it in a documented commit; otherwise leave it and report it.\n2. \`${SP}/wave/lock.sh status\` must show no locks; report any.\n3. Run the full gates IN THE SHARED TREE, each redirected to a file, quoting exit codes and totals:\n${P.gates}\n4. Fix any failure at its root with a documented commit (test red first), then re-run that gate. A stale test's premise gets fixed, never deleted.\n\n${FIX_RULES}\n\nReturn through StructuredOutput.`, { phase: 'Final gates', schema: GATES })

const gateFixes = (gates && gates.failuresFixed) || []
const gateVerify = gateFixes.length && !LEAN ? await run('final-gates-verify', `${CONTEXT}\n\nYou are an INDEPENDENT VERIFIER. The final gate keeper fixed these failures with new commits:\n${JSON.stringify(gateFixes, null, 1)}\nFor each: read the commit, confirm a test was written first and seen failing for the right reason (its red-output file under ${SP}/tdd/), revert-proof it in a snapshot, and confirm the fix is at the root, not a weakened test. Then run the full gates in the snapshot and quote exit codes.\n\n${P.snapshot}\n\n${P.gates}\n\n${QUOTE_RULE}\n\nresolved = true only if every fix holds. Return through StructuredOutput.`, { phase: 'Final gates', schema: VERIFY }) : null

return {
  units: laneResults.map(r => ({ unit: r.unit, title: r.title, items: r.items, lane: r.lane, lean: LEAN || !!(UNIT[r.unit] && UNIT[r.unit].lean), error: r.error || null, impl: r.impl || null, finalVerdict: r.reviews && r.reviews.length ? (r.reviews[r.reviews.length - 1] || {}).verdict : null, reviews: r.reviews || [], fixes: r.fixes || [] })),
  journeys: journeyResults,
  leftovers,
  closeResults,
  later,
  productCalls,
  gates,
  gateVerify,
}
