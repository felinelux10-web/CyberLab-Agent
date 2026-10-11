from lab_v4_dev.conversation.conversation_manager import ConversationManager
from lab_v4_dev.conversation.mode_detector import detect_mode
from lab_v4_dev.conversation.semantic_contract import ContextTransition
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.llm.prompt_builder import _chat_domain
from lab_v4_dev.awareness.knowledge_retriever import ProjectScope


def test_lexical_mentions_do_not_become_project_or_work_requests():
    examples = [
        "لماذا تظهر كلمة المشروع في الرد؟",
        "لماذا تعرض كلمة العمل سياق العمل؟",
        "أريد فهم معنى كلمة شغل في هذه الجملة",
        "هل مصطلح الاشتغال هنا يعني سياق العمل؟",
        "لماذا تظهر كلمة مساحة في هذا المثال؟",
    ]
    for text in examples:
        result = parse(text)
        assert result["intent"] == Intent.PERSONAL_CHAT, (text, result)
        assert result.get("semantic_pattern") == "INTENT_WORD_MENTION"


def test_lexical_mentions_do_not_trigger_phone_storage_or_device_cleanup():
    examples = [
        "لماذا تظهر مساحة الهاتف في الرد؟",
        "ما معنى كلمة تنظيف في هذا النص؟",
        "اشرح معنى حذف الملف في هذه الجملة",
        "لماذا يظهر الهاتف في هذا المثال؟",
    ]
    for text in examples:
        result = parse(text)
        assert result["intent"] == Intent.PERSONAL_CHAT, (text, result)
        assert result["intent"] not in {
            Intent.SPACE, Intent.CLEAN_DEVICE, Intent.DELETE_FILE,
        }


def test_incidental_cleanup_and_delete_nouns_do_not_authorize_actions():
    cleanup = parse("هذا المشروع يحتاج تنظيف")
    assert cleanup["intent"] not in {
        Intent.CLEAN, Intent.CLEAN_DEVICE, Intent.CLEANUP_CODE,
    }

    deletion = parse("هل حذف الملف خطير؟")
    assert deletion["intent"] != Intent.DELETE_FILE


def test_explicit_operational_requests_keep_their_routes():
    assert parse("مساحة الهاتف")["intent"] == Intent.SPACE
    assert parse("كم مساحة التخزين؟")["intent"] == Intent.SPACE
    assert parse("حلل المشروع")["intent"] == Intent.PROJECT_SCAN
    assert parse("ما هو المشروع الحالي")["intent"] == Intent.SWITCH_PROJECT
    assert parse("ما هي المشاريع التي اشتغلت عليها فعليا")["intent"] == Intent.PROJECT_INDEX
    assert parse("نظف الهاتف")["intent"] == Intent.CLEAN_DEVICE
    assert parse("احذف الملف test.py")["intent"] == Intent.DELETE_FILE


def test_project_and_work_words_alone_do_not_force_project_prompt_domain():
    assert _chat_domain("لماذا تظهر كلمة المشروع في الرد؟") == "general"
    assert _chat_domain("أريد فهم معنى كلمة العمل") == "general"
    assert _chat_domain("ما رأيك في المشروع؟") == "general"
    assert parse("ما رأيك في بنية المشروع؟")["intent"] != Intent.PROJECT_SCAN
    assert parse("ما هي بنية المشروع؟")["intent"] == Intent.PROJECT_SCAN
    assert _chat_domain(
        "ما طبقات CyberLab Agent؟",
        ProjectScope.CURRENT_PROJECT,
    ) == "project"


def test_incidental_action_word_does_not_force_task_mode():
    assert detect_mode("لماذا تظهر كلمة شغل في الجملة؟") == "QUESTION"
    assert detect_mode("ما معنى كلمة حذف؟") == "QUESTION"
    assert detect_mode("لماذا تظهر مشكلة في الكود؟") == "QUESTION"
    assert detect_mode("هذا الوكيل شغل النظام أمس") != "TASK"
    assert detect_mode("اكتب سكريبت يطبع مرحبا") == "TASK"


def test_work_word_mention_is_not_recorded_as_work_context():
    manager = ConversationManager(orchestrator=None)
    parsed = {
        "intent": Intent.CYBER_EXPLAIN,
        "target": "",
        "conversation_act": "NONE",
    }
    context_kind = manager._context_kind(
        "اشرح معنى كلمة العمل في هذه الجملة",
        parsed,
        ContextTransition.AMBIGUOUS,
    )
    assert context_kind == "unknown"


def test_project_plus_work_verb_requires_a_real_progress_question():
    result = parse("ماذا كنا نشتغل على هذا المشروع؟")
    assert result["intent"] == Intent.WORK_CONTEXT

    opinion = parse("ما رأيك في مشروع كنا نعمل عليه؟")
    assert opinion["intent"] != Intent.WORK_CONTEXT
    assert opinion["intent"] != Intent.PROJECT_INDEX


def test_status_report_storage_and_edit_nouns_do_not_route_from_opinion_questions():
    status = parse("ما رأيك في حالة النظام؟")
    report = parse("ما رأيك في التقرير؟")
    storage = parse("ما رأيك في مساحة الهاتف؟")
    edit = parse("ما رأيك في تحرير الملف؟")
    assert status["intent"] not in {Intent.STATUS, Intent.SYSTEM_STATUS}
    assert report["intent"] != Intent.REPORT
    assert storage["intent"] != Intent.SPACE
    assert edit["intent"] not in {Intent.MODIFY_CODE, Intent.MODIFY_FILE}
