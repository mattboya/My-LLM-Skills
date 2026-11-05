#!/usr/bin/env python3
"""List the Gemini models this Antigravity account can pick, with quota left.

Reads the running Antigravity app's local server. Usage: agy-models.py
"""
import glob, json, os, re, ssl, sys, urllib.request
from datetime import datetime

home = os.path.expanduser("~/.gemini/antigravity")
hubs = sorted(glob.glob(f"{home}/daemon/hub_*.json"), key=os.path.getmtime)
if not hubs:
    sys.exit("Antigravity isn't running: no daemon/hub_*.json")
hub = json.load(open(hubs[-1]))
req = urllib.request.Request(
    f"https://127.0.0.1:{hub['httpsPort']}/exa.language_server_pb.LanguageServerService/GetUserStatus",
    data=b'{"metadata":{"ideName":"antigravity","extensionName":"antigravity","locale":"en"}}',
    headers={"Content-Type": "application/json", "X-Codeium-Csrf-Token": hub["csrfToken"]},
)
try:
    # ponytail: the app's own self-signed cert on localhost
    status = json.load(urllib.request.urlopen(req, context=ssl._create_unverified_context(), timeout=5))
except OSError as e:
    sys.exit(f"Antigravity's local server didn't answer ({e}); is the app open?")

models = status["userStatus"]["cascadeModelConfigData"]["clientModelConfigs"]
state = open(f"{home}/antigravity_state.pbtxt").read()
picked = re.search(r"last_selected_agent_model: (\S+)", state)
labels = {m["modelOrAlias"].get("model"): m["label"] for m in models}
print("picker is on:", labels.get(picked and picked.group(1), "unknown"))
for m in models:
    if not m["label"].startswith("Gemini") or m.get("disabled"):
        continue
    q = m.get("quotaInfo", {})
    left = f"{round(q['remainingFraction'] * 100)}% left" if "remainingFraction" in q else "quota unknown"
    refill = q.get("resetTime")
    if refill:
        refill = datetime.fromisoformat(refill.replace("Z", "+00:00")).astimezone().strftime("%a %-I:%M%p")
        left += f", refills {refill}"
    print(f"{m['label']}: {left}")
