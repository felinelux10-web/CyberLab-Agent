# CyberLab Agent v4.0
# core/state.py

import json
import os
from datetime import datetime

STATE_FILE = "lab_v4_dev/cache/state.json"

VALID_STATES = ["normal", "safe", "frozen"]

class AgentState:

    def __init__(self):
        self.mode = "normal"
        self.consecutive_failures = 0
        self.session_start = datetime.now().isoformat()
        self.last_error = None

    def can_edit_files(self):
        return self.mode == "normal"

    def can_execute(self):
        return self.mode in ["normal", "safe"]

    def enter_safe_mode(self, reason: str):
        self.mode = "safe"
        self.last_error = reason
        print(f"[STATE] SAFE MODE: {reason}")

    def enter_frozen_mode(self, reason: str):
        self.mode = "frozen"
        self.last_error = reason
        print(f"[STATE] FROZEN MODE: {reason}")

    def resume_normal(self):
        self.mode = "normal"
        self.consecutive_failures = 0
        self.last_error = None
        print("[STATE] NORMAL MODE resumed")

    def record_failure(self):
        self.consecutive_failures += 1
        return self.consecutive_failures

    def record_success(self):
        self.consecutive_failures = 0

    def save(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        data = {
            "mode": self.mode,
            "consecutive_failures": self.consecutive_failures,
            "session_start": self.session_start,
            "last_error": self.last_error,
            "saved_at": datetime.now().isoformat(),
        }
        with open(STATE_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def load(self):
        if not os.path.exists(STATE_FILE):
            return
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        self.mode = data.get("mode", "normal")
        self.consecutive_failures = data.get("consecutive_failures", 0)
        self.last_error = data.get("last_error")

    def status(self):
        return {
            "mode": self.mode,
            "failures": self.consecutive_failures,
            "can_edit": self.can_edit_files(),
            "can_execute": self.can_execute(),
            "last_error": self.last_error,
        }
