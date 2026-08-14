# CyberLab Agent v4.4
# lab_v4/cli/commands.py

import os
import shutil
import json
from datetime import datetime

SHORTCUTS = {
    "health"  : "شغّل echo checking...",
    "log"     : "اقرأ lab_v4/logs/agent.log",
    "errors"  : "اقرأ lab_v4/logs/errors.log",
    "status"  : "status",
    "ls"      : "شغّل ls lab_v4",
    "help"    : "help",
    "space"   : "space",
    "clean"   : "clean",
    "report"  : "report",
    "history" : "history",
    "todos"   : "todos",
    "schedule": "schedule",
}

NOTES_FILE    = "lab_v4/cache/notes.json"
TODOS_FILE    = "lab_v4/cache/todos.json"
SCHEDULE_FILE = "lab_v4/cache/schedule.json"

def load_json(path):
    try:
        return json.load(open(path))
    except:
        return []

def save_json(path, data):
    json.dump(data, open(path, "w"), ensure_ascii=False, indent=2)

def resolve(user_input):
    cmd = user_input.strip().lower()
    for prefix in ["draft ", "note ", "todo ", "search ", "at "]:
        if cmd.startswith(prefix):
            return user_input
    return SHORTCUTS.get(cmd, user_input)

def is_special(cmd):
    c = cmd.strip().lower()
    specials = ["status","help","space","clean","report","history","todos","schedule"]
    if c in specials:
        return True
    for prefix in ["draft ","note ","todo ","search ","at "]:
        if c.startswith(prefix):
            return True
    return False

def handle_special(cmd, agent):
    c = cmd.strip().lower()

    if c == "status":
        s = agent.state
        h = agent.session.summary()
        return f"mode:{s.mode} tasks:{h['tasks_done']} files:{h['files_modified']} errors:{h['error_count']}"

    if c == "space":
        home = os.path.expanduser("~")
        total, used, free = shutil.disk_usage(home)
        return f"total:{total//(1024**3)}GB used:{used//(1024**2)}MB free:{free//(1024**2)}MB"

    if c == "clean":
        removed = 0
        for root, dirs, files in os.walk(os.path.expanduser("~/cyberlab_agent")):
            for f in files:
                if f.endswith(".pyc") or f.endswith(".tmp"):
                    try:
                        os.remove(os.path.join(root, f))
                        removed += 1
                    except:
                        pass
        return f"cleaned: {removed} files removed"

    if c == "report":
        h = agent.session.summary()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        report = f"Session Report\ntime:{now}\ntasks:{h['tasks_done']}\nfiles:{h['files_modified']}\nerrors:{h['error_count']}\nstate:{agent.state.mode}"
        path = f"lab_v4/cache/report_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        try:
            open(path, "w").write(report)
            report += f"\nsaved:{path}"
        except:
            pass
        return report

    if c == "history":
        from lab_v4.memory.task_history import TaskHistory
        th = TaskHistory(agent.db)
        tasks = th.recent(10)
        if not tasks:
            return "no tasks yet"
        lines = ["Last 10 Tasks:"]
        for t in tasks:
            lines.append(f"[{t['status']}] {t['intent'][:50]}")
        return "\n".join(lines)

    if c.startswith("note "):
        text = cmd[5:].strip()
        notes = load_json(NOTES_FILE)
        notes.append({"text": text, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
        save_json(NOTES_FILE, notes)
        return f"note saved ({len(notes)} total)"

    if c.startswith("todo "):
        task = cmd[5:].strip()
        todos = load_json(TODOS_FILE)
        todos.append({"task": task, "done": False, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
        save_json(TODOS_FILE, todos)
        return f"todo added ({len(todos)} total)"

    if c == "todos":
        todos = load_json(TODOS_FILE)
        if not todos:
            return "no todos yet"
        lines = ["=== Todos ==="]
        for i, t in enumerate(todos):
            status = "✓" if t["done"] else "○"
            lines.append(f"{i+1}. {status} {t['task']}")
        return "\n".join(lines)

    if c.startswith("at "):
        parts = cmd[3:].strip().split(" ", 1)
        if len(parts) < 2:
            return "usage: at [HH:MM] [task]"
        time_str = parts[0]
        task = parts[1]
        schedule = load_json(SCHEDULE_FILE)
        schedule.append({
            "time": time_str,
            "task": task,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "done": False
        })
        save_json(SCHEDULE_FILE, schedule)
        return f"scheduled: {task} at {time_str}"

    if c == "schedule":
        schedule = load_json(SCHEDULE_FILE)
        if not schedule:
            return "no scheduled tasks"
        lines = ["=== Schedule ==="]
        for s in schedule:
            status = "✓" if s["done"] else "○"
            lines.append(f"{status} {s['time']} — {s['task']}")
        return "\n".join(lines)

    if c.startswith("search "):
        keyword = cmd[7:].strip()
        results = []
        for root, dirs, files in os.walk("lab_v4"):
            dirs[:] = [d for d in dirs if d not in ["__pycache__","archives","cache"]]
            for f in files:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(root, f)
                try:
                    content = open(path).read()
                    if keyword.lower() in content.lower():
                        results.append(path)
                except:
                    pass
        if not results:
            return f"not found: {keyword}"
        return "found in:\n" + "\n".join(results[:10])

    if c.startswith("draft "):
        topic = cmd[6:].strip()
        now = datetime.now().strftime("%Y-%m-%d")
        draft = f"Draft: {topic}\nDate: {now}\n\n[Introduction]\nWrite about {topic} here.\n\n[Points]\n- Point 1\n- Point 2\n\n[Conclusion]\nWrite conclusion here."
        path = f"lab_v4/cache/draft_{topic[:20].replace(chr(32),chr(95))}.txt"
        try:
            open(path, "w").write(draft)
            draft += f"\nsaved:{path}"
        except:
            pass
        return draft

    if c == "help":
        return """=== Commands ===
شغّل [cmd]      : run shell command
اقرأ [path]    : read file
اكتب [path]    : write file
health         : system health
log / errors   : logs
status         : agent status
ls             : list lab_v4
space          : storage info
clean          : remove temp files
report         : session report
history        : last 10 tasks
note [text]    : save a note
todo [task]    : add todo
todos          : show todos
at [HH:MM] [task]: schedule task
schedule       : show schedule
search [word]  : search in files
draft [topic]  : create draft
exit           : shutdown"""

    return ""
