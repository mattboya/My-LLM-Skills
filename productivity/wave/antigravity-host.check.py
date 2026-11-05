# Runs antigravity-host.py against the real native-host.mjs, with stand-ins for run_workflow's agent() and log().
# No model calls or repository edits.   python3 antigravity-host.check.py
import ast, asyncio, json, os, shutil, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.path.join(HERE, "native-host.mjs")
BRIDGE = os.path.join(HERE, "antigravity-host.py")
with open(BRIDGE) as f:
    CODE = compile(f.read(), BRIDGE, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
T = tempfile.mkdtemp(prefix="wave-agy-check-")
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
GOOD = {"ok": True}
IMPL = {"status": "complete", "commits": [{"sha": "abc123", "ticket": "T-A", "subject": "test"}], "filesTouched": ["a"],
        "summary": "test", "userFacingChange": "test", "decisions": [], "deviationsFromBrief": [], "pendingHumanSteps": [],
        "testsAdded": [{"file": "test", "what": "behavior", "tier": "unit", "sawRedFirst": True, "redOutputFile": "red.txt"}],
        "openQuestions": [], "crossLaneNotes": [], "reviewPlan": [], "laterItems": [], "incomplete": []}


def fixture(name, script, args=None):
    paths = os.path.join(T, name + ".js"), os.path.join(T, name + ".json")
    with open(paths[0], "w") as f:
        f.write(script)
    with open(paths[1], "w") as f:
        json.dump(args or {}, f)
    return paths


def status(args_path):
    return json.loads(subprocess.run(["node", HOST, "status", args_path], capture_output=True, text=True, check=True).stdout)


class Agents:
    """Stand-in for run_workflow's agent(): answer(role, prompt, turn) returns a turn's result, raises, or awaits."""
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, prompt=None, schema=None, role=None, **kw):
        turns = [0]

        async def turn(p, s=None):
            turns[0] += 1
            self.calls.append((role, p))
            value = self.answer(role, p, turns[0])
            return await value if asyncio.iscoroutine(value) else value
        return turn

    def prompts(self, role):
        return [p for r, p in self.calls if r == role]


def bridge(script, args_path, agents, resume=False):
    g = {"args": {"script": script, "args": args_path, "resume": resume, "host": HOST},
         "agent": agents, "log": lambda *a: None, "__name__": "__agy_check__"}
    return g, eval(CODE, g)   # a coroutine: the bridge awaits at top level, as under run_workflow


async def main():
    # Independent jobs run together; a dependent job waits; reports reach the runner unchanged.
    script, args_path = fixture("ordering", f"""
const s = {json.dumps(SCHEMA)}
const results = await parallel([() => agent('build A', {{ label: 'a', schema: s }}), () => agent('build B', {{ label: 'b', schema: s }})])
return {{ results, review: await agent('review', {{ label: 'review', schema: s }}) }}""")
    def first_turn_fails_for_b(role, p, turn):
        if role == "b" and turn == 1:
            raise RuntimeError("no finish")
        return GOOD
    agents = Agents(first_turn_fails_for_b)
    g, run = bridge(script, args_path, agents)
    await run
    with open(os.path.join(T, "ordering.native.run", "result.json")) as f:
        assert json.load(f) == {"results": [GOOD, GOOD], "review": GOOD}
    assert [r for r, _ in agents.calls].index("review") > max(i for i, (r, _) in enumerate(agents.calls) if r in "ab")
    assert "call your finish tool" in agents.prompts("a")[0]
    assert agents.prompts("b")[1] == g["FIX"], "an agent that ends without finish gets one correction turn"
    print("ok dispatch: independent jobs, dependency waits, finish note, one correction turn")

    # A failed agent stops the host before dependents start; resume replaces it.
    script, args_path = fixture("failed", f"await agent('first', {{ label: 'first', schema: {json.dumps(SCHEMA)} }}); "
                                          "return agent('second', { label: 'second', schema: { type: 'string' } })")
    def broken(role, p, turn):
        raise RuntimeError("no finish")
    agents = Agents(broken)
    _, run = bridge(script, args_path, agents)
    try:
        await run
        raise AssertionError("a failed agent must stop the run")
    except RuntimeError as e:
        assert "resume: true" in str(e), e
    assert not agents.prompts("second"), "failure cannot release a dependent job"
    agents = Agents(lambda role, p, turn: GOOD if role == "first" else "done")
    _, run = bridge(script, args_path, agents, resume=True)
    await run
    with open(os.path.join(T, "failed.native.run", "attempts.jsonl")) as f:
        assert "Antigravity agent failed" in f.read()
    assert agents.prompts("second")
    print("ok failure: a failed agent stops dependents; resume archives it and runs a replacement")

    # A stopped workflow: its host keeps running, one agent saved a report, one was cut off mid-job.
    script, args_path = fixture("stopped", f"""
const s = {json.dumps(SCHEMA)}
return parallel([() => agent('a', {{ label: 'a', schema: s }}), () => agent('b', {{ label: 'b', schema: s }})])""")
    hang = asyncio.Event()
    g, run = bridge(script, args_path, Agents(lambda role, p, turn: hang.wait()))
    main_task = asyncio.ensure_future(run)
    while len([j for j in (status(args_path)["jobs"] if os.path.exists(os.path.join(T, "stopped.native.run", "state.json")) else [])
               if j["state"] == "running"]) < 2:
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.1)
    for t in [main_task] + g["tasks"]:
        t.cancel()
    await asyncio.gather(main_task, *g["tasks"], return_exceptions=True)
    orphan = g["proc"]
    assert orphan.poll() is None, "the stopped workflow's host is still running"
    a = next(j for j in status(args_path)["jobs"] if j["label"] == "a")
    with open(os.path.join(T, "stopped.native.run", "agy-reports", a["id"] + ".json"), "w") as f:
        json.dump({"agentId": a["agentId"], "result": GOOD}, f)
    sleeper = subprocess.Popen(["sleep", "30"])
    with open(os.path.join(T, "stopped.native.run", "agy-bridge.json"), "w") as f:
        json.dump({"pid": sleeper.pid}, f)
    _, run = bridge(script, args_path, Agents(lambda role, p, turn: GOOD), resume=True)
    try:
        await run
        raise AssertionError("a second bridge must refuse while the first is alive")
    except RuntimeError as e:
        assert "another bridge" in str(e), e
    sleeper.kill(); sleeper.wait()
    agents = Agents(lambda role, p, turn: GOOD)
    _, run = bridge(script, args_path, agents, resume=True)
    await run
    assert orphan.wait() == 130, "the stale host was stopped through its SIGTERM handler"
    assert not agents.prompts("a"), "a saved report is submitted, not redone"
    assert "earlier attempt" in agents.prompts("b")[0], "a cut-off job runs again and is told to check its partial work"
    with open(os.path.join(T, "stopped.native.run", "result.json")) as f:
        assert json.load(f) == [GOOD, GOOD]
    print("ok resume: stale host stopped, second bridge refused, saved report used, cut-off job re-run")

    # The shared lane runner, lean, end to end through the bridge.
    _, args_path = fixture("lanes", "", {
        "wave": "Antigravity bridge check", "repo": T, "sp": T, "base": "base", "waveDoc": os.path.join(T, "wave.md"),
        "coAuthor": "test", "tickets": {"A": "T-A", "B": "T-B"}, "lean": True,
        "protocol": {"shared": "shared", "gates": "gates", "snapshot": "snapshot"},
        "units": [{"id": "U1", "lane": "L1", "title": "first", "items": ["A"], "files": ["a"], "brief": "first"},
                  {"id": "U2", "lane": "L2", "title": "dependent", "items": ["B"], "deps": ["U1"], "files": ["b"], "brief": "second"}],
        "lanes": [["U1"], ["U2"]], "journeys": []})
    gates = {"gates": [], "allGreen": True, "failuresFixed": [], "remainingFailures": [], "flaky": [], "notes": ""}
    agents = Agents(lambda role, p, turn: IMPL if role.startswith("impl:") else gates)
    _, run = bridge(os.path.join(HERE, "lane-runner.js"), args_path, agents)
    await run
    assert [r for r, _ in agents.calls] == ["impl:U1", "impl:U2", "final-gates"]
    assert "TEST-DRIVEN DEVELOPMENT" in agents.prompts("impl:U1")[0]
    with open(os.path.join(T, "lanes.native.run", "result.json")) as f:
        result = json.load(f)
    assert len(result["units"]) == 2 and result["gates"]["allGreen"]
    print("ok shared lane runner: unit deps, TDD prompts, lean mode and final gates through the bridge")


try:
    asyncio.run(main())
finally:
    shutil.rmtree(T, ignore_errors=True)
