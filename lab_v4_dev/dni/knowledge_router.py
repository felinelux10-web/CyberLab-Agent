# CyberLab Agent — DNI-6
# dni/knowledge_router.py — Knowledge Router
# طبقة وصول موحدة فوق مصادر المعرفة الحالية. إضافية فقط، لا تحذف أو تعدل أي مصدر.

# ─── Cyber Explain Knowledge Base ───

def search_cyber_kb(topic: str):
    from lab_v4_dev.awareness.knowledge_base import search
    return search(topic)

def store_cyber_kb(topic: str, answer: str):
    from lab_v4_dev.awareness.knowledge_base import store
    return store(topic, answer)

# ─── Change Planning / Impact Analysis ───

def create_change_plan(target_file: str):
    from lab_v4_dev.project_knowledge.change_planner import ChangePlanner
    return ChangePlanner().create_plan(target_file)

def analyze_general_impact(file_path: str) -> dict:
    from lab_v4_dev.planner.impact_analyzer import analyze_impact
    return analyze_impact(file_path)

# ─── Project Structure / Dependency Knowledge ───

def get_entry_points():
    from lab_v4_dev.awareness.dependency_engine import get_entry_points as _f
    return _f()

def get_critical_files():
    from lab_v4_dev.awareness.dependency_engine import get_critical_files as _f
    return _f()

def query_file_risk(file_path: str) -> dict:
    """استعلام موحد: اعتماديات + تأثير + خطورة (risk_level مُضمَّن داخلياً)"""
    from lab_v4_dev.awareness.query_engine import query_file
    return query_file(file_path)

# ─── P10 Declarative Planner ───

def create_p10_plan(
    intent: dict,
    actions: list[dict] | tuple[dict, ...],
    *,
    plan_id: str = "",
    metadata: dict | None = None,
):
    """Create a declarative P10 Plan without executing anything."""
    from lab_v4_dev.planner.planner import Planner

    return Planner().from_actions(
        intent,
        actions,
        plan_id=plan_id,
        metadata=metadata,
    )



def create_p10_plan_from_change(
    target_file: str,
    *,
    plan_id: str = "",
    metadata: dict | None = None,
):
    """Create the canonical declarative P10 Plan for a file change.

    Legacy ChangePlanner data is used when impact-aware execution steps exist.
    Otherwise, the factory creates the minimal declarative P10 plan directly.
    No execution is performed here.
    """
    from lab_v4_dev.project_knowledge.change_planner import ChangePlanner
    from lab_v4_dev.planner.legacy_adapter import LegacyExecutionPlanAdapter
    from lab_v4_dev.planner.planner import Planner

    legacy = ChangePlanner().create_plan(target_file)
    execution_plan = legacy.get("execution_plan", [])

    if execution_plan:
        return LegacyExecutionPlanAdapter().convert(
            {
                "action": "change_file",
                "target": target_file,
            },
            execution_plan,
            plan_id=plan_id,
            metadata=metadata,
        )

    return Planner().from_actions(
        {
            "action": "change_file",
            "target": target_file,
        },
        [
            {
                "step_id": "step-1",
                "action": "change_file",
                "parameters": {
                    "file": target_file,
                },
                "description": f"Plan change for {target_file}",
            }
        ],
        plan_id=plan_id,
        metadata=metadata,
    )
