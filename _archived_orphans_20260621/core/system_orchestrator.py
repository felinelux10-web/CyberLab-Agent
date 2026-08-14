from core.system_state import STATE, repair_state
from core.system_snapshot import load_snapshot
from core.context_graph import load_graph


class SystemOrchestrator:
    def __init__(self):
        self.state = STATE
        self.snapshot = None
        self.graph = None

    def _fuse_context(self):
        fused = {
            "state_version": self.state.version,
            "snapshot_version": self.snapshot.get("version") if self.snapshot else None,
            "graph_nodes": len(self.graph.get("nodes", {})) if self.graph else 0,
            "consistency": True
        }

        if self.snapshot and self.snapshot.get("version") != self.state.version:
            fused["consistency"] = False
            self.state.version = self.snapshot.get("version")

        return fused

    def boot(self):
        self.snapshot = load_snapshot()
        self.graph = load_graph()

        repair_state(self.state)

        fused = self._fuse_context()

        return {
            "status": "booted",
            "fused_context": fused,
            "version": self.state.version,
            "graph_nodes": len(self.graph.get("nodes", {})) if self.graph else 0,
            "snapshot": self.snapshot
        }

    def repair(self):
        return repair_state(self.state)

    def get_system_state(self):
        return {
            "state_version": self.state.version,
            "snapshot": self.snapshot,
            "graph": self.graph
        }
