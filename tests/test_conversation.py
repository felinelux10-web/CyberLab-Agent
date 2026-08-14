"""
test_conversation.py — Series 10
اختبارات مستقلة لطبقة الحوار.
"""
import sys, os
sys.path.insert(0, os.path.expanduser("~/cyberlab_agent"))

from lab_v4_dev.conversation.mode_detector import detect_mode
from lab_v4_dev.conversation.assistant_style import clean_response, single_question
from lab_v4_dev.memory.db import Database
from lab_v4_dev.awareness.context_store import ContextStore
from lab_v4_dev.conversation.dialogue_memory import DialogueMemory

def run_tests():
    print("=== Conversation Layer Tests — Series 10 ===")
    passed = 0
    total  = 0

    def check(label, result, expected):
        nonlocal passed, total
        total += 1
        ok = result == expected
        if ok: passed += 1
        print(f"{'✅' if ok else '❌'} {label}")

    # Mode Detection
    check("TASK — افحص agent.py",       detect_mode("افحص agent.py"),        "TASK")
    check("TASK — اكتب كوداً",          detect_mode("اكتب كوداً"),           "TASK")
    check("CHAT — شكراً",               detect_mode("شكراً"),                "CHAT")
    check("CHAT — مرحبا",               detect_mode("مرحبا"),                "CHAT")
    check("QUESTION — ما رأيك؟",        detect_mode("ما رأيك؟"),             "QUESTION")
    check("QUESTION — ماذا تقترح",      detect_mode("ماذا تقترح"),           "QUESTION")
    check("DISCUSSION — دعنا نناقش",    detect_mode("دعنا نناقش"),           "DISCUSSION")
    check("DISCUSSION — ما الأفضل",     detect_mode("ما الأفضل"),            "DISCUSSION")
    check("FOLLOW_UP — هذا",            detect_mode("هذا"),                  "FOLLOW_UP")
    check("FOLLOW_UP — الملف السابق",   detect_mode("الملف السابق"),         "FOLLOW_UP")
    check("SYSTEM — احفظ الجلسة",       detect_mode("احفظ الجلسة"),          "SYSTEM")
    check("SYSTEM — استكمل الجلسة",     detect_mode("استكمل الجلسة"),        "SYSTEM")

    # Assistant Style
    check("clean — بالطبع!",   clean_response("بالطبع! سأفحص"),  "سأفحص")
    check("clean — رائع!",     clean_response("رائع! تم"),        "تم")
    check("clean — ممتاز!",    clean_response("ممتاز! نجح"),      "نجح")
    check("single_question",   single_question("هل X؟ أم Y؟"),   "هل X؟")

    # Dialogue Memory
    db = Database(); db.connect()
    ctx = ContextStore(db)
    ctx.current_file    = "core/agent.py"
    ctx.current_subject = "core/agent.py"
    dm = DialogueMemory(ctx)

    check("resolve — هذا",          "core/agent.py" in dm.resolve_references("هذا"),           True)
    check("resolve — السابق",       "core/agent.py" in dm.resolve_references("افحص السابق"),   True)
    check("resolve — الملف السابق", "core/agent.py" in dm.resolve_references("الملف السابق"),  True)

    # Topic Switching
    dm.save_pending("موضوع Runtime")
    restored = dm.restore_pending()
    check("topic save/restore",  restored, "موضوع Runtime")
    check("topic cleared after restore", dm.restore_pending(), None)

    print(f"\nالنتيجة: {passed}/{total}")
    print("✅ PASSED" if passed == total else "❌ FAILED")
    return passed == total

if __name__ == "__main__":
    run_tests()
