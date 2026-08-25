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
    """
    DNI-owned cognitive state only.

    Ownership contract:
    - ContextStore owns operational/dialogue execution context.
    - MemoryStore/DialogueMemory own memory/history concerns.
    - CognitiveState owns DNI cognitive signals only.
    - This object must not become a ContextStore or MemoryStore.
    """


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
