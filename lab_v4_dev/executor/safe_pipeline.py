# CyberLab Agent v4.6-prep
# executor/safe_pipeline.py

import json
import os
from datetime import datetime
from lab_v4_dev.awareness.dep_analyzer import analyze_file
from lab_v4_dev.awareness.project_memory import load_memory, save_memory
from lab_v4_dev.planner.impact_analyzer import analyze_impact
from lab_v4_dev.recovery.snapshot import take, list_snapshots, SNAPSHOTS_DIR
from lab_v4_dev.recovery.rollback import rollback
from lab_v4_dev.recovery.permissions import check_write
from lab_v4_dev.recovery.safe_apply import safe_apply
from lab_v4_dev.core.audit import emit_event

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache")

class SafePipeline:

    def __init__(self, db):
        self.db          = db
        self.transaction = None

    # ─────────────────────────────────────
    # Stage 1 — Pre-Execution Analysis
    # ─────────────────────────────────────
    def analyze(self, files: list) -> dict:
        memory  = load_memory()
        impacts = {}

        for f in files:
            impacts[f] = analyze_impact(f)

        overall_risk = "low"
        for f, imp in impacts.items():
            if imp["risk_level"] == "high":
                overall_risk = "high"
                break
            elif imp["risk_level"] == "medium":
                overall_risk = "medium"

        bundle = {
            "timestamp"   : datetime.now().isoformat(),
            "files"       : files,
            "impacts"     : impacts,
            "overall_risk": overall_risk,
            "project_files": memory.get("total_files", 0),
        }

        path = os.path.join(CACHE_DIR, "analysis_bundle.json")
        saved = safe_apply(path, json.dumps(bundle, ensure_ascii=False, indent=2))
        if saved.get("status") != "ok":
            raise OSError(f"analysis cache write rejected: {saved.get('reason', saved.get('status'))}")

        return bundle

    # ─────────────────────────────────────
    # Stage 2 — Build Execution Plan
    # ─────────────────────────────────────
    def build_plan(self, task: str, steps: list) -> dict:
        plan = {
            "task"      : task,
            "timestamp" : datetime.now().isoformat(),
            "steps"     : steps,
            "status"    : "pending",
        }

        path = os.path.join(CACHE_DIR, "execution_plan.json")
        saved = safe_apply(path, json.dumps(plan, ensure_ascii=False, indent=2))
        if saved.get("status") != "ok":
            raise OSError(f"execution plan cache write rejected: {saved.get('reason', saved.get('status'))}")

        return plan

    # ─────────────────────────────────────
    # Stage 3 — Multi-file Snapshot
    # ─────────────────────────────────────
    def snapshot_all(self, files: list) -> dict:
        snapshots  = {}
        failed     = []

        for file_path in files:
            try:
                check_write(file_path)
                result = take(file_path)
                if result["status"] == "ok":
                    snapshots[file_path] = result["snapshot"]
                    emit_event("safe_pipeline.snapshot_ok", source="safe_pipeline", context={"file": file_path}, details={"snapshot": result.get("snapshot")})
                else:
                    snapshots[file_path] = None
                    emit_event("safe_pipeline.snapshot_skipped", source="safe_pipeline", context={"file": file_path}, details={"status": result.get("status")})
            except Exception as e:
                failed.append({"file": file_path, "error": str(e)})
                emit_event("safe_pipeline.snapshot_failed", source="safe_pipeline", context={"file": file_path}, details={"error": str(e)})

        return {
            "snapshot_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "snapshots"  : snapshots,
            "failed"     : failed,
        }

    # ─────────────────────────────────────
    # Stage 4 — Execute Transaction
    # ─────────────────────────────────────
    def execute(self, plan: dict, modifications: dict) -> dict:
        files     = list(modifications.keys())
        emit_event("safe_pipeline.execute.start", source="safe_pipeline", context={"task": plan.get("task"), "files": files})
        bundle    = self.analyze(files)
        snapshots = self.snapshot_all(files)

        if snapshots["failed"]:
            emit_event("safe_pipeline.execute.aborted", source="safe_pipeline", context={"task": plan.get("task")}, details={"failed": snapshots["failed"]})
            return {
                "status" : "aborted",
                "reason" : "snapshot_failed",
                "failed" : snapshots["failed"],
            }

        results   = {}
        completed = []

        for file_path, new_content in modifications.items():
            try:
                emit_event("safe_pipeline.file_write.start", source="safe_pipeline", context={"file": file_path})
                applied = safe_apply(file_path, new_content)
                if applied.get("status") != "ok":
                    self._rollback_all(snapshots["snapshots"], completed)
                    reason = str(applied.get("reason") or "safe_apply_failed")
                    emit_event("safe_pipeline.file_write.failed", source="safe_pipeline", context={"file": file_path}, details={"reason": reason})
                    if reason.startswith("syntax_error:"):
                        return {"status": "failed", "reason": f"syntax_error in {file_path}", "error": reason.split(":", 1)[1].strip()}
                    return {"status": "failed", "reason": reason, "rolled_back": completed}

                completed.append(file_path)
                results[file_path] = "ok"
                emit_event("safe_pipeline.file_write.ok", source="safe_pipeline", context={"file": file_path}, details={"snapshot": applied.get("snapshot")})

            except Exception as e:
                self._rollback_all(snapshots["snapshots"], completed)
                emit_event("safe_pipeline.execute.failed", source="safe_pipeline", context={"task": plan.get("task")}, details={"error": str(e), "rolled_back": completed})
                return {
                    "status": "failed",
                    "reason": str(e),
                    "rolled_back": completed,
                }

        # تحديث project memory
        save_memory(self.db)
        emit_event("safe_pipeline.execute.success", source="safe_pipeline", context={"task": plan.get("task")}, details={"files_modified": len(completed), "snapshot_id": snapshots.get("snapshot_id"), "risk": bundle.get("overall_risk")})

        return {
            "status"     : "success",
            "files_modified": len(completed),
            "results"    : results,
            "snapshot_id": snapshots["snapshot_id"],
            "risk"       : bundle["overall_risk"],
        }

    # ─────────────────────────────────────
    # Stage 5 — Validation
    # ─────────────────────────────────────
    def _validate_syntax(self, file_path: str) -> dict:
        import ast

        if not file_path.endswith(".py"):
            return {"ok": True}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()

            ast.parse(source)
            return {"ok": True}

        except SyntaxError as e:
            return {"ok": False, "error": str(e)}

        except Exception:
            return {"ok": True}

    def _validate_imports(self, file_path: str) -> dict:
        try:
            analysis = analyze_file(file_path)
            return {"ok": True, "imports": analysis["imports"]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ─────────────────────────────────────
    # Rollback All
    # ─────────────────────────────────────
    def _rollback_all(self, snapshots: dict, files: list):
        emit_event("safe_pipeline.rollback_all", source="safe_pipeline", context={"files": files})
        for f in files:
            snap = snapshots.get(f)
            if snap:
                rollback(f, snap)
