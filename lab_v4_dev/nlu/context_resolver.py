# CyberLab Agent — NLU Layer
# nlu/context_resolver.py
# يستكمل العناصر الناقصة من السياق السابق

import json
import os
import time

BASE = os.path.dirname(__file__)
CONTEXT_FILE = os.path.join(BASE, "nlu_context.json")
MAX_HISTORY = 5
CONTEXT_TTL = 300  # 5 دقائق

def _load() -> list:
    try:
        with open(CONTEXT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def _save(history: list):
    with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def save_state(action: str, entity: str, entity_type: str = ""):
    """يحفظ آخر NLU State — المعنى وليس النص"""
    history = _load()
    state = {
        "action"     : action,
        "entity"     : entity,
        "entity_type": entity_type,
        "timestamp"  : time.time(),
    }
    history.insert(0, state)
    history = history[:MAX_HISTORY]
    _save(history)

def get_last_entity() -> dict:
    """يعيد آخر كيان صالح ضمن نافذة الوقت"""
    history = _load()
    now = time.time()
    for state in history:
        age = now - state.get("timestamp", 0)
        if age <= CONTEXT_TTL and state.get("entity"):
            return state
    return {}

def is_incomplete(nlu_result: dict) -> bool:
    """
    هل الجملة ناقصة؟
    الجملة ناقصة إذا:
    - يوجد intent/action
    - لكن لا يوجد entity/target
    - والـ intent يحتاج entity
    """
    intent = nlu_result.get("intent", "")
    target = nlu_result.get("target", "")
    entity = nlu_result.get("entity", {})
    entity_value = entity.get("value", "") if isinstance(entity, dict) else ""

    # intents تحتاج entity
    needs_entity = {
        "cyber_explain", "analyze_code", "file_impact",
        "dependencies", "read_file", "delete_file", "criticality_query",
        "dependents_query", "impact_chain_query"
    }

    if intent in needs_entity and not target and not entity_value:
        return True
    return False

def resolve(nlu_result: dict) -> dict:
    """
    يستكمل العناصر الناقصة من السياق السابق.
    لا يغير intent، فقط يضيف entity/target إذا كانا فارغين
    وكان نوع الكيان السابق متوافقاً مع الـ intent الحالي.
    """
    if not is_incomplete(nlu_result):
        return nlu_result

    last = get_last_entity()
    if not last:
        return nlu_result

    inherited_entity = last.get("entity", "")
    inherited_type = last.get("entity_type", "")
    previous_action = last.get("action", "")

    if inherited_entity:
        compatible = True
        intent = nlu_result.get("intent", "")

        if intent in {
            "read_file",
            "analyze_code",
            "file_impact",
            "dependencies",
            "dependents_query",
            "impact_chain_query",
            "delete_file",
        }:
            compatible = inherited_type in {"FILE", "COMPONENT"}

        elif intent == "cyber_explain":
            compatible = inherited_type in {"CONCEPT", "FILE", "COMPONENT"}

        elif intent == "current_version":
            compatible = inherited_type == "VERSION"

        if compatible:
            nlu_result = nlu_result.copy()
            nlu_result["target"] = inherited_entity
            nlu_result["context_inherited"] = True
            nlu_result["inherited_from"] = previous_action

    return nlu_result
