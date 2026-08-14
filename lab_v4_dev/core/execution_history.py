# CyberLab Agent v5.0
# core/execution_history.py

import json
import os
from datetime import datetime

HISTORY_FILE = "workspace/run_history"

def save_run(script, status, duration, exit_code=0, error=""):
    os.makedirs(HISTORY_FILE, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    data = {
        "timestamp": datetime.now().isoformat(),
        "script"   : script,
        "status"   : status,
        "duration" : round(duration, 2),
        "exit_code": exit_code,
        "error"    : error[:200] if error else "",
    }
    path = os.path.join(HISTORY_FILE, f"run_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

def get_history(limit=10):
    if not os.path.exists(HISTORY_FILE):
        return []
    files = sorted(os.listdir(HISTORY_FILE), reverse=True)
    history = []
    for f in files[:limit]:
        if f.endswith(".json"):
            with open(os.path.join(HISTORY_FILE, f)) as fp:
                history.append(json.load(fp))
    return history

def get_script_stats(script_name):
    history = get_history(50)
    runs    = [r for r in history if script_name in r.get("script","")]
    success = sum(1 for r in runs if r["status"] == "success")
    failed  = sum(1 for r in runs if r["status"] != "success")
    return {"total": len(runs), "success": success, "failed": failed}
