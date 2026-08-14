"""
Series 8 — Runtime Manager

المسؤولية:
- تجميع مكونات Runtime في نقطة واحدة.
"""

from .runtime_state import RuntimeState
from .runtime_context import RuntimeContext
from .runtime_environment import RuntimeEnvironment
from .runtime_monitor import RuntimeMonitor
from .runtime_lifecycle import RuntimeLifecycle
from .runtime_snapshot import RuntimeSnapshot


class RuntimeManager:

    def __init__(self):
        self.state = RuntimeState()
        self.context = RuntimeContext()
        self.environment = RuntimeEnvironment()
        self.monitor = RuntimeMonitor()
        self.lifecycle = RuntimeLifecycle()
        self.snapshot = RuntimeSnapshot()


    def start(self, operation="boot", project=None, goal=None, phase=None):
        self.lifecycle.start()
        self.state.begin(operation, project=project)
        self.context.update(
            project=project,
            goal=goal,
            phase=phase,
        )

    def update_active_file(self, active_file):
        self.context.update(active_file=active_file)

    def end(self, snapshot_data=None):
        self.state.end()
        if snapshot_data is not None:
            self.snapshot.capture(snapshot_data)
        self.monitor.check()

    def pause(self):
        self.lifecycle.pause()

    def resume(self):
        self.lifecycle.resume()

    def stop(self):
        self.lifecycle.stop()

    def update_context(self, **kwargs):
        self.context.update(**kwargs)

    def snapshot_capture(self, data):
        self.snapshot.capture(data)

    def monitor_check(self):
        self.monitor.check()

    def status(self):
        return {
            "state": self.state.to_dict(),
            "context": self.context.to_dict(),
            "environment": self.environment.to_dict(),
            "monitor": self.monitor.to_dict(),
            "lifecycle": self.lifecycle.to_dict(),
            "snapshot": self.snapshot.to_dict(),
        }
