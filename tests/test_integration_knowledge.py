# CyberLab Agent v5.9.8.F
# tests/test_integration_knowledge.py
# اختبار تكاملي: هل جميع الدوال ترجع نفس البيانات عند تغيير project_data؟

import sys, os, json
sys.path.insert(0, os.path.expanduser("~/cyberlab_agent"))

DATA = os.path.expanduser("~/cyberlab_agent/project_data")
ROADMAP = os.path.join(DATA, "roadmap.json")

passed = 0
failed = 0

def check(name, a, b):
    global passed, failed
    if a == b:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}")
        print(f"     project_knowledge: {repr(a)}")
        print(f"     مصدر آخر:         {repr(b)}")
        failed += 1

# حفظ القيمة الأصلية
with open(ROADMAP, encoding="utf-8") as f:
    original = json.load(f)

# تعديل مؤقت
test_focus = "INTEGRATION_TEST_FOCUS"
original_focus = original.get("current_focus", "?")
original["current_focus"] = test_focus
with open(ROADMAP, "w", encoding="utf-8") as f:
    json.dump(original, f, ensure_ascii=False, indent=2)

print("=== اختبار التكامل ===")
print(f"تعديل current_focus مؤقتاً إلى: {test_focus}")
print()

try:
    # اختبار 1: project_knowledge
    from lab_v4_dev.awareness.project_knowledge import get_current_focus, get_roadmap
    pk_focus = get_current_focus()
    pk_roadmap = get_roadmap().get("current_focus")

    # اختبار 2: work_tracker
    from lab_v4_dev.data.work_tracker import load_roadmap
    wt_focus = load_roadmap().get("current_focus")

    # اختبار 3: prompt_builder
    from lab_v4_dev.llm.prompt_builder import _load_roadmap
    pb_focus = _load_roadmap().get("current_focus")

    print("--- مقارنة current_focus ---")
    check("project_knowledge.get_current_focus() == test_focus", pk_focus, test_focus)
    check("project_knowledge.get_roadmap() == test_focus", pk_roadmap, test_focus)
    check("work_tracker.load_roadmap() == project_knowledge", wt_focus, pk_focus)
    check("prompt_builder._load_roadmap() == project_knowledge", pb_focus, pk_focus)

    print()
    print("--- مقارنة session_state ---")
    from lab_v4_dev.awareness.project_knowledge import get_last_goal
    from lab_v4_dev.memory.session_state import load_session

    pk_goal = get_last_goal()
    ss_goal = load_session().get("active_goal", "?")
    check("project_knowledge.get_last_goal() == session_state.load_session()", pk_goal, ss_goal)

finally:
    # استعادة القيمة الأصلية
    original["current_focus"] = original_focus
    with open(ROADMAP, "w", encoding="utf-8") as f:
        json.dump(original, f, ensure_ascii=False, indent=2)
    print()
    print(f"تم استعادة current_focus إلى: {original_focus}")

print()
print(f"النتيجة: {passed}/{passed+failed} | ", end="")
print("✅ PASSED" if failed == 0 else f"❌ FAILED ({failed} فشل)")
