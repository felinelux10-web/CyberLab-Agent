"""
DNI Cognitive Profile

Responsible for the live cognitive state.

Current stage:
Foundation only.

Future responsibilities:

- Conversation Style
- User Intent Style
- Urgency Detection
- Conversation Depth
- Emotional State
- Thinking Mode
"""

class CognitiveProfile:

    def __init__(self):
        self.profile = {
            "conversation_mode": "normal",
            "depth": "unknown",
            "urgency": "unknown",
            "emotion": "neutral",
            "thinking_mode": "normal"
        }

    def snapshot(self):
        return self.profile.copy()
