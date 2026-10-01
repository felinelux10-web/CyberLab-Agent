from lab_v4_dev.core.agent import Agent
from lab_v4_dev.core.contracts import PreparedExecutionRequest
from lab_v4_dev.conversation import conversation_manager as conversation_module
from lab_v4_dev.executor.contracts import ExecutionResult
from lab_v4_dev.loop.event_loop import EventLoop
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.matcher import match
from lab_v4_dev.intent.intents import Intent


class FakeState:
    mode = "normal"

    def can_execute(self):
        return True

    def can_edit_files(self):
        return True

    def record_success(self):
        pass

    def record_failure(self):
        pass


class FakeMemory:
    tasks = None
    lessons = None


def test_prepared_path_uses_planner_adapter_executor_without_raw_parser(monkeypatch):
    calls = []

    def forbidden_parser(_):
        raise AssertionError("RAW_PARSER_MUST_NOT_BE_CALLED")

    def fake_execute(self, request):
        calls.append(request)
        return ExecutionResult(
            status="success",
            plan_id=request.plan_id,
            step_id=request.step_id,
            action=request.action,
            stdout="PREPARED_PATH_OK",
        )

    monkeypatch.setattr(
        "lab_v4_dev.loop.event_loop.parse",
        forbidden_parser,
    )
    monkeypatch.setattr(
        "lab_v4_dev.executor.executor.Executor.execute",
        fake_execute,
    )

    loop = EventLoop(
        FakeState(),
        None,
        memory=FakeMemory(),
    )

    prepared = PreparedExecutionRequest(
        intent={
            "intent": "run_command",
            "target": "shell",
            "context": "system",
        },
        request_id="prepared-test-01",
        metadata={
            "execution": {
                "action": "run_command",
                "parameters": {
                    "command": "echo PREPARED_PATH_OK",
                },
            }
        },
    )

    loop.submit_prepared(prepared)
    result = loop.tick()

    assert result["status"] == "executed"
    assert len(calls) == 1

    request = calls[0]
    assert request.plan_id == "prepared-test-01"
    assert request.step_id == "step-1"
    assert request.action == "run_command"
    assert request.parameters["command"] == "echo PREPARED_PATH_OK"
    assert request.metadata["source"] == "p10_plan"

    assert result["results"][0]["status"] == "success"
    assert result["results"][0]["stdout"] == "PREPARED_PATH_OK"


def test_snapshot_personal_chat_and_fuzzy_matching_regression(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        conversation_module,
        "gateway_ask",
        lambda *_args, **_kwargs: {
            "status": "success",
            "text": "أهلًا بك.",
            "provider_used": "offline-test",
        },
    )

    # Snapshot-style natural conversation must remain PERSONAL_CHAT.
    parsed_chat = parse("مرحبا")
    assert parsed_chat["intent"] == Intent.PERSONAL_CHAT

    # Canonical parser must preserve PERSONAL_CHAT for close conversational input.
    parsed_fuzzy_chat = parse("مرحببا")
    assert parsed_fuzzy_chat["intent"] == Intent.PERSONAL_CHAT

    # Verify the normal Agent.run() path still accepts the same chat input.
    agent = Agent()
    assert agent.boot() is True

    result = agent.run("مرحبا")
    assert isinstance(result, dict)
    assert result.get("status") == "success"
