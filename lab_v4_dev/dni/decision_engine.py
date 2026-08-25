"""
DNI Decision Engine

Foundation only.

Future responsibilities:

- Decide conversation route
- Decide privacy route
- Decide memory updates
- Decide external provider usage
- Decide local execution
"""

class DecisionEngine:
    """
    DNI decision foundation.

    This component must not replace Orchestrator routing or execution.
    It currently provides no canonical runtime decision authority.
    """


    def __init__(self):
        self.version = "DNI-3.036"

    def decide(self):
        return {
            "decision": "none",
            "target": "none",
            "version": self.version
        }
