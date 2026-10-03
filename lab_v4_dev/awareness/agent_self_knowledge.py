"""Curated, source-linked facts for questions about this CyberLab Agent.

This is deliberately a small knowledge manifest, not a second intent parser or
runtime capability scanner. Each statement is emitted only while at least one
referenced source file exists in the current checkout.
"""
from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]

_AGENT_SELF_INTENTS = frozenset({
    "agent_identity",
    "agent_capabilities",
    "agent_architecture",
    "agent_execution_flow",
    "agent_limits",
})

# Statements are reviewed against these source paths. Keep claims narrow enough
# that each cited file supports the complete statement and its qualifications.
_FACTS = (
    (
        "واجهة التشغيل هنا هي تطبيق CyberLab Agent مكتوب ببايثون. نقطة CLI في "
        "run.py تستقبل السطر، تستدعي Agent.run ثم تعرض النتيجة؛ لا يجعل ذلك "
        "ملف العرض مالكًا للحوار أو التوجيه.",
        ("run.py", "lab_v4_dev/core/agent.py"),
    ),
    (
        "Agent.boot يهيئ ProjectMetadata وAgentState وDatabase وMemoryStore و"
        "EventLoop وContextStore وOrchestrator وDNICore وConversationManager؛ "
        "هذه وحدات تطبيق، وليست وصفًا لبنية نموذج لغوي داخلي.",
        ("lab_v4_dev/core/agent.py",),
    ),
    (
        "في المسار الرئيسي، Agent.run يبني Request من الإدخال ويمرر raw_text إلى "
        "ConversationManager.process. ويسجل المهمة في Session عند نجاح نتيجة "
        "نُفذت بالفعل.",
        ("lab_v4_dev/core/agent.py", "lab_v4_dev/core/contracts.py"),
    ),
    (
        "ConversationManager هو حدّ دورة الحوار: يستدعي ModeDetector لوصف نمط "
        "الرسالة، ثم IntentParser للنية canonical، ويحسم انتقال السياق، ثم يوجه "
        "النية القابلة للتنفيذ إلى Orchestrator أو الرسالة الحوارية إلى "
        "build_chat_prompt وLLM Gateway.",
        (
            "lab_v4_dev/conversation/conversation_manager.py",
            "lab_v4_dev/conversation/mode_detector.py",
            "lab_v4_dev/intent/intent_parser.py",
            "lab_v4_dev/llm/prompt_builder.py",
            "lab_v4_dev/llm/gateway.py",
        ),
    ),
    (
        "ConversationSemantics يصنف مجال الرسالة والفعل الحواري وسمات الصياغة؛ "
        "هو signal دلالي لا يختار route تنفيذيًا ولا يحل محل IntentParser.",
        (
            "lab_v4_dev/nlu/conversation_semantics.py",
            "lab_v4_dev/conversation/semantic_contract.py",
            "lab_v4_dev/intent/intent_parser.py",
        ),
    ),
    (
        "DialogueMemory يملك حالة الحوار وسجل الأدوار والموضوعات والمراجع. "
        "ContextStore يملك سياق التنفيذ. وNLU context resolver ذاكرة منفصلة "
        "محدودة بزمن، فلا ينبغي وصفها كمالك لسياق الحوار.",
        (
            "lab_v4_dev/conversation/dialogue_memory.py",
            "lab_v4_dev/context/context_store.py",
            "lab_v4_dev/nlu/context_resolver.py",
            "lab_v4_dev/core/agent.py",
        ),
    ),
    (
        "MemoryStore واجهة ملكية لذاكرة الجلسة وسجل المهام والدروس؛ لا يملك "
        "DialogueMemory أو سياق المحادثة أو التوجيه. DNICore يحتفظ بإشارات "
        "تحليل الحوار التي يمررها ConversationManager، لكنه لا يملك تاريخ الحوار "
        "أو Intent parsing أو تنفيذ Orchestrator.",
        (
            "lab_v4_dev/memory/store.py",
            "lab_v4_dev/dni/dni_core.py",
            "lab_v4_dev/conversation/conversation_manager.py",
        ),
    ),
    (
        "أسئلة هوية الوكيل وقدراته وبنيته ومسار الرسالة وحدوده لها AGENT_* intents "
        "canonical غير تنفيذية. يرفق ConversationManager حقائق هذا الملخص في "
        "system prompt ثم يطلب من Gateway صياغة الرد؛ لا يرسل هذه الأسئلة إلى "
        "Orchestrator كعمليات.",
        (
            "lab_v4_dev/intent/intents.py",
            "lab_v4_dev/intent/intent_parser.py",
            "lab_v4_dev/conversation/conversation_manager.py",
            "lab_v4_dev/llm/prompt_builder.py",
            "lab_v4_dev/llm/gateway.py",
        ),
    ),
    (
        "Prompt Builder يبني prompt المحادثة. build_project_context منفصل ويقرأ "
        "فهارس المشروع وroadmap؛ لا يُستخدم هذا السياق العام بديلًا عن سجل "
        "Agent Self-Knowledge في أسئلة الهوية والبنية.",
        (
            "lab_v4_dev/llm/prompt_builder.py",
            "lab_v4_dev/awareness/project_index.py",
            "lab_v4_dev/awareness/project_knowledge.py",
        ),
    ),
    (
        "LLM Router يقدم تصنيفًا إلى intents محلية أو intents تحتاج مزودًا؛ أما "
        "LLM Gateway فهو حد طلب/استجابة المزوّد. هذا لا يعني أن كل رسالة حوارية "
        "تمر حتمًا عبر LLM Router أو أن اسم/نوع المزوّد ثابت.",
        (
            "lab_v4_dev/llm/router.py",
            "lab_v4_dev/llm/gateway.py",
            "lab_v4_dev/config/provider_config.py",
        ),
    ),
    (
        "Orchestrator هو مالك dispatch التنفيذي في المسار canonical. بعض routes "
        "محلية، وبعضها يستخدم مزودًا، وبعضها ينشئ PreparedExecutionRequest "
        "للتنفيذ؛ وجود route في الشفرة لا يثبت وحده أنه متاح أو ناجح على كل جهاز.",
        (
            "lab_v4_dev/core/orchestrator.py",
            "lab_v4_dev/core/contracts.py",
            "lab_v4_dev/loop/event_loop.py",
            "lab_v4_dev/llm/router.py",
        ),
    ),
    (
        "PreparedExecutionRequest يحمل intent وtarget وcontext وmetadata محلولة، "
        "ولا يحمل raw conversation text أو خطوات التخطيط؛ لذلك يفصل handoff "
        "التنفيذي عن إعادة تحليل نص المستخدم.",
        ("lab_v4_dev/core/contracts.py", "lab_v4_dev/core/orchestrator.py"),
    ),
    (
        "EventLoop.submit_prepared يقبل PreparedExecutionRequest فقط ولا يستدعي "
        "parser أو clarifier أو decomposer القديم. في هذا المسار يفحص الصحة "
        "والميزانية، ثم يبني Planner خطة declarative، ويحّول PlanExecutionAdapter "
        "خطواتها إلى طلبات، وينفذها Executor. لكن EventLoop يحتفظ أيضًا بواجهة "
        "submit الخام ومسار _process التاريخي، فلا يصح وصف prepared بأنه المسار "
        "الوحيد لكل استدعاء EventLoop.",
        (
            "lab_v4_dev/loop/event_loop.py",
            "lab_v4_dev/core/contracts.py",
            "lab_v4_dev/planner/planner.py",
            "lab_v4_dev/executor/plan_adapter.py",
            "lab_v4_dev/executor/executor.py",
        ),
    ),
    (
        "حقائق هذا الملخص منتقاة ومربوطة بمصادر الشفرة الموجودة في checkout؛ "
        "ليست فحصًا حيًا لكل نظام التشغيل أو الملفات أو العمليات أو اسم النموذج "
        "الخارجي. إذا لم يثبت المصدر معلومة عن البيئة أو الإمكانات، فلا تُخمنها.",
        (
            "lab_v4_dev/awareness/agent_self_knowledge.py",
            "lab_v4_dev/llm/gateway.py",
            "lab_v4_dev/config/provider_config.py",
        ),
    ),
)


def build_agent_self_knowledge(intent: str) -> str:
    """Return only reviewed, source-backed project facts for self questions."""
    value = getattr(intent, "value", intent)
    value = str(value or "").casefold()
    if value not in _AGENT_SELF_INTENTS:
        return ""

    lines = []
    for statement, sources in _FACTS:
        existing = [
            source for source in sources
            if (_REPO_ROOT / source).is_file()
        ]
        if existing:
            lines.append(
                f"- {statement}\n  مصادر الشفرة: {', '.join(existing)}"
            )

    return "\n".join(lines)


__all__ = ["build_agent_self_knowledge"]
