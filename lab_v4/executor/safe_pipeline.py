# CyberLab Agent v4.6-prep
# executor/safe_pipeline.py

import json
import os
from datetime import datetime
from lab_v4.awareness.dep_analyzer import analyze_file
from lab_v4.awareness.project_memory import load_memory, save_memory
from lab_v4.planner.impact_analyzer import analyze_impact
from lab_v4.recovery.snapshot import take, list_snapshots, SNAPSHOTS_DIR
from lab_v4.recovery.rollback import rollback
from lab_v4.recovery.permissions import check_write

CACHE_DIR = "lab_v4/cache"

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
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)

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
        with open(path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)

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
                else:
                    snapshots[file_path] = None
            except Exception as e:
                failed.append({"file": file_path, "error": str(e)})

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
        bundle    = self.analyze(files)
        snapshots = self.snapshot_all(files)

        if snapshots["failed"]:
            return {
                "status" : "aborted",
                "reason" : "snapshot_failed",
                "failed" : snapshots["failed"],
            }

        results   = {}
        completed = []

        for file_path, new_content in modifications.items():
            try:
                check_write(file_path)

                tmp = file_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(new_content)

                # Syntax check
                validation = self._validate_syntax(tmp)
                if not validation["ok"]:
                    os.remove(tmp)
                    self._rollback_all(snapshots["snapshots"], completed)
                    return {
                        "status": "failed",
                        "reason": f"syntax_error in {file_path}",
                        "error" : validation["error"],
                    }

                os.replace(tmp, file_path)
                completed.append(file_path)
                results[file_path] = "ok"

            except Exception as e:
                self._rollback_all(snapshots["snapshots"], completed)
                return {
                    "status": "failed",
                    "reason": str(e),
                    "rolled_back": completed,
                }

        # تحديث project memory
        save_memory(self.db)

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
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
            ast.parse(source)
            return {"ok": True}
        except SyntaxError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": True}  # ليس Python

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
        for f in files:
            snap = snapshots.get(f)
            if snap:
                rollback(f, snap)
