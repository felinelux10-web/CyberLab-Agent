# CyberLab Agent v4.7
# monitor/self_diagnostics.py

from lab_v4_dev.llm.provider_names import GROQ
import os
import json
from datetime import datetime
from lab_v4_dev.core.audit import emit_event

DIAG_HISTORY_FILE = "project_data/diag_history.json"

# ─── فحوص مستقلة ───

def check_routing() -> dict:
    try:
        from lab_v4_dev.llm.router import needs_llm, is_local
        from lab_v4_dev.intent.intents import Intent
        assert needs_llm(Intent.PROJECT_SCAN)
        assert is_local(Intent.STATUS)
        return {"status": "OK", "score": 1.0}
    except Exception as e:
        return {"status": "FAIL", "score": 0.0, "error": str(e)}

def check_context() -> dict:
    try:
        from lab_v4_dev.context.context_store import ContextStore
        cs = ContextStore()
        cs.update("test", "v4.7", {"text": "test"})
        assert cs.current_version == "4.7"
        assert cs.current_subject == "version_4.7"
        return {"status": "OK", "score": 1.0}
    except Exception as e:
        return {"status": "FAIL", "score": 0.0, "error": str(e)}

def check_release_analyzer() -> dict:
    try:
        from lab_v4_dev.awareness.release_analyzer import get_available_versions
        versions = get_available_versions()
        if not versions:
            return {"status": "WARN", "score": 0.5,
                    "warning": "لا توجد إصدارات"}
        return {"status": "OK", "score": 1.0,
                "versions": len(versions)}
    except Exception as e:
        return {"status": "FAIL", "score": 0.0, "error": str(e)}

def check_work_tracker() -> dict:
    try:
        from lab_v4_dev.data.work_tracker import load_roadmap
        r = load_roadmap()
        if not r:
            return {"status": "WARN", "score": 0.5,
                    "warning": "roadmap.json فارغ"}
        active = r.get("active", [])
        if not active:
            return {"status": "WARN", "score": 0.8,
                    "warning": "لا توجد مهمة نشطة"}
        return {"status": "OK", "score": 1.0,
                "active": active[0]}
    except Exception as e:
        return {"status": "FAIL", "score": 0.0, "error": str(e)}

def check_groq() -> dict:
    try:
        from lab_v4_dev.llm.gateway import ask
        r = ask("قل OK فقط", max_tokens=10)
        if r.get("status") == "success":
            return {"status": "OK", "score": 1.0}
        return {"status": "WARN", "score": 0.5,
                "warning": r.get("message", "unknown")}
    except Exception as e:
        return {"status": "FAIL", "score": 0.0, "error": str(e)}

# ─── التشخيص الكامل ───

def run_diagnostics(quick=False) -> dict:
    checks = {
        "routing"         : check_routing(),
        "context"         : check_context(),
        "release_analyzer": check_release_analyzer(),
        "work_tracker"    : check_work_tracker(),
    }
    if not quick:
        checks[GROQ] = check_groq()

    # حساب Health Score
    scores   = [c["score"] for c in checks.values()]
    health   = round(sum(scores) / len(scores) * 100)

    # تجميع التحذيرات
    warnings = [
        f"{k}: {v['warning']}"
        for k, v in checks.items()
        if v["status"] == "WARN" and "warning" in v
    ]
    failures = [
        f"{k}: {v.get('error','?')}"
        for k, v in checks.items()
        if v["status"] == "FAIL"
    ]

    result = {
        "timestamp": datetime.now().isoformat(),
        "health"   : health,
        "checks"   : checks,
        "warnings" : warnings,
        "failures" : failures,
        "quick"    : quick,
    }

    # Emit a canonical diagnostics event for observability (P014-03, P014-01)
    try:
        emit_event(
            "diagnostics.completed",
            source="self_diagnostics",
            context={"quick": quick},
            details={"health": health, "warnings": warnings, "failures": failures},
            persist=False,
        )
    except Exception:
        pass

    # حفظ آخر نتيجة
    _save_history(health, warnings)
    return result

def _save_history(health: int, warnings: list):
    try:
        os.makedirs(os.path.dirname(DIAG_HISTORY_FILE), exist_ok=True)
        with open(DIAG_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "last_check": datetime.now().isoformat(),
                "health"    : health,
                "warnings"  : len(warnings),
            }, f, ensure_ascii=False, indent=2)
    except:
        pass

def format_quick(result: dict) -> str:
    h = result["health"]
    w = len(result["warnings"])
    f = len(result["failures"])
    return f"Health: {h}%  |  Warnings: {w}  |  Failures: {f}"

def format_full(result: dict, context_store=None) -> str:
    lines = []
    lines.append(f"=== System Diagnostics ===")
    lines.append(f"Time   : {result['timestamp'][:19]}")
    lines.append(f"Health : {result['health']}%")
    lines.append("")

    for name, check in result["checks"].items():
        icon = "✅" if check["status"]=="OK" else "⚠️" if check["status"]=="WARN" else "❌"
        lines.append(f"{icon} {name:<20}: {check['status']}")

    if result["warnings"]:
        lines.append("\nWarnings:")
        for w in result["warnings"]:
            lines.append(f"  ⚠️  {w}")

    if result["failures"]:
        lines.append("\nFailures:")
        for f in result["failures"]:
            lines.append(f"  ❌ {f}")

    if context_store:
        lines.append("")
        lines.append(f"Last Intent  : {context_store.last_intent or '—'}")
        lines.append(f"Last Version : {context_store.current_version or '—'}")
        lines.append(f"Last File    : {context_store.current_file or '—'}")

    lines.append("=" * 26)
    return "\n".join(lines)
