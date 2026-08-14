"""
DNI Cognitive State

Single live cognitive state.

Foundation only.

Future responsibilities:

- Active conversation state
- Active project state
- Active user state
- Active reasoning state
- Runtime cognitive snapshot
"""

class CognitiveState:

    def __init__(self):
        self.state = {
            "conversation": {},
            "project": {},
            "user": {},
            "reasoning": {},
            "runtime": {}
        }

    def snapshot(self):
        return self.state.copy()
