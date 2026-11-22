from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory


class RecordingOrchestrator:
    def __init__(self):
        self.context = ContextStore()
        self.calls = []

    def handle(self, text, parsed=None, **kwargs):
        self.calls.append((text, dict(parsed or {}), kwargs))
        return {
            "status": "success",
            "intent": (parsed or {}).get("intent"),
            "text": "unexpected orchestrator dispatch",
        }


def test_attached_lam_dialogue_opening_survives_provider_failure_and_mesopotamia_followup(monkeypatch):
    orchestrator = RecordingOrchestrator()
    memory = DialogueMemory(orchestrator.context)
    manager = ConversationManager(orchestrator, memory)
    prompts = []
    responses = iter([
        {"status": "error", "message": "provider offline", "source": "llm"},
        {
            "status": "success",
            "text": "بلاد الرافدين من أقدم مراكز نشوء المدن والكتابة.",
            "provider_used": "test",
        },
    ])

    def controlled_gateway(prompt, **kwargs):
        prompts.append(prompt)
        return next(responses)

    monkeypatch.setattr(
        "lab_v4_dev.conversation.conversation_manager.gateway_ask",
        controlled_gateway,
    )

    first = manager.process("لنتحدث عن مصر القديمة والأهرامات.")

    assert first["status"] == "error"
    assert memory.state.failed_exchange_archive
    failed = memory.state.failed_exchange_archive[-1]
    assert failed["user"] == "لنتحدث عن مصر القديمة والأهرامات."
    assert failed["target"] == "مصر القديمة والأهرامات"
    assert failed["response_failed"] is True
    assert failed["assistant"] == ""

    # Reproduce the live-state variant in which the topic survived but the
    # entity classifier did not persist a type.
    memory.state.last_entity_type = None
    branch = memory.active_dialogue_branch()
    assert branch["entity"] == "مصر القديمة والأهرامات"
    assert branch["source_archive"] == "failed_exchange_archive"

    result = manager.process("وماذا عن بلاد الرافدين؟")

    assert result["status"] == "success", result
    assert result["route_decision"].route == "L-LIVE"
    assert result["semantic_request"]["context_transition"] == "continue"
    assert len(prompts) == 2
    assert "لنتحدث عن مصر القديمة والأهرامات." in prompts[-1]
    assert "وماذا عن بلاد الرافدين؟" in prompts[-1]
    assert "SQL Injection" not in prompts[-1]
    assert orchestrator.calls == []
