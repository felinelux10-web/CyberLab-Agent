# CyberLab Agent v4.7
# context/context_store.py — Context Graph

import re
from datetime import datetime

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
        from lab_v4_dev.memory.intelligence import memory_metadata
        self.history.append({
            **memory_metadata(
                "short_term_execution_context",
                source="context_store",
                confidence="observed",
                importance=0.55,
                scope="active_project",
            ),
            "intent": str(intent or ""),
            "target": target,
            "subject": self.current_subject,
            "version": self.current_version,
        })
        if len(self.history) > 20:
            self.history.pop(0)
        if result and result.get("text"):
            self.current_analysis = result["text"][:500]

    def _extract_context(self, text: str):
        version = re.search(r"(?<![\w])v?(\d+(?:\.\d+){1,3}(?:-[\w.-]+)?)(?![\w])", str(text))
        if version:
            self.current_version = version.group(1)
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

    def search_history(self, query: str, limit: int = 5) -> list:
        """Retrieve context entries by relevance, not only by recency."""
        from lab_v4_dev.memory.intelligence import rank_memory_records
        return rank_memory_records(
            query, self.history, fields=("intent", "target", "subject", "version"),
            minimum_score=0.15, limit=max(1, min(20, int(limit))),
        )

    def snapshot(self) -> dict:
        return {
            "schema_version": 1,
            "memory_type": "short_term_execution_context",
            "last_intent": self.last_intent,
            "last_target": self.last_target,
            "current_subject": self.current_subject,
            "current_version": self.current_version,
            "current_file": self.current_file,
            "current_analysis": self.current_analysis,
            "history": [dict(item) for item in self.history],
        }

    def clear(self):
        self.last_intent = None
        self.last_target = None
        self.last_result = None
        self.history = []
        self.current_subject = None
        self.current_version = None
        self.current_file = None
        self.current_analysis = None

    def get_last(self):
        return {
            "intent": self.last_intent,
            "target": self.last_target,
            "result": self.last_result,
            "subject": self.current_subject,
            "version": self.current_version,
            "file": self.current_file,
        }
