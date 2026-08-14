
from core.system_state import STATE, repair_state
from core.context_graph import load_graph, get_graph
from core.system_snapshot import create_snapshot

def boot_system():
    # 1. repair state (critical fix)
    repair_state(STATE)

    # 2. load graph
    load_graph()
    graph = get_graph()

    # 3. snapshot after recovery
    snapshot = create_snapshot(STATE, graph, None)

    return {
        "status": "booted",
        "version": STATE.version,
        "graph_nodes": len(graph.get("nodes", {})),
        "snapshot": snapshot
    }


def shutdown_system():
    graph = get_graph()
    return create_snapshot(STATE, graph, None)
