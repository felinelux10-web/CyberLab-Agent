#!/usr/bin/env python3
# CyberLab Agent v4.6
# run.py

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lab_v4_dev.core.agent import Agent
from lab_v4_dev.core.logger import log
from lab_v4_dev.core.guard import guard, execute
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.cli.commands import is_special, handle_special

def display(result: dict):
    status = result.get("status","")
    source = result.get("source","local")
    warning = result.get("warning","")

    if result.get("intent") in ["generate_code", "modify_code"]:
        if result.get("status") in ["failed","needs_target"]:
            print(f"❌ {result.get("text","فشل التعديل")}")
            return
        print(f"✅ تم كتابة الكود وحفظه في: {result.get('saved_to','')}")
        print(f"\n{result.get('code','')[:500]}")
        if result.get("save_prompt"):
            print("\n" + result.get("save_prompt"))

    if result.get("text"):
        print(f"\n--- الشرح ---")
        print(result["text"][:300])
        if result.get("save_prompt"):
            print("\n" + result.get("save_prompt"))
            return
        return

    if result.get("intent") == "analyze_code":
        print(f"--- تحليل الكود [{result.get('language','')}] ---")
        print(result.get("text","")[:500])
        return

    if result.get("intent") == "list_scripts":
        print(result.get("text",""))
        return

    if result.get("intent") == "task_chain":
        print(f"=== {result['steps']} خطوات ===")
        for r in result.get("results", []):
            print(f"\n[{r['step']}] {r['cmd'][:50]}")
            if r.get("text"):
                print(r["text"][:200])
        return

    if result.get("intent") == "context_report":
        print("=" * 40)
        print(f"الإصدار  : {result.get('version','?')}")
        print(f"التركيز  : {result.get('focus','?')}")
        print(f"الإصدارات: {', '.join(result.get('releases',[]))}")
        phases = result.get("phases", [])
        print(f"المراحل  : {len(phases)} مكتملة")
        if phases:
            print(f"  آخرها : {phases[-1]}")
        tasks = result.get("tasks", [])
        if tasks:
            print("آخر المهام:")
            for t in tasks[:5]:
                print(f"  [{t['status']}] {t['intent'][:50]}")
        print("=" * 40)
        return

    if status == "unclear":
        print(result.get("message","؟ لم أفهم"))
        return

    if result.get("text"):
        prefix = "[Groq]" if "groq" in source else "[Local]"
        print(f"{prefix} {result['text']}")
        return

    if result.get("output"):
        print(result["output"][:500])
        return

    if result.get("total_files"):
        print(f"المشروع: {result['total_files']} ملف")
        for f in result.get("critical",[])[:3]:
            print(f"  - {f}")
        return

    if result.get("free"):
        print(f"المساحة: {result['free']} متاح من {result.get('total','?')}")
        return

    if result.get("mode"):
        print(f"الحالة: {result['mode']} | مهام: {result.get('tasks',0)}")
        return

    if result.get("tasks"):
        print("آخر المهام:")
        for t in result["tasks"][:5]:
            print(f"  [{t['status']}] {t['intent'][:40]}")
        return

    if result.get("intent") == "clean_device":
        print(result.get("text", "تم التنظيف"))
        return
    if "removed" in result:
        print(f"تم حذف {result['removed']} ملف مؤقت")
        return

    if result.get("health"):
        h = result["health"]
        print(f"الصحة: {'جيد' if h.get('healthy') else 'تحذير'} | RAM: {h.get('ram_mb')}MB")
        return

    if result.get("session"):
        s = result["session"]
        print(f"الجلسة: مهام={s['tasks_done']} أخطاء={s['error_count']}")
        return

    if status == "fallback":
        print("لا يوجد اتصال — أعمل محلياً")
        return

    intent = result.get("intent","?")
    print(f"❓ لم أفهم الأمر (intent={intent} status={status})")

def main():
    with open("lab_v4_dev/cache/state.json","w") as f:
        json.dump({"mode":"normal","consecutive_failures":0,
                   "session_start":"","last_error":None,"saved_at":""}, f)

    agent = Agent()
    if not agent.boot():
        sys.exit(1)

    print()
    print("CyberLab Agent v5.0 — جاهز")
    print("اكتب 'مساعدة' أو 'exit'")
    print("-" * 40)

    try:
        while True:
            try:
                user_input = input(">>> ").strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ["exit","quit","خروج"]:
                break
            if is_special(user_input):
                print(handle_special(user_input, agent))
                continue

            result = agent.run(user_input)
            display(result)
            if result.get("warning"):
                print(result["warning"])

    except KeyboardInterrupt:
        print()
    finally:
        agent.shutdown()
        print("وداعاً.")

if __name__ == "__main__":
    main()
