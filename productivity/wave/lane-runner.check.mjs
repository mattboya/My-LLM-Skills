import { readFileSync } from 'node:fs'
// Run: node ~/.agents/skills/wave/lane-runner.check.mjs  (stub agents; proves the control flow after any runner edit)
const src = readFileSync(new URL('./lane-runner.js', import.meta.url), 'utf8').replace(/^export const meta/m, 'const meta')
const body = new Function('args', 'agent', 'parallel', 'log', 'phase', `return (async () => {\n${src}\n})()`)
const calls = []
const reviewCount = {}
const prompts = {}, started = {}, ended = {}, optsOf = {}
const sev = p => p.includes('"severity": "low"') ? 'low' : p.includes('"severity": "medium"') ? 'medium' : 'high'
const find = (t, severity, file) => ({ title: t, severity, ticket: 'T', files: [file], evidence: '', reproduction: 'r', suggestedFix: '' })
const JOURNEY_FINDINGS = { J1: [find('J1-low', 'low', 'a.ts'), find('J1-high', 'high', 'a.ts')], J2: [find('J2-high', 'high', 'c.ts'), find('J2-downgraded', 'medium', 'c.ts')], J3: [find('J3-low', 'low', 'b.ts')], J4: [find('J4-medium', 'medium', 'd.ts')], J5: [] }
const rem = (title, severity, productCall) => ({ title, detail: 'd', severity, productCall })
let leanStub = false   // the lean run: U3's builder commits nothing, and final gates fix one failure
async function agent(prompt, opts) {
  const l = opts.label; calls.push(l); prompts[l] = prompt; optsOf[l] = opts; started[l] = performance.now()
  await new Promise(r => setTimeout(r, l === 'journey:J5' ? 400 : /:U3\b/.test(l) ? 20 : 5))   // U3 is the slow lane, J5 the slow journey
  ended[l] = performance.now()
  if (leanStub && l === 'impl:U3') return { status: 'blocked', commits: [], filesTouched: [], summary: l, userFacingChange: '', testsAdded: [], decisions: [], deviationsFromBrief: [], pendingHumanSteps: [], openQuestions: [], crossLaneNotes: [], reviewPlan: [], laterItems: [], incomplete: ['could not build'] }
  if (leanStub && l === 'final-gates') return { gates: [], allGreen: true, failuresFixed: [{ what: 'lint', commit: 'g1' }], remainingFailures: [], notes: '' }
  if (l.startsWith('impl:')) return { status: 'complete', commits: [{ sha: 'abc' + l, ticket: 'T', subject: l }], filesTouched: [], summary: l, userFacingChange: '', testsAdded: [], decisions: [], deviationsFromBrief: [], pendingHumanSteps: [], openQuestions: [], crossLaneNotes: [], reviewPlan: [], laterItems: [], incomplete: [] }
  if (l.startsWith('review:') || l.startsWith('verify:')) {
    const u = l.split(':')[1].split('#')[0]; reviewCount[u] = (reviewCount[u] || 0) + 1
    const fail = (u === 'U1' && reviewCount[u] < 3) || u === 'U3'   // U1 fails twice then passes; U3 never passes
    return { verdict: fail ? 'fail' : 'pass', mustFix: fail ? [{ title: 'bug', file: 'f', detail: 'd', howToVerify: 'h' }] : [], shouldFix: [], tddEvidence: { ok: true, detail: '' }, revertProofs: [], reproduced: [], gates: [], notes: '' }
  }
  if (l.startsWith('fix:') || l.startsWith('jfix:') || l.startsWith('close:')) return { commits: [{ sha: 'fix' + l, ticket: 'T', subject: l }], fixed: [], notFixed: [], decisions: [], reviewPlanAdditions: [], summary: '' }
  if (l.startsWith('journey:')) return { findings: JOURNEY_FINDINGS[l.slice(8)], checkedAndFine: [] }
  if (l.startsWith('skeptic:')) return { real: true, severity: prompt.includes('J2-downgraded') ? 'low' : sev(prompt), reproducedHow: '', reasoning: '' }
  // J1's first verify leaves only a low and a product call (settled); J4's never settles (a medium stays)
  if (l === 'jverify:J1#1') return { resolved: false, remaining: [rem('new low', 'low', false), rem('ask Ed', 'medium', true)], revertProof: '', gates: [], notes: '' }
  if (l.startsWith('jverify:J4#')) return { resolved: false, remaining: [rem('still broken', 'medium', false), rem('J4 side low', 'low', false)], revertProof: '', gates: [], notes: '' }
  if (l.startsWith('jverify:') || l.startsWith('close-verify:')) return { resolved: true, remaining: [], revertProof: '', gates: [], notes: '' }
  if (l === 'final-gates-verify') return { resolved: true, remaining: [], revertProof: '', gates: [], notes: '' }
  if (l === 'final-gates') return { gates: [], allGreen: true, failuresFixed: [], remainingFailures: [], notes: '' }
  if (l === 'lane-gates:U1') return { resolved: false, remaining: [rem('lane red', 'high', false), rem('lane low', 'low', false)], revertProof: '', gates: [], notes: '' }   // L1's full gates go red
  if (l.startsWith('lane-gates:')) return { resolved: true, remaining: [], revertProof: '', gates: [], notes: '' }
  throw new Error('unexpected label ' + l)
}
async function parallel(thunks) { return Promise.all(thunks.map(t => t().catch(() => null))) }
const args = {
  wave: 'Sim', repo: '/r', sp: '/sp', base: 'b0', waveDoc: '/r/w.md', tickets: { A: 'T-1', B: 'T-2', C: 'T-3' }, coAuthor: 'Co-Authored-By: x',
  protocol: { shared: 'S', hot: '', method: '', snapshot: 'SN', gates: 'G' },
  units: [ { id: 'U1', lane: 'L1', title: 'one', items: ['A'], files: ['a.ts'], brief: 'b' }, { id: 'U2', lane: 'L1', title: 'two', items: ['B'], brief: 'b' },
           { id: 'U3', lane: 'L2', title: 'three', items: ['C'], deps: ['U1'], files: ['c.ts'], brief: 'b' } ],
  lanes: [['U1', 'U2'], ['U3']],
  journeys: [{ key: 'J1', title: 'j', units: ['U1', 'U2'], focus: 'f' }, { key: 'J2', title: 'j', units: ['U3'], focus: 'f' }, { key: 'J3', title: 'j', units: ['U2'], focus: 'f' },
             { key: 'J4', title: 'j', units: ['U1'], focus: 'f' }, { key: 'J5', title: 'j', units: ['U2'], focus: 'f' }],
  seeds: { 'impl:U2': { status: 'complete', commits: [{ sha: 'seeded', ticket: 'T-2', subject: 's' }], filesTouched: [], summary: 'seeded', userFacingChange: '', testsAdded: [], decisions: [], deviationsFromBrief: [], pendingHumanSteps: [], openQuestions: [], crossLaneNotes: [], reviewPlan: [], laterItems: [], incomplete: [] } },
}
const logs = []
const out = await body(args, agent, parallel, m => logs.push(m), () => {})
const idx = l => calls.indexOf(l)
const assert = (c, m) => { if (!c) { console.log('FAIL', m); process.exitCode = 1 } else console.log('ok  ', m) }
assert(!calls.includes('impl:U2'), 'seeded impl:U2 not re-run')
assert(idx('impl:U3') > idx('verify:U1#3'), 'U3 waits for U1 to finish its fix rounds')
assert(calls.filter(c => c.startsWith('fix:U1')).length === 2, 'U1 got exactly 2 fix rounds')
assert(calls.filter(c => c.startsWith('fix:U3')).length === 2 && out.leftovers.some(l => l.unit === 'U3' && l.kind === 'review-cap'), 'U3 capped at 2 fixes and left an open item')
assert(idx('journey:J1') > idx('review:U2'), 'journey J1 starts only after its lanes land')
assert(calls.some(c => c.startsWith('close:U3')), 'close-open-items ran for U3')
assert(calls[calls.length - 1] === 'final-gates', 'final gates run last')
assert(out.units.length === 3 && out.gates.allGreen, 'returns units + gates')

// Lows and product calls never hold a fix loop open: lows go to later, product calls to productCalls.
assert(!calls.some(c => c.startsWith('jfix:J3')) && out.later.some(l => l.source === 'J3' && l.title === 'J3-low'), 'a journey with only lows skips the fix loop; its lows go to later')
assert(prompts['jfix:J1#1'].includes('J1-high') && !prompts['jfix:J1#1'].includes('J1-low'), 'the journey fixer gets high and medium findings only')
assert(!calls.includes('jfix:J1#2') && !out.leftovers.some(l => l.unit === 'J1'), 'a verify left with only a low and a product call ends the loop')
assert(out.later.some(l => l.title === 'new low') && out.productCalls.some(p => p.title === 'ask Ed'), 'a verifier\'s lows go to later, its product calls to productCalls')
const j4 = out.leftovers.find(l => l.unit === 'J4')
assert(j4 && j4.mustFix.length === 1 && j4.mustFix[0].title === 'still broken' && out.later.some(l => l.title === 'J4 side low'), 'an unsettled journey hands close-out only its blocking items')
// 2026-10-06: skeptics check only what the reviewer graded high or medium; a reviewer's low goes to later unchecked.
assert(calls.includes('skeptic:J1#2') && !calls.includes('skeptic:J1#1') && !calls.some(c => c.startsWith('skeptic:J3#')), 'skeptics check only high and medium findings, each under its own finding number')
assert(out.later.some(l => l.title === 'J1-low' && l.unconfirmed === true) && out.later.some(l => l.title === 'J3-low' && l.unconfirmed === true), 'a reviewer-graded low goes to later marked unconfirmed')
assert(calls.includes('skeptic:J2#2') && !prompts['jfix:J2#1'].includes('J2-downgraded') && out.later.some(l => l.title === 'J2-downgraded' && !l.unconfirmed), 'a medium the skeptic re-grades low goes to later as checked, not to the fixer')
assert(!out.later.find(l => l.title === 'new low').unconfirmed, 'a verifier\'s lows are not marked unconfirmed')
assert(out.journeys.find(x => x.journey === 'J1').findings.length === 2, 'the journey result still lists every finding, checked or not')
// Close-out starts as soon as its item exists, once every lane has landed and every journey covering its unit is done.
const laneEnd = Math.max(...Object.keys(ended).filter(l => /^(impl|review|fix|verify):/.test(l)).map(l => ended[l]))
assert(started['close:J4:journey#1'] >= laneEnd, 'close-out waits for every lane to land')
assert(started['close:J4:journey#1'] < ended['journey:J5'], 'close-out does not wait for unrelated journeys')
assert(started['close:U3:review-cap#1'] >= ended['jverify:J2#1'], 'a unit\'s close-out waits for the journeys covering it')

// Bad args must stop the run before any agent starts.
const bad = { ...args, units: args.units.map(u => u.id === 'U3' ? { ...u, deps: ['U9'] } : u), journeys: [{ key: 'J2', title: 'j', units: ['U7'], focus: 'f' }] }
let err = null
const before = calls.length
try { await body(bad, agent, parallel, () => {}, () => {}) } catch (e) { err = String(e) }
assert(err && err.includes('U3 waits on unknown unit U9') && err.includes('journey J2 covers unknown unit U7') && calls.length === before, 'invalid args refused before any agent runs')

// A cycle across lanes must be refused, not hang.
const cyc = { ...args, units: args.units.map(u => u.id === 'U1' ? { ...u, deps: ['U3'] } : u) }
let cerr = null
try { await body(cyc, agent, parallel, () => {}, () => {}) } catch (e) { cerr = String(e) }
assert(cerr && cerr.includes('dependency cycle'), 'dependency cycle refused')
assert(calls.some(c => c.startsWith('close:U3:review-cap#')), 'close-out labels are deterministic (unit:kind#round)')

// Trial switch: protocol.reviewGates gives reviews the targeted gates and adds one full-gates run per lane; a red one becomes an open item.
assert(!calls.some(c => c.startsWith('lane-gates:')) && !prompts['review:U1'].includes('targeted to this unit') && prompts['review:U1'].includes('\n\nG\n\n'), 'without reviewGates: no lane gates, reviews run the full gates')
assert(prompts['jverify:J1#1'].includes('\n\nG\n\n') && prompts[calls.find(c => c.startsWith('close-verify:'))].includes('\n\nG\n\n'), 'without reviewGates: journey and close-out verifiers run the full gates')
calls.length = 0; for (const k in reviewCount) delete reviewCount[k]
const out2 = await body({ ...args, seeds: {}, protocol: { ...args.protocol, reviewGates: 'RG-TARGETED' } }, agent, parallel, () => {}, () => {})
assert(prompts['review:U1'].includes('RG-TARGETED') && prompts['review:U1'].includes('targeted to this unit') && prompts['verify:U1#3'].includes('RG-TARGETED'), 'with reviewGates: every unit review runs the targeted gates')
assert(calls.filter(c => c.startsWith('lane-gates:')).sort().join() === 'lane-gates:U1,lane-gates:U3', 'one lane-gates run per lane, keyed by its first unit')
assert(prompts['lane-gates:U1'].includes('\n\nG\n\n') && !prompts['lane-gates:U1'].includes('RG-TARGETED'), 'lane gates run the full gates')
assert(started['lane-gates:U1'] >= Math.max(ended['review:U2'], ended['verify:U1#3']), 'lane gates start after the lane\'s last unit settles')
assert(out2.leftovers.some(l => l.unit === 'U1' && l.kind === 'lane-gates' && l.mustFix.length === 1 && l.mustFix[0].title === 'lane red') && calls.includes('close:U1:lane-gates#1'), 'a red lane gate becomes an open item and is closed out')
assert(out2.later.some(l => l.title === 'lane low') && !out2.leftovers.some(l => l.unit === 'U3' && l.kind === 'lane-gates'), 'a lane gate\'s lows go to later; a green lane opens nothing')

// Lean mode (/wave lean): builders only, then one final-gates run. No reviews, lane gates, journeys, close-outs or gate verifier.
calls.length = 0; leanStub = true
const out3 = await body({ ...args, lean: true, seeds: {}, protocol: { ...args.protocol, reviewGates: 'RG-TARGETED' } }, agent, parallel, () => {}, () => {})
leanStub = false
assert(calls.every(c => c.startsWith('impl:') || c === 'final-gates'), 'lean: only builders and final gates run (got ' + calls.join(',') + ')')
assert(calls.filter(c => c === 'final-gates').length === 1 && calls[calls.length - 1] === 'final-gates', 'lean: final gates run once, last, with no verifier after their fixes')
assert(idx('impl:U3') > idx('impl:U1') && idx('impl:U2') > idx('impl:U1'), 'lean: lane order and deps still hold')
assert(out3.leftovers.some(l => l.unit === 'U3' && l.kind === 'no-commits') && out3.closeResults.length === 0, 'lean: a unit that built nothing is reported, not closed out')
assert(out3.units.length === 3 && out3.journeys.length === 0, 'lean: returns every unit and no journeys')

// 2026-10-03: slim agent types, per-unit effort, risk-tiered review, planner prototypes, targeted verifies.
assert(optsOf['impl:U1'].agentType === undefined && optsOf['final-gates'].agentType === undefined, 'without agentTypes: agents use the default subagent type')
calls.length = 0; for (const k in reviewCount) delete reviewCount[k]
const units4 = args.units.map(u => u.id === 'U2' ? { ...u, lean: true } : u.id === 'U3' ? { ...u, effort: 'max' } : { ...u, proto: '/sp/proto/A.patch' })
const out4 = await body({ ...args, seeds: {}, units: units4, agentTypes: { builder: 'wave-builder', checker: 'wave-checker' }, protocol: { ...args.protocol, reviewGates: 'RG-TARGETED' } }, agent, parallel, () => {}, () => {})
const typeOf = l => optsOf[l] && optsOf[l].agentType
const builders = calls.filter(c => /^(impl|fix|jfix|close|final-gates)(:|$)/.test(c))
const checkers = calls.filter(c => !builders.includes(c))
assert(builders.length >= 5 && builders.every(c => typeOf(c) === 'wave-builder'), 'agentTypes: builders and fixers run as the builder type (' + builders.filter(c => typeOf(c) !== 'wave-builder').join(',') + ')')
assert(checkers.length >= 8 && checkers.every(c => typeOf(c) === 'wave-checker'), 'agentTypes: reviewers, verifiers, skeptics, journeys and gate keepers run as the checker type (' + checkers.filter(c => typeOf(c) !== 'wave-checker').join(',') + ')')
assert(['impl:U3', 'review:U3', 'fix:U3#1', 'verify:U3#2'].every(l => optsOf[l] && optsOf[l].effort === 'max'), 'per-unit effort: the unit\'s builder, reviews and fixes run at it')
assert(optsOf['impl:U1'].effort === undefined && optsOf['journey:J1'].effort === undefined && optsOf['skeptic:J1#2'].effort === undefined, 'other units and the journeys keep the session effort')
assert(optsOf['lane-gates:U1'].effort === 'medium' && optsOf['lane-gates:U3'].effort === 'medium', 'lane gate keepers run at medium effort')
assert(!calls.some(c => /^(review|verify|fix):U2\b/.test(c)), 'risk-tiered: a lean unit gets no per-unit review or fix')
assert(['journey:J1', 'journey:J3', 'journey:J5', 'lane-gates:U1'].every(l => calls.includes(l)), 'risk-tiered: the journeys and lane gates covering a lean unit still run')
const u1r = out4.units.find(u => u.unit === 'U1'), u2r = out4.units.find(u => u.unit === 'U2')
assert(u2r.lean === true && u2r.reviews.length === 0 && u1r.lean === false && u1r.reviews.length === 3, 'risk-tiered: results say which units skipped review')
assert(prompts['impl:U1'].includes('/sp/proto/A.patch') && prompts['impl:U1'].includes('PROTOTYPE') && !prompts['impl:U3'].includes('PROTOTYPE'), 'a unit with a planner prototype gets it in its build prompt; others do not')
const cv4 = calls.find(c => c.startsWith('close-verify:'))
assert(prompts['jverify:J1#1'].includes('RG-TARGETED') && !prompts['jverify:J1#1'].includes('\n\nG\n\n'), 'with reviewGates: journey verifiers run the targeted gates')
assert(cv4 && prompts[cv4].includes('RG-TARGETED') && !prompts[cv4].includes('\n\nG\n\n'), 'with reviewGates: close-out verifiers run the targeted gates')
assert(prompts['final-gates'].includes('\nG\n') && !prompts['final-gates'].includes('RG-TARGETED'), 'the final gates still run the full gates')

// Auto may continue independently verifiable work alongside a known unrelated baseline failure.
calls.length = 0; for (const k in reviewCount) delete reviewCount[k]
await body({ ...args, seeds: {}, baselineFailures: [{ gate: 'legacy suite', evidence: '/sp/baseline-red.txt', scope: 'outside-wave', heldItems: ['OLD'] }] }, agent, parallel, () => {}, () => {})
assert(['impl:U1', 'review:U1', 'journey:J1', 'final-gates'].every(l => prompts[l].includes('/sp/baseline-red.txt') && prompts[l].includes('outside-wave')), 'auto baseline evidence and scope reach builders, reviewers, journeys and final gates')
assert(prompts['final-gates'].includes('\nG\n') && prompts['final-gates'].includes('allGreen is false while any full gate is red') && !prompts['final-gates'].includes('4. Fix any failure'), 'known unrelated baseline failures remain visible without granting final gates permission to repair held scope')
