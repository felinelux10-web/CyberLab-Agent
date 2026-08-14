# CyberLab Agent — DNI-5
# memory/router.py — Memory Router
# طبقة قراءة موحدة فوق مصادر الذاكرة الحالية. إضافية فقط، لا تحذف أو تعدل أي مصدر.

# ─── Section 1: Roadmap / Session / Project History ───
# يغلف awareness.project_knowledge (Single Source of Truth الموثق أصلاً)

def get_roadmap() -> dict:
    from lab_v4_dev.awareness.project_knowledge import get_roadmap as _f
    return _f()

def get_session_state() -> dict:
    from lab_v4_dev.awareness.project_knowledge import get_session_state as _f
    return _f()

def get_project_history() -> dict:
    from lab_v4_dev.awareness.project_knowledge import get_project_history as _f
    return _f()

def get_current_version() -> str:
    from lab_v4_dev.awareness.project_knowledge import get_current_version as _f
    return _f()

def save_roadmap(data: dict):
    from lab_v4_dev.awareness.project_knowledge import save_roadmap as _f
    return _f(data)

def save_session(data: dict):
    from lab_v4_dev.awareness.project_knowledge import save_session as _f
    return _f(data)

# ─── Section 2: SQLite (Session / Lessons / TaskHistory) ───
# يتطلب تمرير db (كائن Database) صراحة — لا يُدار داخلياً هنا

def get_lesson(db, error_pattern: str) -> dict | None:
    from lab_v4_dev.memory.lessons import Lessons
    return Lessons(db).find(error_pattern)

def record_lesson(db, error_pattern: str, solution: str, success: bool):
    from lab_v4_dev.memory.lessons import Lessons
    return Lessons(db).record(error_pattern, solution, success)

def recent_tasks(db, limit: int = 10) -> list:
    from lab_v4_dev.memory.task_history import TaskHistory
    return TaskHistory(db).recent(limit)

def add_task_history(db, intent: str, plan: str = None) -> int:
    from lab_v4_dev.memory.task_history import TaskHistory
    return TaskHistory(db).add(intent, plan)

# ─── Section 3: Conversation Context (context/context_store.py) ───
# يتطلب تمرير context (كائن ContextStore الخاص بالمحادثة) صراحة

def get_current_subject(context) -> str | None:
    return getattr(context, "current_subject", None)

def get_current_file(context) -> str | None:
    return getattr(context, "current_file", None)

def get_current_version_from_context(context) -> str | None:
    return getattr(context, "current_version", None)

def get_conversation_summary(context) -> dict:
    return context.get_last() if hasattr(context, "get_last") else {}

# ─── Section 4: Project Structure / Dependencies (awareness/project_memory.py) ───

def get_project_memory() -> dict:
    from lab_v4_dev.awareness.project_memory import load_memory
    return load_memory()

def get_file_dependency_info(file_path: str) -> dict:
    from lab_v4_dev.awareness.project_memory import get_file_info
    return get_file_info(file_path)

# ─── Section 5: Runtime / Session State (awareness/state_reader.py) ───

def get_runtime_state() -> dict:
    from lab_v4_dev.awareness import state_reader
    return state_reader.load()

def get_runtime_state_summary() -> str:
    from lab_v4_dev.awareness import state_reader
    return state_reader.summary()

# ─── Section 6: NLU Entity Context (nlu/context_resolver.py) ───
# نظام منفصل تماماً عن Section 3 (context/context_store.py) — أغراض مختلفة، لا يُدمجان

def get_last_nlu_entity() -> dict:
    from lab_v4_dev.nlu.context_resolver import get_last_entity
    return get_last_entity()

def resolve_nlu_context(nlu_result: dict) -> dict:
    from lab_v4_dev.nlu.context_resolver import resolve
    return resolve(nlu_result)
