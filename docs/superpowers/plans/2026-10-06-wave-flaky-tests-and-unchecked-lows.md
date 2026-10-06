# /wave: queue flaky tests, skip second opinions on lows — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/wave` runs shorter and cheaper without dropping any check that has caught real bugs: a flaky test goes to the queue's Ready list instead of holding the run open, and a journey finding the reviewer grades low skips the skeptic and goes to Later marked unconfirmed.

**Architecture:** Two changes to the generic runner `productivity/wave/lane-runner.js`. (1) Gate keepers (lane gates and final gates) re-run each failing test alone and sort it: a test that passes on re-run, with the timing problem in the test itself, goes in a new `flaky` list instead of `remaining`, so it opens no close-out; the runner returns `flaky` and the handoff writes it to `## Ready`. (2) `runJourney` sends only high and medium findings to a skeptic; lows go straight to `later` with `unconfirmed: true`. The docs (`SKILL.md`, `README.md`, `protocol-template.md`) describe both.

**Tech Stack:** Plain Node ESM, no dependencies. Tests are the stub-agent check scripts beside the runner (`node <name>.check.mjs`).

**Spec:** this document's **Background** section (measured on a real run; no separate spec).

## Background: why

Measured on run `wf_ec1eb06d-391` in the salesfirst-comp project (2026-10-06): three deferred test waves run together, 125 agents, 1,202 agent-minutes, 4h35m on the clock (01:55–06:30 PT). All work that found or fixed something was done by **04:29**.

**Flaky test: 2 hours of clock time for nothing kept.**
- One browser test failed at random in a lane's full-gates run. The runner treats every red gate as an open item: a close-out fixer (reproduce red first, fix at the root) and an independent verifier (reproduce again, revert-proof), up to 2 rounds, after every lane has landed, when nothing else overlaps.
- Round 1: 04:29–05:24 (13 min fix, 41 min re-running browser tests to prove it held; it didn't fully). Round 2: 05:24–06:29, cut at the deadline, discarded. The final gates never ran. The flake went to the project's queue anyway.
- With this change the run ends ≈05:05 including final gates: about **30% shorter**, the same outcome.
- It recurs. Flaky tests showed up in at least four runs of one project (2026-09-27 baseline: a login rate limit; 2026-10-02: "17 lane-gates runs found nothing red from the wave's code, only load flakes"; 2026-10-03: a picker shifting the page in CI; 2026-10-06: a page fade-in). A run puts up to 16 agents on one machine, so load makes timing tests flakier, and proving a flake fixed needs repeated runs, which are slow and noisy under that load.
- Why the queue's **Ready** list, not Later: Ready is what the next wave builds by default, so the flake gets fixed on a quieter machine without anyone remembering it. Left in Later, CI stays red with noise and people stop trusting it.
- The one real danger: a test that fails at random because the **product** has a race a fast user would also hit. That is a real bug. The gate keeper decides test vs product for each flake, and "can't tell" defaults to real bug.

**Second opinions on low findings: 8% of the run's agent time, changed nothing.**

| Reviewer graded | Count | Skeptic outcome | Agent-min |
|---|---|---|---|
| low | 37 | 33 stayed low, 4 refuted, **0 re-graded up** | 94 (8% of run) |
| medium | 17 | 5 stayed medium (fixed), 10 re-graded low, 2 refuted | 49 |
| high | 0 | — | — |

- Skeptics run in parallel right after each journey (2–5 min), so skipping them saves usage, not clock time.
- Checking lows only ever removed false lows from the queue (4 of 37, 11%). Unchecked lows land in Later marked `unconfirmed`, so whoever picks one up reproduces it first.
- Checking mediums stays: it turned 12 of 17 into no-fix-needed, and each avoided fix plus verify costs about 16 agent-minutes against a 3-minute check.

**What stays as it is:** per-change reviews (they found 5 of the run's 7 bugs that would have hit users: wrong pay saved or shown), journeys, medium and high skeptics, fix rounds for real failures.

## Global Constraints

- Shell paths: the repo root is `/Users/mboyajian/Code/[My-LLM-Skills]`. The brackets glob in zsh: always double-quote that path.
- No new dependencies. Checks run with `node <file>.check.mjs`.
- Runner schemas use only `type`, `properties`, `required`, `items`, `enum`: `native-host.mjs`'s `validate()` supports nothing else.
- Agent labels stay deterministic, derived from content (unit ID, journey key, the finding's own number), never from call order. Seeds and native-host resume match on labels.
- `lane-runner.js` keeps the line `const A = args\n` exactly once: big-wave wrappers and a project's test-wave tooling string-replace it.
- The skill is shared by Claude Code (Workflow tool) and Codex (`native-host.mjs`): run all four check scripts at the end.
- A flaky-test fix never loosens an assertion; the rule text says so.
- Don't change the runner while a wave is running: the native host aborts a resume when a job's prompt or schema changed.
- Commit only the paths each task names (`git add <paths>`), never `git add -A`.

## Review Focus

1. **A product race labelled a test flake.** A real user-facing timing bug would be queued instead of fixed. Expected: the rule tells the gate keeper "can't tell → real failure". Pinned in Task 2 (the prompt carries the safe default).
2. **A lane gate keeper that sets `resolved: false`, lists nothing in `remaining`, and lists flakes.** Expected: no close-out; today the runner would open an empty open item and burn a close-out on it. Pinned in Task 2 (the stub returns exactly that).
3. **The same flaky test reported by a lane gate and again by the final gates.** Expected: one entry, so one Ready item. Pinned in Task 3.
4. **Lean mode, where the final gate keeper is the only gate.** Expected: it gets the same flaky rule and schema. Pinned in Task 3.
5. **A journey whose low comes before its high.** Expected: the high's skeptic keeps the high's own finding number (`#2`), so a resumed run's seeds still match. Pinned in Task 1.

---

### Task 0: Settle pending work and prove the baseline

**Files:** none changed.

- [ ] **Step 1: Check for uncommitted work**

Run: `git -C "/Users/mboyajian/Code/[My-LLM-Skills]" status --short`

On 2026-10-06 these were modified and uncommitted (the Codex native-dispatch work): `productivity/queue/estimate.py`, `productivity/wave/README.md`, `productivity/wave/SKILL.md`, `productivity/wave/lane-runner.check.mjs`, `productivity/wave/lane-runner.js`. This plan edits four of them, so its commits would sweep that work in.

- [ ] **Step 2: If any of those are still dirty, stop and ask the user**

Options: (A, recommended) commit the pending work first as its own commit, so this plan's commits contain only this plan; (B) fold it into this plan's commits. Don't start Task 1 until answered.

- [ ] **Step 3: Run every check for a green baseline**

```bash
cd "/Users/mboyajian/Code/[My-LLM-Skills]/productivity/wave" && for f in lane-runner native-host codex-host prepare-auto; do node "$f.check.mjs" > "/tmp/wave-$f.check.log" 2>&1; echo "$f=$?"; done
```

Expected: all four `=0` (they were on 2026-10-06). If one is red, stop and report it; don't build on a red baseline.

---

### Task 1: Skeptics check only high and medium journey findings

**Files:**
- Modify: `productivity/wave/lane-runner.js` (`meta.phases` Journeys detail; `jPrompt`; `runJourney`, the block from `const findings =` to `const out =`)
- Test: `productivity/wave/lane-runner.check.mjs`

**Interfaces:**
- Produces: items in the runner's returned `later` array may carry `unconfirmed: true` (a reviewer-graded low nobody re-reproduced). Items without it are unchanged. `journeys[].findings` lists every finding; an unchecked one has `verdict: null`.

- [ ] **Step 1: Write the failing assertions**

In `lane-runner.check.mjs`, replace the `JOURNEY_FINDINGS` line (J1's low now comes first; J2 gets a medium the skeptic will re-grade low):

```js
const JOURNEY_FINDINGS = { J1: [find('J1-low', 'low', 'a.ts'), find('J1-high', 'high', 'a.ts')], J2: [find('J2-high', 'high', 'c.ts'), find('J2-downgraded', 'medium', 'c.ts')], J3: [find('J3-low', 'low', 'b.ts')], J4: [find('J4-medium', 'medium', 'd.ts')], J5: [] }
```

Replace the skeptic stub line:

```js
  if (l.startsWith('skeptic:')) return { real: true, severity: prompt.includes('J2-downgraded') ? 'low' : sev(prompt), reproducedHow: '', reasoning: '' }
```

Directly after the assertion `'an unsettled journey hands close-out only its blocking items'`, add:

```js
// 2026-10-06: skeptics check only what the reviewer graded high or medium; a reviewer's low goes to later unchecked.
assert(calls.includes('skeptic:J1#2') && !calls.includes('skeptic:J1#1') && !calls.some(c => c.startsWith('skeptic:J3#')), 'skeptics check only high and medium findings, each under its own finding number')
assert(out.later.some(l => l.title === 'J1-low' && l.unconfirmed === true) && out.later.some(l => l.title === 'J3-low' && l.unconfirmed === true), 'a reviewer-graded low goes to later marked unconfirmed')
assert(calls.includes('skeptic:J2#2') && !prompts['jfix:J2#1'].includes('J2-downgraded') && out.later.some(l => l.title === 'J2-downgraded' && !l.unconfirmed), 'a medium the skeptic re-grades low goes to later as checked, not to the fixer')
assert(!out.later.find(l => l.title === 'new low').unconfirmed, 'a verifier\'s lows are not marked unconfirmed')
assert(out.journeys.find(x => x.journey === 'J1').findings.length === 2, 'the journey result still lists every finding, checked or not')
```

- [ ] **Step 2: Run it and see it fail for the right reason**

Run: `node "/Users/mboyajian/Code/[My-LLM-Skills]/productivity/wave/lane-runner.check.mjs"`
Expected: `FAIL skeptics check only high and medium findings…` (today `skeptic:J1#1` runs on the low) and `FAIL a reviewer-graded low goes to later marked unconfirmed`. The other three new lines pass; they pin existing behaviour. Exit code 1. Every older assertion still prints `ok`.

- [ ] **Step 3: Implement**

In `lane-runner.js`, `meta.phases`, replace the Journeys detail with:

```js
    { title: 'Journeys', detail: 'cross-lane reviews start as soon as the lanes they cover land; a skeptic re-reproduces every high and medium finding and those that hold are fixed; lows go to Later unchecked' },
```

In `jPrompt`, after `Find real user-visible or data-integrity defects, not style.` insert (same template string):

```
 Only your high and medium findings get an independent check and a fix in this run. A low goes straight to the queue as you wrote it, so grade honestly and give every finding a reproduction someone else can run.
```

In `runJourney`, replace everything from `const findings = (found && found.findings) || []` through the `const out = { … }` line with:

```js
  const findings = (found && found.findings) || []
  // Skeptics check only what the reviewer graded high or medium (2026-10-06: 0 of 37 lows re-graded up, 4 refuted;
  // 10 of 17 mediums re-graded down). A low goes to later unchecked. Labels keep the finding's own number.
  const numbered = findings.map((f, i) => ({ f, n: i + 1 }))
  const unchecked = numbered.filter(x => x.f.severity === 'low').map(x => ({ ...x.f, journey: j.key, verdict: null }))
  const verdicts = await parallel(numbered.filter(x => x.f.severity !== 'low').map(({ f, n }) => () => run(`skeptic:${j.key}#${n}`, skepticPrompt(f, j), { phase: 'Journeys', schema: VERDICT }).then(v => ({ ...f, journey: j.key, verdict: v }))))
  const judged = verdicts.filter(Boolean)
  const real = judged.filter(f => f.verdict && f.verdict.real)
  const confirmed = real.filter(f => f.verdict.severity !== 'low')
  const laterEntry = f => ({ source: j.key, title: f.title, severity: 'low', productCall: false, ticket: f.ticket, detail: `${f.reproduction}\nEvidence: ${f.evidence}\nFiles: ${(f.files || []).join(', ')}\nSuggested fix: ${f.suggestedFix}` })
  for (const f of real) if (f.verdict.severity === 'low') later.push(laterEntry(f))
  for (const f of unchecked) later.push({ ...laterEntry(f), unconfirmed: true })
  log(`${j.key}: ${findings.length} findings, ${unchecked.length} low queued unchecked, ${real.length} of ${judged.length} checked confirmed by a skeptic, ${confirmed.length} high or medium to fix now`)
  const out = { journey: j.key, title: j.title, checkedAndFine: (found && found.checkedAndFine) || [], findings: judged.concat(unchecked), fixes: [], verifies: [] }
```

- [ ] **Step 4: Run it and see it pass**

Run: `node "/Users/mboyajian/Code/[My-LLM-Skills]/productivity/wave/lane-runner.check.mjs"; echo "exit=$?"`
Expected: every line `ok`, `exit=0`.

- [ ] **Step 5: Revert-proof**

Temporarily change `x.f.severity === 'low'` in the `unchecked` line back to `false` (every finding checked again). Re-run: the first two new assertions must FAIL. Restore it and re-run: all `ok`.

- [ ] **Step 6: Commit**

```bash
cd "/Users/mboyajian/Code/[My-LLM-Skills]" && git add productivity/wave/lane-runner.js productivity/wave/lane-runner.check.mjs && git commit -m "wave: skeptics check only high and medium journey findings

Lows go to later unchecked, marked unconfirmed. Measured 2026-10-06:
skeptics re-graded 0 of 37 lows upward and refuted 4 (94 agent-min,
8% of the run); mediums keep their check (10 of 17 re-graded down)."
```

---

### Task 2: Lane gates queue a test-side flake instead of opening a close-out

**Files:**
- Modify: `productivity/wave/lane-runner.js` (new `FLAKY`, `LANE_GATES`, `FLAKY_RULE`, `flaky`, `harvestFlaky`; `laneGatesPrompt`; the lane-gates block in `runLane`; the return object)
- Test: `productivity/wave/lane-runner.check.mjs`

**Interfaces:**
- Consumes: `args.protocol.flaky` (optional string: the project's `### Flaky tests` block).
- Produces: `FLAKY` schema `{ test, file, runs, whyTestNotProduct, reproduction, suggestedFix }` (all strings, all required); `FLAKY_RULE` (prompt text containing `FLAKY TESTS` and `or if you cannot tell: it is a real failure`); `harvestFlaky(v, source)`; the runner's return gains `flaky: [{ source, ...FLAKY }]`, deduplicated on `file` + `test`.

- [ ] **Step 1: Write the failing assertions**

In `lane-runner.check.mjs`, after the `const rem = …` line add:

```js
const flake = test => ({ test, file: 'e2e/pill.spec.ts', runs: 'failed 1 of 4', whyTestNotProduct: 'clicks while the page fades in', reproduction: 'r', suggestedFix: 'wait for the fade' })
let flakyStub = false   // the flaky run: L2's lane gate is red only on a test-side flake
```

In `agent()`, directly above `if (l === 'lane-gates:U1') return …`, add:

```js
  if (flakyStub && l === 'lane-gates:U3') return { resolved: false, remaining: [], flaky: [flake('pill.spec.ts:119')], revertProof: '', gates: [], notes: '' }
```

At the end of the file add:

```js
// 2026-10-06: a lane gate whose only red is a test-side flake opens no close-out; the flake is returned for the queue's Ready.
calls.length = 0; for (const k in reviewCount) delete reviewCount[k]; flakyStub = true
const out5 = await body({ ...args, seeds: {}, protocol: { ...args.protocol, reviewGates: 'RG-TARGETED', flaky: 'FLK-NOTES' } }, agent, parallel, () => {}, () => {})
flakyStub = false
assert(!calls.some(c => c.startsWith('close:U3:lane-gates')) && !out5.leftovers.some(l => l.unit === 'U3' && l.kind === 'lane-gates'), 'a lane gate whose only red is a test-side flake opens no close-out')
assert((out5.flaky || []).some(f => f.source === 'U3' && f.test === 'pill.spec.ts:119' && f.whyTestNotProduct), 'the flake is returned in flaky, keyed to its lane, with the test-or-product call')
assert(calls.includes('close:U1:lane-gates#1'), 'a real red lane gate in the same run is still closed out')
assert(prompts['lane-gates:U1'].includes('FLAKY TESTS') && prompts['lane-gates:U1'].includes('or if you cannot tell: it is a real failure') && prompts['lane-gates:U1'].includes('FLK-NOTES'), 'lane gate keepers get the flaky rule, its safe default and the project\'s notes')
assert(optsOf['lane-gates:U1'].schema.required.includes('flaky') && optsOf['lane-gates:U1'].schema.properties.flaky?.items.required.includes('whyTestNotProduct'), 'the lane-gates schema requires the flaky list and the test-or-product call')
assert(src.split('const A = args\n').length === 2, 'const A = args appears exactly once (wrappers replace it)')
```

- [ ] **Step 2: Run it and see it fail for the right reason**

Run: `node "/Users/mboyajian/Code/[My-LLM-Skills]/productivity/wave/lane-runner.check.mjs"`
Expected FAILs: `opens no close-out` (today `resolved: false` opens an empty open item and `close:U3:lane-gates#1` runs), `returned in flaky`, `flaky rule…`, `schema requires the flaky list`. Expected passes: `still closed out`, `const A = args`. Exit code 1.

- [ ] **Step 3: Implement**

In `lane-runner.js`, directly after the `VERIFY` schema, add:

```js
// A test that failed, then passed when re-run alone on the same code, with the timing problem in the test itself.
const FLAKY = { type: 'object', properties: { test: { type: 'string' }, file: { type: 'string' }, runs: { type: 'string' }, whyTestNotProduct: { type: 'string' }, reproduction: { type: 'string' }, suggestedFix: { type: 'string' } }, required: ['test', 'file', 'runs', 'whyTestNotProduct', 'reproduction', 'suggestedFix'] }
const LANE_GATES = { ...VERIFY, properties: { ...VERIFY.properties, flaky: { type: 'array', items: FLAKY } }, required: [...VERIFY.required, 'flaky'] }
```

Next to `const later = []` / `const productCalls = []`, add:

```js
// Flaky tests never hold a run open: the gate keeper lists a test-side flake, the handoff puts it in Ready.
const flaky = []
function harvestFlaky(v, source) {
  for (const f of (v && v.flaky) || []) if (!flaky.some(x => x.file === f.file && x.test === f.test)) flaky.push({ source, ...f })
}
```

After the `const VGATES = …` line, add:

```js
const FLAKY_RULE = `FLAKY TESTS: re-run each failing test on its own, on the same code, up to 3 times. If it passes on any re-run, it is flaky; decide where the timing problem lives. In the TEST (waiting for an animation or a re-render, test order, state shared between tests, machine load): list it in flaky with the runs ("failed 1 of 4"), why the problem is the test and not the product, a reproduction, and a suggested fix that never loosens an assertion; leave it out of remaining and do not fix it here. A builder fixes it from the queue on a quiet machine. In the PRODUCT (a person acting at the same speed would hit it too), or if you cannot tell: it is a real failure; report it like any other.${P.flaky ? `\nThis project's notes on flaky tests:\n${P.flaky}` : ''}`
```

In `laneGatesPrompt`, replace

```
resolved = true only if every gate is green, or every remaining failure is another lane's work in flight. ${REMAINING}\n\n${P.snapshot}
```

with

```
resolved = true only if every gate is green, or every failure is another lane's work in flight or a test-side flake you listed in flaky. ${REMAINING}\n\n${FLAKY_RULE}\n\n${P.snapshot}
```

In `runLane`, replace

```js
    const ver = await run(`lane-gates:${key}`, laneGatesPrompt(ids, out), { phase: 'Lanes', schema: VERIFY })
    harvest(ver, key)
    if (!settled(ver)) {
```

with

```js
    const ver = await run(`lane-gates:${key}`, laneGatesPrompt(ids, out), { phase: 'Lanes', schema: LANE_GATES })
    harvest(ver, key)
    harvestFlaky(ver, key)
    const onlyFlaky = !!ver && blocking(ver).length === 0 && (ver.flaky || []).length > 0
    if (!settled(ver) && !onlyFlaky) {
```

In the final `return { … }`, add `flaky,` after `productCalls,`.

- [ ] **Step 4: Run it and see it pass**

Run: `node "/Users/mboyajian/Code/[My-LLM-Skills]/productivity/wave/lane-runner.check.mjs"; echo "exit=$?"`
Expected: every line `ok`, `exit=0`.

- [ ] **Step 5: Revert-proof**

Temporarily replace `&& !onlyFlaky` with nothing. Re-run: `opens no close-out` must FAIL. Restore and re-run: all `ok`.

- [ ] **Step 6: Commit**

```bash
cd "/Users/mboyajian/Code/[My-LLM-Skills]" && git add productivity/wave/lane-runner.js productivity/wave/lane-runner.check.mjs && git commit -m "wave: lane gates queue a test-side flake instead of a close-out

A flaky test held a 2026-10-06 run open for 2 hours (two close-out
rounds, second discarded; the flake was queued anyway). Gate keepers
now re-run each failure alone; a test-side flake goes to flaky, a
product-side or uncertain one stays a real failure."
```

---

### Task 3: Final gates list a test-side flake (full and lean runs)

**Files:**
- Modify: `productivity/wave/lane-runner.js` (`GATES` schema; `meta.phases` Final gates detail; `finalRepair`; the final-gates prompt; one line after the final-gates `run`)
- Modify: `productivity/wave/native-host.check.mjs` (its final-gates report gains `flaky: []`)
- Test: `productivity/wave/lane-runner.check.mjs`

**Interfaces:**
- Consumes: `FLAKY`, `FLAKY_RULE`, `harvestFlaky` from Task 2.
- Produces: the `GATES` schema requires `flaky: FLAKY[]`. Final-gates flakes join the returned `flaky` with `source: 'final-gates'`.

- [ ] **Step 1: Write the failing assertions**

In `lane-runner.check.mjs`, in `agent()`, directly above `if (l === 'final-gates') return { gates: [], allGreen: true, …`, add:

```js
  if (flakyStub && l === 'final-gates') return { gates: [], allGreen: true, failuresFixed: [], remainingFailures: [], flaky: [flake('pill.spec.ts:119'), flake('other.spec.ts:7')], notes: '' }
```

After the assertion `'lean: returns every unit and no journeys'`, add:

```js
assert(prompts['final-gates'].includes('FLAKY TESTS') && optsOf['final-gates'].schema.required.includes('flaky'), 'lean: the only gate keeper gets the flaky rule and must report a flaky list')
```

At the end of the file add:

```js
assert((out5.flaky || []).filter(f => f.test === 'pill.spec.ts:119').length === 1 && (out5.flaky || []).some(f => f.source === 'final-gates' && f.test === 'other.spec.ts:7'), 'final-gates flakes join flaky once each, keyed to final-gates')
assert(prompts['final-gates'].includes('A test-side flake (FLAKY TESTS below) is listed, not fixed.') && prompts['final-gates'].includes('counts as green'), 'the final gate keeper lists a test-side flake instead of fixing it')
assert(optsOf['final-gates'].schema.required.includes('flaky'), 'the final-gates schema requires the flaky list')
```

- [ ] **Step 2: Run it and see it fail for the right reason**

Run: `node "/Users/mboyajian/Code/[My-LLM-Skills]/productivity/wave/lane-runner.check.mjs"`
Expected FAILs: the lean line, `join flaky once each`, `lists a test-side flake`, `schema requires the flaky list`. Exit code 1.

- [ ] **Step 3: Implement**

In `GATES`, add `flaky: { type: 'array', items: FLAKY },` to `properties` and `'flaky'` to `required`. Move the `FLAKY` definition above `GATES` if it isn't already (Task 2 placed it right after `VERIFY`, which comes before `GATES`).

In `meta.phases`, replace the Final gates detail with:

```js
    { title: 'Final gates', detail: 'full gates on the quiet tree; a test-side flaky test is listed for the queue, not fixed' },
```

Wrap `finalRepair`'s ternary in parentheses and append the flake sentence: the line becomes

```js
const finalRepair = (BASELINE ? 'Fix in-wave failures and regressions at their root with a documented commit (test red first), then re-run that gate. Preserve outside-wave baseline failures in remainingFailures; allGreen is false while any full gate is red. A stale test\'s premise gets fixed only within scope, never weakened or deleted.' : 'Fix any failure at its root with a documented commit (test red first), then re-run that gate. A stale test\'s premise gets fixed, never deleted.') + ' A test-side flake (FLAKY TESTS below) is listed, not fixed.'
```

In the `final-gates` prompt, replace `\n4. ${finalRepair}\n\n${FIX_RULES}` with:

```
\n4. ${finalRepair}\n5. ${FLAKY_RULE}\nA gate whose only failures are test-side flakes you listed counts as green; name each one in notes too.\n\n${FIX_RULES}
```

Directly after `const gates = await run('final-gates', …)`, add:

```js
harvestFlaky(gates, 'final-gates')
```

- [ ] **Step 4: Run the runner check and see it pass**

Run: `node "/Users/mboyajian/Code/[My-LLM-Skills]/productivity/wave/lane-runner.check.mjs"; echo "exit=$?"`
Expected: every line `ok`, `exit=0`.

- [ ] **Step 5: Run the native-host check and see the schema bite**

Run: `node "/Users/mboyajian/Code/[My-LLM-Skills]/productivity/wave/native-host.check.mjs"; echo "exit=$?"`
Expected: FAIL, the bridge rejecting the final-gates report with `$.flaky: required`. This proves Codex runs enforce the new field.

- [ ] **Step 6: Update the native-host stub and see it pass**

In `native-host.check.mjs`, change the final-gates report to:

```js
  report(lanes.argsPath, 'final-gates', 'final-gates', { gates: [], allGreen: true, failuresFixed: [], remainingFailures: [], flaky: [], notes: '' })
```

Re-run it. Expected: all `ok`, `exit=0`.

- [ ] **Step 7: Commit**

```bash
cd "/Users/mboyajian/Code/[My-LLM-Skills]" && git add productivity/wave/lane-runner.js productivity/wave/lane-runner.check.mjs productivity/wave/native-host.check.mjs && git commit -m "wave: final gates list a test-side flake instead of fixing it

Covers lean runs too, where the final gate keeper is the only gate.
The flaky list is required in the gates schema, so Codex's native
bridge rejects a report that skips the test-or-product call."
```

---

### Task 4: Document it: SKILL.md, README.md, protocol template

**Files:**
- Modify: `productivity/wave/SKILL.md` (step 3 `protocol` arg; step 4.2 Queue; step 4.4 Results; step 4.5 Wrap-up; Lean mode `Run:`)
- Modify: `productivity/wave/README.md` ("What a run does" steps 4 and 5)
- Modify: `productivity/wave/protocol-template.md` (header comment; new optional `### Flaky tests` block)

**Interfaces:**
- Consumes: `args.protocol.flaky`, the runner's returned `flaky`, and `later[].unconfirmed` (Tasks 1–3).

- [ ] **Step 1: SKILL.md, step 3 args**

In the `protocol` bullet, after `…one more agent per lane);` add: `plus `flaky` = its `### Flaky tests` block when it has one (how this project reproduces and fixes its flaky tests; gate keepers read it);`

- [ ] **Step 2: SKILL.md, step 4.2 Queue**

After the sentence ending `…grouped by area, keyed to their ticket, reproduction kept.`, add:

```
     A `later` item with `unconfirmed: true` was graded low by a journey reviewer and not re-reproduced: its entry says `(unconfirmed: reproduce before fixing)`. The runner's `flaky` list (tests that failed, then passed when re-run alone, with the problem in the test, not the product) becomes `## Ready` entries, never Later: one per test file, typed as test tooling, with the runs, the test-or-product reasoning, the reproduction and the suggested fix, and the rule that the fix never loosens an assertion. Ready, because the next wave then fixes it on a quieter machine; left in Later, CI stays noisy until someone remembers it.
```

- [ ] **Step 3: SKILL.md, Results and wrap-up**

Step 4.4: in `(commits, units, agents, hours from go to handoff, first-review failure rate, journey findings confirmed: …)`, insert `, lows queued unchecked, flaky tests queued` after `journey findings confirmed`.

Step 4.5: after `the page link,` insert `the flaky tests queued to Ready (CI may flake on them until the next wave),`.

- [ ] **Step 4: SKILL.md, Lean mode**

In `**Run:**`, replace `then one final-gates agent that fixes anything red.` with `then one final-gates agent that fixes anything red except a test-side flaky test, which it lists for the queue's Ready.`

- [ ] **Step 5: README.md**

In "What a run does" step 4, after `Cross-lane "journey" reviews follow shared user paths,` insert ` with a skeptic re-checking each high and medium finding (lows go to the queue unchecked),` and at the end of the step add ` A test that fails, then passes when re-run alone, with the problem in the test, goes to the queue's Ready list instead of holding the run open.` In step 5, after `leftover findings become `## Later` entries`, insert ` and flaky tests become `## Ready` entries`.

- [ ] **Step 6: protocol-template.md**

In the header comment, replace `The five "###" blocks below Setup are pasted into agent` with `The "###" blocks below Setup are pasted into agent` (the paragraph keeps its other lines). At the end of the file add:

```
### Flaky tests

<!-- Optional: delete this block until the project has notes. Gate keepers read it when a test fails at random. -->
FLAKY TESTS IN THIS PROJECT: {{HOW TO REPRODUCE A FLAKE (e.g. the CI shard command at one worker), KNOWN CAUSES (page transitions, login rate limits, machine load), AND THE FIX PATTERN (wait for the transition; target something the UI can't cover). Never loosen an assertion.}}
```

- [ ] **Step 7: Run all four checks**

```bash
cd "/Users/mboyajian/Code/[My-LLM-Skills]/productivity/wave" && for f in lane-runner native-host codex-host prepare-auto; do node "$f.check.mjs" > "/tmp/wave-$f.check.log" 2>&1; echo "$f=$?"; done
```

Expected: all four `=0`.

- [ ] **Step 8: Commit**

```bash
cd "/Users/mboyajian/Code/[My-LLM-Skills]" && git add productivity/wave/SKILL.md productivity/wave/README.md productivity/wave/protocol-template.md && git commit -m "wave: document flaky tests to Ready and unconfirmed lows

Handoff writes the runner's flaky list to ## Ready and marks
unconfirmed lows; the protocol gains an optional ### Flaky tests block."
```

---

## Not doing (and why)

- **A switch to re-check lows:** no project has asked for one. Add it when one does.
- **Flaky handling in journey, fix and close-out verifiers:** they run targeted gates on snapshots, and no run has lost time there yet.
- **Changing per-change reviews or medium/high skeptics:** they are where the real bugs were found.
- **Watch, don't act:** 2 of the 10 medium→low re-grades in the measured run looked pay-relevant on a later read (a corrected rate that saves without changing pay; answered rates left unpriced after a deploy). If skeptic downgrades keep looking wrong, tighten the skeptic's severity rule then.

## Follow-up in each project (not this repo)

Add a `### Flaky tests` block to the project's `## Wave protocol` in `WORK_QUEUE.md`. For salesfirst-comp, from its last four runs:

```
### Flaky tests

FLAKY TESTS IN THIS PROJECT: reproduce a browser flake by running all four CI shards at once at --workers=1 (tests/e2e/ci). Known causes: page fade-ins (/income fades in over 0.3s and Playwright re-scrolls a target it calls "not stable"), Fortify's five-logins-a-minute limit (log in once per run via auth.setup.ts), layout shifts when a picker opens. Fix in the test: wait for the transition to finish, or target an element the open UI provably can't cover. Never loosen an assertion.
```

That project's test-wave tooling (`prepare-test-wave.py`) reads `~/.claude/skills/wave/lane-runner.js` when each test wave is prepared, so test waves prepared after this lands get the new behaviour automatically.
