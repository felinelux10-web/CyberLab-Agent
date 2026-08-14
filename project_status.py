#!/usr/bin/env python3
import os, subprocess

root = os.path.expanduser("~/cyberlab_agent")
print("=" * 50)
print("PROJECT STATUS REPORT")
print("=" * 50)

# 1. run.py entry point
print("\n[1] run.py - أول 5 أسطر:")
with open(f"{root}/run.py") as f:
    for l in f.readlines()[:5]:
        print("  ", l.rstrip())

# 2. ملفات مكررة الاسم (orchestrator, agent, etc)
print("\n[2] ملفات orchestrator/agent الموجودة:")
for dirpath, dirs, files in os.walk(root):
    if "stable" in dirpath or "__pycache__" in dirpath or ".git" in dirpath:
        continue
    for f in files:
        if f in ("orchestrator.py", "agent.py", "system_orchestrator.py"):
            full = os.path.join(dirpath, f)
            mtime = os.path.getmtime(full)
            print(f"   {full}  (mtime={int(mtime)})")

# 3. آخر تعديل على الملفات الأساسية
print("\n[3] آخر تعديل (lab_v4_dev/core, awareness):")
for sub in ["lab_v4_dev/core", "lab_v4_dev/awareness", "lab_v4_dev/intent"]:
    p = os.path.join(root, sub)
    if os.path.exists(p):
        files = sorted(
            [(f, os.path.getmtime(os.path.join(p,f))) for f in os.listdir(p) if f.endswith(".py")],
            key=lambda x: -x[1]
        )[:3]
        print(f"  {sub}:")
        for f, m in files:
            print(f"     {f}")

# 4. آخر release
print("\n[4] آخر إصدارات في releases/:")
rel = os.path.join(root, "releases")
if os.path.exists(rel):
    dirs = sorted(os.listdir(rel))
    print("  ", dirs[-5:])

# 5. ملفات يتيمة محتملة (في core/ الجذر مباشرة)
print("\n[5] ملفات في core/ بالجذر (قد تكون يتيمة):")
core_root = os.path.join(root, "core")
if os.path.exists(core_root):
    for f in os.listdir(core_root):
        print(f"   {f}")

print("\n" + "=" * 50)
