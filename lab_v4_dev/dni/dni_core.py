"""
DNI Core

Central coordinator for the DNI layer.

Current stage:
Foundation only.

Future responsibilities:

- Hold Brain
- Hold Cognitive State
- Expose unified cognitive interface
"""

from lab_v4_dev.dni.dni_brain import DNIBrain
from lab_v4_dev.dni.cognitive_state import CognitiveState
from lab_v4_dev.dni.policy_engine import PolicyEngine
from lab_v4_dev.dni.knowledge_map import KnowledgeMap
from lab_v4_dev.dni.cognitive_classifier import CognitiveClassifier


class DNICore:
    """
    DNI cognitive coordination boundary.

    DNI does not own:
    - Core orchestration/runtime execution
    - ContextStore
    - MemoryStore/DialogueMemory
    - Intent parsing/routing
    - persistent user-profile storage

    External state/profile/context may be supplied explicitly by the
    canonical owning subsystem.
    """


    def __init__(self):
        self.brain = DNIBrain()
        self.state = CognitiveState()
        self.policy = PolicyEngine()
        self.knowledge = KnowledgeMap()
        self.classifier = CognitiveClassifier()
        self.last_analysis = {}
        self._dialogue_memory_ref = None

    def status(self):
        return {
            "core": "ready",
            "brain": self.brain.status(),
            "state": self.state.snapshot(),
            "policy": self.policy.status(),
            "knowledge": self.knowledge.status(),
            "profile_loaded": False,
            "profile_keys": [],
            "profile_source": None,
            "conversation": self.cognitive_snapshot(),
            "version": "DNI-3.036"
        }


    def get_profile(self):
        """Deprecated compatibility hook; DNI does not own persistent profile data."""
        return {}


    def get_profile_value(self, key, default=None):
        """Deprecated compatibility hook; persistent profile is externally owned."""
        return default


    def has_profile_key(self, key):
        """Deprecated compatibility hook; DNI owns no persistent profile."""
        return False


    def profile_summary(self):
        """Deprecated compatibility hook; no persistent profile is owned by DNI."""
        return {
            "loaded": False,
            "keys": [],
            "count": 0,
            "source": None,
        }


    def attach_dialogue_memory(self, memory):
        """Attach a read-only integration reference; ownership stays external."""
        if memory is None:
            return False
        self._dialogue_memory_ref = memory
        return True

    def has_dialogue_memory(self):
        return self._dialogue_memory_ref is not None

    def get_dialogue_memory(self):
        """Return the externally-owned reference for inspection only."""
        return self._dialogue_memory_ref

    def get_last_message(self):
        """Read the latest message through the external dialogue owner."""
        memory = self._dialogue_memory_ref
        if memory is not None:
            history = getattr(getattr(memory, "state", None), "history", [])
            if history:
                last = history[-1]
                return {
                    "role": last.get("role"),
                    "content": last.get("content"),
                }
        return {
            "role": None,
            "content": None,
        }


    def set_conversation_analysis(self, analysis):
        """Store cognitive analysis signals without retaining conversation state."""
        self.last_analysis = dict(analysis or {})


    def analyze_conversation(self):
        return {
            "conversation_available": False,
            "last_message": self.get_last_message(),
            "analysis": dict(self.last_analysis),
        }


    def conversation_snapshot(self):
        analysis = dict(getattr(self, "last_analysis", {}))
        memory = self._dialogue_memory_ref
        state = getattr(memory, "state", None) if memory is not None else None

        return {
            "attached": memory is not None,
            "analysis": analysis,
            "intent": analysis.get("intent"),
            "mode": analysis.get("mode"),
            "last_topic": getattr(state, "last_topic", None),
            "pending_topic": getattr(state, "pending_topic", None),
            "messages": len(getattr(state, "turns", []) or []),
        }


    def cognitive_snapshot(self):
        attached = self._dialogue_memory_ref is not None
        return {
            "conversation": self.conversation_snapshot(),
            "analysis_available": bool(self.last_analysis),
            "memory_attached": attached,
        }


    def conversation_summary(self):
        """Read-only summary; dialogue history remains externally owned."""
        memory = self._dialogue_memory_ref
        state = getattr(memory, "state", None) if memory is not None else None
        history = getattr(state, "history", []) if state is not None else []
        last_user = next((item for item in reversed(history) if item.get("role") == "user"), {})
        last_assistant = next((item for item in reversed(history) if item.get("role") == "assistant"), {})
        return {
            "attached": memory is not None,
            "messages": len(history),
            "pending_topic": getattr(state, "pending_topic", None),
            "last_topic": getattr(state, "last_topic", None),
            "last_user": last_user.get("content"),
            "last_assistant": last_assistant.get("content"),
            "last_role": (history[-1].get("role") if history else None),
            "last_content": (history[-1].get("content") if history else None),
        }
