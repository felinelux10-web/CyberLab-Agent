# CyberLab Agent v5.0
# tests/smoke_test.py

import sys
import os
sys.path.insert(0, os.path.expanduser("~/cyberlab_agent"))
os.chdir(os.path.expanduser("~/cyberlab_agent"))

from lab_v4_dev.core.agent import Agent

TESTS = [
    # Series 1 — النواة الأساسية
    ("خريطة المشروع",                                    ["success"], ["text"]),
    ("تقرير السياق",                                     ["success"], ["version"]),
    ("شخص النظام",                                       ["success"], ["text"]),
    ("تاريخ التشغيل",                                    ["success"], ["text"]),
    ("شيء غير مفهوم xyz123",                             ["unsupported"], []),

    # Series 2 — الوعي بالمشروع
    ("ما نقطة الدخول",                                   ["success"], ["text"]),
    ("اعرض كل الملفات المتاثرة",                         ["success"], ["text"]),
    ("اقرأ مشروع ~/external_projects/dynamic-lab-app",   ["success"], ["text"]),
    ("اقرأ ملف ~/external_projects/dynamic-lab-app/client/src/data/labs.ts", ["success"], ["output"]),
    ("هل يوجد ملف cleaner.py",                           ["success"], ["text"]),

    # Series 3 — التعافي والاسترجاع
    ("تقرير المشروع",                                    ["success"], ["text"]),

    # Series 4 — التفكير واتخاذ القرار
    ("ما تاثير orchestrator",                            ["success"], ["text"]),
    ("اعتماديات memory/db.py",                           ["success"], ["text"]),
    ("تاثير شامل memory/db.py",                          ["success"], ["text"]),
    ("خطورة memory/db.py",                               ["success"], ["text"]),

    # Series 5 — دورة التنفيذ
    ("اكتب سكريبت يطبع مرحبا",                          ["success"], ["code", "saved_to"]),
    ("اكتب سكريبت يفحص المنفذ 80 على 127.0.0.1",        ["success"], ["code", "saved_to"]),

    # Series 6-7 — المعرفة والذاكرة
    ("اشرح SQL Injection",                               ["success"], ["text"]),
    ("ما وظيفة orchestrator.py",                         ["success"], ["text"]),
    ("قارن ملف cleaner.py و state.py",                   ["success"], ["text"]),

    # Series 8-9 — Runtime
    ("حالة النظام",                                      ["success"], ["text"]),

    # Test 21 — Dialogue Continuity Recovery
    ("ما دوره في المشروع؟",                              ["success"], ["text"]),
    ("كيف يعمل؟",                                        ["success"], ["text"]),
]

def run_smoke_test():
    print("=== CyberLab Smoke Test v6.0 — Series 1-9 ===")
    agent = Agent()
    agent.boot()
    passed = 0
    failed = 0
    for cmd, expected_statuses, expected_keys in TESTS:
        try:
            # P06 — reset complete conversational lifecycle
            agent.reset_conversation_context()

            # P06 — production path:
            # Agent.run -> ConversationManager -> Orchestrator
            r = agent.run(cmd)
            status    = r.get("status", "?")
            ok_status = status in expected_statuses
            ok_keys   = all(k in r and r[k] for k in expected_keys)
            ok        = ok_status and ok_keys
            icon = "✅" if ok else "❌"
            passed += 1 if ok else 0
            failed += 0 if ok else 1
            # فحص إضافي للكود المولد
            if "saved_to" in r and r.get("saved_to"):
                script = r.get("code","")
                if "os.system" in script or "setcap" in script:
                    ok = False
                    icon = "❌"
                    failed += 1
                    passed -= 1
                    print(f"❌ {cmd[:35]:<35} → كود يحتوي أدوات غير مطلوبة")
                    continue
            print(f"{icon} {cmd[:35]:<35} → {status}")
        except Exception as e:
            failed += 1
            print(f"💥 {cmd[:35]:<35} → {e}")
    print()
    print(f"النتيجة: {passed}/{len(TESTS)} | Coverage: {round(passed/len(TESTS)*100)}%")
    print("✅ PASSED" if failed == 0 else "❌ FAILED")
    return failed == 0

if __name__ == "__main__":
    run_smoke_test()
