# Antigravity-only bridge, run by the run_workflow tool (which supplies args, agent and log):
#   run_workflow(ScriptPath="~/.agents/skills/wave/antigravity-host.py", Description="...",
#                Args={"script": "<abs lane-runner.js>", "args": "<abs lanes.args.json>", "resume": false})
# native-host.mjs runs the unchanged Workflow-API script and publishes each agent() call as a job file;
# this script runs each job as a workflow agent and hands its report back. See references/antigravity.md.
import asyncio, json, os, re, signal, subprocess, uuid

HOST = args.get("host") or os.path.expanduser("~/.agents/skills/wave/native-host.mjs")
SCRIPT, ARGS, RESUME = args["script"], args["args"], bool(args.get("resume"))
RUN = re.sub(r"\.json$", "", os.path.abspath(ARGS)) + ".native.run"   # native-host's run folder
REPORTS, PIDFILE = os.path.join(RUN, "agy-reports"), os.path.join(RUN, "agy-bridge.json")
MAX = 16  # ponytail: the runner's prompts promise "up to 16 agents"
RETURN = ('\n\n(Antigravity: "return through StructuredOutput" means: call your finish tool with the JSON '
          'your result schema describes.)')
RETRY = ('\n\nAn earlier attempt at this job stopped before it reported. Check `git status` and `git log` '
         'for its work first, keep what is correct, and finish the job.')
FIX = 'You ended without calling finish. Do not repeat work you already did: call finish now with your report.'


def host(*argv):
    out = subprocess.run(["node", HOST, *argv], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(out.stderr.strip() or f"native-host {argv[0]} failed")
    return json.loads(out.stdout) if out.stdout.strip() else None


def tell(*argv):
    try:
        host(*argv)
    except RuntimeError as e:   # a stopped host refuses; the saved report settles the job on resume
        log(f"native-host {argv[0]}: {e}")


def pid_in(path):
    try:
        with open(path) as f:
            pid = int(json.load(f)["pid"])
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError, KeyError):
        return None


def saved(job):
    try:
        with open(os.path.join(REPORTS, job["id"] + ".json")) as f:
            return json.load(f)["agentId"] == job["agentId"]
    except (OSError, ValueError, KeyError):
        return False


async def dispatch(job, agent_id, retry=False):
    with open(job["jobPath"]) as f:
        request = json.load(f)
    schema = request.get("schema") or {"type": "string"}
    worker = agent(role=job["label"])
    try:
        try:
            result = await worker(request["prompt"] + (RETRY if retry else "") + RETURN, schema)
        except Exception:
            result = await worker(FIX, schema)   # one correction turn, same conversation
    except Exception as e:
        log(f"{job['label']}: agent failed: {e}")
        return tell("fail", ARGS, job["id"], f"Antigravity agent failed: {e}")
    finally:
        del worker
    report = os.path.join(REPORTS, job["id"] + ".json")
    with open(report + ".tmp", "w") as f:
        json.dump({"agentId": agent_id, "result": result}, f)
    os.replace(report + ".tmp", report)
    try:
        host("complete", ARGS, job["id"], report)
    except RuntimeError as e:
        tell("fail", ARGS, job["id"], f"report rejected: {e}")


def forward(logged=[0]):   # host.log lines (phases, jobs, STALL) into the workflow's log
    path = os.path.join(RUN, "host.log")
    if os.path.exists(path):
        with open(path, "rb") as f:
            f.seek(logged[0])
            text = f.read()
        logged[0] += len(text)
        for line in text.decode(errors="replace").splitlines():
            log(line)


os.makedirs(REPORTS, exist_ok=True)
other = pid_in(PIDFILE)
if other and other != os.getpid():
    raise RuntimeError(f"another bridge (pid {other}) is running this wave: let it finish, or stop it first")
with open(PIDFILE, "w") as f:
    json.dump({"pid": os.getpid()}, f)
stale = pid_in(os.path.join(RUN, "host.lock")) if RESUME else None
if stale and "native-host.mjs" in subprocess.run(["ps", "-p", str(stale), "-o", "command="],
                                                 capture_output=True, text=True).stdout:
    log(f"stopping the host a stopped workflow left running (pid {stale})")   # it would refuse --resume
    os.kill(stale, signal.SIGTERM)
    for _ in range(150):
        if not os.path.exists(os.path.join(RUN, "host.lock")):
            break
        await asyncio.sleep(0.2)
    else:
        raise RuntimeError(f"the host a stopped workflow left running (pid {stale}) did not stop in 30 s")
with open(os.path.join(RUN, "host.err"), "a") as err:
    proc = subprocess.Popen(["node", HOST, "serve", SCRIPT, ARGS] + (["--resume"] if RESUME else []),
                            stdout=subprocess.DEVNULL, stderr=err)
tasks, seen, started = [], set(), False

while proc.poll() is None:
    forward()
    state = host("status", ARGS) if os.path.exists(os.path.join(RUN, "state.json")) else {}
    if state.get("state") == "running" and state.get("pid") == proc.pid:
        if not started:   # jobs an earlier bridge bound before its workflow stopped
            started = True
            for job in [j for j in state["jobs"] if j["state"] == "running"]:
                seen.add(job["id"])
                if saved(job):
                    tell("complete", ARGS, job["id"], os.path.join(REPORTS, job["id"] + ".json"))
                else:
                    tasks.append(asyncio.ensure_future(dispatch(job, job["agentId"], retry=True)))
        live = sum(not t.done() for t in tasks)
        for job in state["jobs"]:
            if live >= MAX:
                break
            if job["state"] == "ready" and job["id"] not in seen:
                seen.add(job["id"])
                agent_id = f"agy-{uuid.uuid4().hex[:12]}"
                try:
                    host("bind", ARGS, job["id"], agent_id, job["label"])
                except RuntimeError as e:   # the host stopped since the status read
                    log(f"{job['label']}: not bound: {e}")
                    continue
                tasks.append(asyncio.ensure_future(dispatch(job, agent_id)))
                live += 1
    await asyncio.sleep(1)

forward()
if any(not t.done() for t in tasks):   # a stopped host: let writers finish rather than cut them off mid-edit
    log("native-host stopped; waiting for the running agents to finish and save their reports")
await asyncio.gather(*tasks)
os.remove(PIDFILE)
if proc.returncode:
    with open(os.path.join(RUN, "host.err")) as f:
        raise RuntimeError(f"native-host stopped (exit {proc.returncode}): {f.read().strip()[-2000:]}\n"
                           "Reconcile per references/antigravity.md, then run again with resume: true.")
print(json.dumps({"result": os.path.join(RUN, "result.json")}))
