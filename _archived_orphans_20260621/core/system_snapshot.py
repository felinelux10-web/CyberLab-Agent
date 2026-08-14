import json
import os
from datetime import datetime

SNAPSHOT_PATH = os.path.expanduser("~/cyberlab_agent/runtime_snapshot.json")

def create_snapshot(state, graph=None, ledger=None):
    snapshot = {
        "version": getattr(state, "version", None),
        "timestamp": str(datetime.now()),
        "graph_size": len(graph.get("nodes", {})) if graph else 0,
        "ledger_size": len(ledger) if ledger else 0
    }

    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)

    return snapshot

def load_snapshot():
    if not os.path.exists(SNAPSHOT_PATH):
        return None
    with open(SNAPSHOT_PATH, "r") as f:
        return json.load(f)
