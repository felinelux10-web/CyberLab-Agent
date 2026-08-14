# CyberLab Agent v5.9.8.E
# tests/test_project_knowledge.py

import sys, os
sys.path.insert(0, os.path.expanduser("~/cyberlab_agent"))

from lab_v4_dev.awareness.project_knowledge import (
    get_version, get_current_version, get_roadmap, get_session_state,
    get_project_history, get_version_history, get_project_state,
    get_current_focus, get_active, get_planned, get_blocked,
    get_completed, get_open_issues, get_last_project, get_last_goal,
    get_last_step, get_last_files, get_latest_release,
    get_release, search_versions, project_summary, summary
)

passed = 0
failed = 0

def check(name, result, expect_type=None, expect_not_empty=False, expect_contains=None):
    global passed, failed
    ok = True
    if expect_type and not isinstance(result, expect_type):
        print(f"  ❌ {name} — نوع خاطئ: {type(result)}")
        ok = False
    if expect_not_empty and not result:
        print(f"  ❌ {name} — فارغ")
        ok = False
    if expect_contains and expect_contains not in str(result):
        print(f"  ❌ {name} — لا يحتوي: {expect_contains}")
        ok = False
    if ok:
        print(f"  ✅ {name}")
        passed += 1
    else:
        failed += 1

print("=== اختبار project_knowledge ===")
print()

print("--- إصدار ---")
check("get_version()", get_version(), str, True)
check("get_current_version()", get_current_version(), str, True)
check("version ليس ?", get_version(), expect_contains="5.9")

print()
print("--- Roadmap ---")
check("get_roadmap()", get_roadmap(), dict, True)
check("get_current_focus()", get_current_focus(), str, True)
check("get_active()", get_active(), list)
check("get_planned()", get_planned(), list)
check("get_blocked()", get_blocked(), list)
check("get_completed()", get_completed(), list, True)
check("get_open_issues()", get_open_issues(), list)

print()
print("--- Session ---")
check("get_session_state()", get_session_state(), dict)
check("get_last_goal()", get_last_goal(), str)
check("get_last_step()", get_last_step(), str)
check("get_last_files()", get_last_files(), list)

print()
print("--- Project History ---")
check("get_project_history()", get_project_history(), dict)
check("get_last_project()", get_last_project(), str, True)

print()
print("--- Version History ---")
check("get_version_history()", get_version_history(), dict)
check("get_latest_release()", get_latest_release(), str, True)
check("get_release(v5.9.8)", get_release("v5.9.8"), dict)
check("search_versions(5.9.8)", search_versions("5.9.8"), list)

print()
print("--- Project State ---")
state = get_project_state()
check("get_project_state()", state, dict, True)
check("state.version", state.get("version"), str, True)
check("state.completed_count > 0", state.get("completed_count", 0) > 0)

print()
print("--- Summary ---")
s = summary()
check("summary()", s, str, True)
check("project_summary()", project_summary(), str, True)

print()
print("--- التعامل مع الملفات المفقودة ---")
from lab_v4_dev.awareness.project_knowledge import _load
check("_load(missing.json)", _load("missing_file.json"), dict)


print()
print("--- Cache Layer ---")
from lab_v4_dev.awareness.project_knowledge import refresh_cache, reload_file, cache_status
cs = cache_status()
check("cache_status() loaded", cs.get("loaded"), bool)
check("cache_status() files", len(cs.get("files", [])) > 0)
refresh_cache()
cs2 = cache_status()
check("refresh_cache() — لا يزال loaded", cs2.get("loaded"), bool)
check("refresh_cache() — نفس الملفات", sorted(cs2.get("files",[])) == sorted(cs.get("files",[])), bool)
reload_file("roadmap.json")
check("reload_file(roadmap.json) — يعمل", get_roadmap().get("current_focus"), str)

print()
print(f"النتيجة: {passed}/{passed+failed} | ", end="")
print("✅ PASSED" if failed == 0 else f"❌ FAILED ({failed} فشل)")
