# CyberLab Agent v4.6
# context/context_store.py

class ContextStore:

    def __init__(self):
        self.last_intent = None
        self.last_target = None
        self.last_result = None
        self.history     = []

    def update(self, intent, target=None, result=None):
        self.last_intent = intent
        self.last_target = target
        self.last_result = result
        self.history.append({
            "intent": intent,
            "target": target,
        })
        if len(self.history) > 20:
            self.history.pop(0)

    def get_last(self):
        return {
            "intent": self.last_intent,
            "target": self.last_target,
            "result": self.last_result,
        }
