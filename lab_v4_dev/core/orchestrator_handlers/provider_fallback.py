"""Provider-backed intent handler.

All provider-backed Orchestrator intents enter through HANDLER_REGISTRY.
This module is the single owner for intents whose implementation is provider
synthesis rather than a local domain operation.
"""

from lab_v4_dev.awareness.knowledge_retriever import resolve_project_scope
from lab_v4_dev.config.provider_config import get_active_provider
from lab_v4_dev.llm.prompt_builder import build_project_context


def handle_provider_intent(
    orchestrator,
    intent,
    *,
    target=None,
    raw=None,
    authorized_ask=None,
):
    if not callable(authorized_ask):
        return {
            "status": "denied",
            "intent": intent,
            "source": "provider_handler_capability_missing",
            "executed": False,
            "text": "لا توجد صلاحية مزوّد مرتبطة بقرار التوجيه النهائي.",
        }

    question = str(raw or "").strip()
    if not question:
        return {
            "status": "needs_clarification",
            "intent": intent,
            "source": "provider_handler_empty_request",
            "executed": False,
            "text": "لم يصل نص كافٍ لتنفيذ طلب الشرح أو التحليل.",
        }

    system = build_project_context(
        question=question,
        intent=intent,
        project_scope=resolve_project_scope(question, intent=intent),
    )
    result = authorized_ask(question, system=system, max_tokens=300)
    if not isinstance(result, dict):
        return {
            "status": "error",
            "intent": intent,
            "source": "provider_handler_invalid_result",
            "executed": False,
            "text": "أعاد المزوّد نتيجة غير صالحة.",
        }

    return {
        "status": result.get("status", "error"),
        "intent": intent,
        "source": result.get("provider_used") or get_active_provider(),
        "route": result.get("provider_used") or get_active_provider(),
        "text": result.get("text", result.get("message", "")),
        "tokens": result.get("tokens", 0),
        "executed": False,
    }
