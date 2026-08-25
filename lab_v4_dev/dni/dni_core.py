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
        """
        Deprecated compatibility hook.

        DialogueMemory is owned by the conversation/memory layer.
        DNI does not retain or own the supplied instance.
        """
        return False

    def has_dialogue_memory(self):
        """DNI no longer owns DialogueMemory."""
        return False

    def get_dialogue_memory(self):
        """Deprecated compatibility hook; DNI does not own DialogueMemory."""
        return None

    def get_last_message(self):
        """DNI does not own or inspect dialogue history."""
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

        return {
            "attached": False,
            "analysis": analysis,
            "intent": analysis.get("intent"),
            "mode": analysis.get("mode"),
            "last_topic": None,
            "pending_topic": None,
            "messages": 0,
        }


    def cognitive_snapshot(self):
        return {
            "conversation": self.conversation_snapshot(),
            "analysis_available": bool(self.last_analysis),
            "memory_attached": False,
        }


    def conversation_summary(self):
        """Compatibility snapshot; dialogue history remains externally owned."""
        return {
            "attached": False,
            "messages": 0,
            "pending_topic": None,
            "last_topic": None,
            "last_user": None,
            "last_assistant": None,
            "last_role": None,
            "last_content": None,
        }
