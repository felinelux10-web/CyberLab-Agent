"""
P05 — Dialogue Memory.

Owns dialogue state and reference resolution.
Does not route, execute, call providers, or decide intent.
"""

from __future__ import annotations

from lab_v4_dev.conversation.dialogue_contract import DialogueState


class DialogueMemory:
    """
    Conversation-owned dialogue coordinator.

    Responsibilities:
        - maintain DialogueState
        - maintain bounded dialogue history
        - resolve conversational references
        - manage pending topics

    Explicitly out of scope:
        - intent classification
        - routing
        - execution
        - provider selection
        - persistence
        - project/runtime state ownership
    """

    def __init__(self, context_store):
        self.context = context_store
        self.state = DialogueState()

    # --------------------------------------------------------
    # Compatibility properties
    # --------------------------------------------------------

    @property
    def last_topic(self):
        return self.state.last_topic

    @last_topic.setter
    def last_topic(self, value):
        self.state.last_topic = value

    @property
    def pending_topic(self):
        return self.state.pending_topic

    @pending_topic.setter
    def pending_topic(self, value):
        self.state.pending_topic = value

    @property
    def last_list(self):
        """Compatibility view of the bounded dialogue history."""
        history = getattr(self.state, "history", [])
        return list(history or [])

    @property
    def last_items(self):
        return self.state.last_items

    @last_items.setter
    def last_items(self, value):
        self.state.last_items = list(value or [])

    # --------------------------------------------------------
    # State lifecycle
    # --------------------------------------------------------


    def reset(self) -> None:
        """
        P06 — Reset dialogue-owned state.

        DialogueMemory owns DialogueState.
        Canonical execution ContextStore remains owned externally.
        """
        self.state = DialogueState()

    def update(
        self,
        text: str,
        result: dict,
        *,
        mode: str | None = None,
        parsed: dict | None = None,
    ) -> None:

        if not isinstance(result, dict):
            return

        if not result.get("text"):
            return

        parsed = parsed or {}

        intent = parsed.get("intent") or result.get("intent")
        target = parsed.get("target") or result.get("target")
        confidence = parsed.get("confidence", result.get("confidence", 0.0))

        self.state.last_mode = mode or result.get("mode")
        self.state.last_intent = intent
        self.state.last_target = target

        try:
            self.state.last_confidence = float(confidence or 0.0)
        except (TypeError, ValueError):
            self.state.last_confidence = 0.0

        topic = self._derive_topic(text, target)

        # Follow-up turns do not replace the active topic.
        if self.state.last_mode != "FOLLOW_UP" and topic:
            self.state.last_topic = topic

        self.state.add_turn(
            role="user",
            content=text,
            mode=self.state.last_mode,
            intent=intent,
            target=target,
            confidence=self.state.last_confidence,
        )

        self.state.add_turn(
            role="assistant",
            content=result.get("text", ""),
            mode=self.state.last_mode,
            intent=intent,
            target=target,
            confidence=self.state.last_confidence,
        )

        items = result.get("items") or result.get("files") or []
        if items:
            self.state.last_items = list(items)

    def _derive_topic(self, text: str, target=None):
        if target:
            return str(target)

        for token in str(text).split():
            cleaned = token.strip(".,،؛:!?؟()[]{}\"'")
            if cleaned.endswith(".py"):
                return cleaned

        return text.strip() or None

    # --------------------------------------------------------
    # Topic lifecycle
    # --------------------------------------------------------

    def save_pending(self, topic: str):
        self.state.pending_topic = topic

    def restore_pending(self) -> str | None:
        topic = self.state.pending_topic
        self.state.pending_topic = None
        return topic

    # --------------------------------------------------------
    # Reference resolution
    # --------------------------------------------------------

    def resolve_references(self, text: str) -> str:
        text = str(text)
        topic = self.state.last_topic

        if not topic:
            return text

        replacements = {
            "هذا": topic,
            "هذه": topic,
            "ذلك": topic,
            "تلك": topic,
            "نفسه": topic,
            "نفسها": topic,
            "بهذا": topic,
            "بهذه": topic,
            "لهذا": topic,
            "السابق": topic,
            "السابقة": topic,
        }

        resolved = text

        # Specific constructions first.
        specific = (
            ("علاقته بهذا", f"ما علاقة {topic} بالمشروع؟"),
            ("علاقته بهذه", f"ما علاقة {topic} بالمشروع؟"),
            ("دوره في هذا", f"{topic} ما دوره في المشروع؟"),
            ("دوره في هذه", f"{topic} ما دوره في المشروع؟"),
        )

        for source, replacement in specific:
            if source in resolved:
                return replacement

        # Follow-up questions that omit the subject.
        prefixes = (
            "ما دوره",
            "ما وظيفته",
            "ما علاقتة",
            "ما علاقته",
            "كيف يعمل",
            "هل هو مهم",
            "هل تنصحني",
        )

        if resolved.strip() == text.strip():
            stripped = text.strip()

            if stripped.startswith("ولماذا"):
                return f"{topic} لماذا؟"

            if stripped.startswith("لماذا"):
                return f"{topic} لماذا؟"

            if stripped.startswith("ماذا عن"):
                return f"{topic} {stripped}"

            if stripped.startswith("وماذا عن"):
                return f"{topic} {stripped[1:]}"

            if stripped.startswith("وما علاقته"):
                return f"{topic} {stripped[1:]}"

            if stripped.startswith("ما علاقته"):
                return f"{topic} {stripped}"

            if stripped.startswith("وأيهما"):
                return f"{topic} {stripped[1:]}"

            if stripped.startswith(prefixes):
                return f"{topic} {stripped}"

        for source, replacement in replacements.items():
            if source in resolved:
                resolved = resolved.replace(source, replacement)

        if (
            "الحل الثاني" in resolved
            and len(self.state.last_items) >= 2
        ):
            resolved = resolved.replace(
                "الحل الثاني",
                str(self.state.last_items[1]),
            )

        return resolved

    # --------------------------------------------------------
    # Read-only inspection
    # --------------------------------------------------------

    def snapshot(self) -> dict:
        return self.state.snapshot()
