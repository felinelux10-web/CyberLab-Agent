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
from lab_v4_dev.user_data.profile_loader import load_profile
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory


class DNICore:

    def __init__(self):
        self.brain = DNIBrain()
        self.state = CognitiveState()
        self.policy = PolicyEngine()
        self.knowledge = KnowledgeMap()
        self.classifier = CognitiveClassifier()
        self.profile = load_profile()
        self.dialogue_memory = None
        self.last_analysis = {}
        self.profile_source = "user_profile.json"

    def status(self):
        return {
            "core": "ready",
            "brain": self.brain.status(),
            "state": self.state.snapshot(),
            "policy": self.policy.status(),
            "knowledge": self.knowledge.status(),
            "profile_loaded": isinstance(self.profile, dict),
            "profile_keys": sorted(self.profile.keys()),
            "profile_source": self.profile_source,
            "conversation": self.cognitive_snapshot(),
            "version": "DNI-3.036"
        }


    def get_profile(self):
        return self.profile


    def get_profile_value(self, key, default=None):
        return self.profile.get(key, default)


    def has_profile_key(self, key):
        return key in self.profile


    def profile_summary(self):
        return {
            "loaded": isinstance(self.profile, dict),
            "keys": sorted(self.profile.keys()),
            "count": len(self.profile),
            "source": self.profile_source,
        }


    def attach_dialogue_memory(self, memory):
        self.dialogue_memory = memory

    def has_dialogue_memory(self):
        return self.dialogue_memory is not None

    def get_dialogue_memory(self):
        return self.dialogue_memory

    def get_last_message(self):
        s = self.conversation_summary()

        return {
            "role": s.get("last_role"),
            "content": s.get("last_content")
        }

    def set_conversation_analysis(self, analysis):
        self.last_analysis = dict(analysis)

    def analyze_conversation(self):
        return {
            "conversation_available": self.has_dialogue_memory(),
            "last_message": self.get_last_message(),
            "analysis": dict(self.last_analysis)
        }


    def conversation_snapshot(self):
        summary = self.conversation_summary()
        analysis = dict(getattr(self, "last_analysis", {}))
        memory = self.dialogue_memory

        return {
            "attached": self.has_dialogue_memory(),
            "analysis": analysis,
            "intent": analysis.get("intent"),
            "mode": analysis.get("mode"),
            "last_topic": getattr(memory, "last_topic", None) if memory else None,
            "pending_topic": getattr(memory, "pending_topic", None) if memory else None,
            "messages": summary.get("messages", 0),
        }


    def cognitive_snapshot(self):
        return {
            "conversation": self.conversation_snapshot(),
            "analysis_available": bool(self.last_analysis),
            "memory_attached": self.has_dialogue_memory(),
        }

    def conversation_summary(self):
        if not self.dialogue_memory:
            return {
                "attached": False,
                "messages": 0,
                "pending_topic": None,
                "last_user": None,
                "last_assistant": None
            }

        history = getattr(self.dialogue_memory, "last_list", [])

        last = history[-1] if history else {}

        return {
            "attached": True,
            "messages": len(history),
            "pending_topic": getattr(self.dialogue_memory, "pending_topic", None),
            "last_role": last.get("role"),
            "last_content": last.get("content")
        }
