# CyberLab Agent v4.7
# context/context_store.py — Context Graph

import re

class ContextStore:

    def __init__(self):
        self.last_intent   = None
        self.last_target   = None
        self.last_result   = None
        self.history       = []
        self.current_subject  = None
        self.current_version  = None
        self.current_file     = None
        self.current_analysis = None

    def update(self, intent, target=None, result=None):
        self.last_intent = intent
        self.last_target = target
        self.last_result = result
        if target:
            self._extract_context(target)
        self.history.append({
            "intent" : intent,
            "target" : target,
            "subject": self.current_subject,
            "version": self.current_version,
        })
        if len(self.history) > 20:
            self.history.pop(0)
        if result and result.get("text"):
            self.current_analysis = result["text"][:500]

    def _extract_context(self, text: str):
        v = re.search(r"v?4\.(\d)", str(text))
        if v:
            self.current_version = f"4.{v.group(1)}"
            self.current_subject = f"version_{self.current_version}"
        f = re.search(r"[\w./]+\.py", str(text))
        if f:
            self.current_file    = f.group(0)
            self.current_subject = self.current_file

    def resolve(self, text: str) -> dict:
        resolved = {
            "subject" : self.current_subject,
            "version" : self.current_version,
            "file"    : self.current_file,
            "analysis": self.current_analysis,
        }
        ref_words = ["فيه","منه","عنه","معه","هذا","هذه","نفس","السابق","الإصدار"]
        resolved["is_reference"] = any(w in text for w in ref_words)
        return resolved

    def get_last(self):
        return {
            "intent"  : self.last_intent,
            "target"  : self.last_target,
            "result"  : self.last_result,
            "subject" : self.current_subject,
            "version" : self.current_version,
            "file"    : self.current_file,
        }
