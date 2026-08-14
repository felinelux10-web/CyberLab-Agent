# CyberLab Agent v5.1
# core/repair/diff_approval.py

import os
import json
from datetime import datetime

PENDING_DIR = "workspace/pending_fixes"

def create_diff(original_code: str, suggested_code: str) -> str:
    orig_lines = original_code.splitlines()
    sugg_lines = suggested_code.splitlines()
    diff = []
    max_lines = max(len(orig_lines), len(sugg_lines))
    for i in range(max_lines):
        orig = orig_lines[i] if i < len(orig_lines) else ""
        sugg = sugg_lines[i] if i < len(sugg_lines) else ""
        if orig != sugg:
            if orig: diff.append(f"- {orig}")
            if sugg: diff.append(f"+ {sugg}")
        else:
            diff.append(f"  {orig}")
    return "\n".join(diff[:30])

PATTERNS_PATH = "project_data/error_patterns.json"

def _learn_pattern(pending: dict):
    error    = pending.get("error", {}) or {}
    analysis = pending.get("analysis", {}) or {}
    import re
    message  = error.get("message","") or error.get("raw","")
    m        = re.search(r"(\w+(?:Error|Exception))", message)
    err_name = m.group(1) if m else ""
    if not err_name:
        return
    os.makedirs(os.path.dirname(PATTERNS_PATH), exist_ok=True)
    patterns = {}
    if os.path.exists(PATTERNS_PATH):
        try:
            with open(PATTERNS_PATH, encoding="utf-8") as f:
                patterns = json.load(f)
        except Exception:
            patterns = {}
    patterns[err_name] = {
        "cause"   : analysis.get("root_cause", pending.get("fix",{}).get("description","")),
        "category": analysis.get("category", "runtime"),
        "fixable" : True,
    }
    with open(PATTERNS_PATH, "w", encoding="utf-8") as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2)

def save_pending_fix(file_path: str, fix: dict, error: dict, analysis: dict = None) -> str:
    os.makedirs(PENDING_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pending = {
        "timestamp" : datetime.now().isoformat(),
        "file"      : file_path,
        "fix"       : fix,
        "error"     : error,
        "analysis"  : analysis or {},
        "approved"  : False,
        "applied"   : False,
    }
    path = os.path.join(PENDING_DIR, f"fix_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)
    return path

def show_fix_proposal(fix: dict, error: dict) -> str:
    lines = [
        "=== اقتراح إصلاح ===",
        f"الخطأ    : {error.get('message','?')[:60]}",
        f"النوع    : {error.get('type','?')}",
        f"الإصلاح  : {fix.get('description','?')}",
        f"النوع    : {fix.get('fix_type','?')}",
        f"الثقة    : {fix.get('confidence',0)*100:.0f}%",
    ]
    if fix.get("original") and fix.get("suggested"):
        lines.append("\n--- التغيير ---")
        lines.append(f"قبل : {fix['original'][:80]}")
        lines.append(f"بعد : {fix['suggested'][:80]}")
    lines.append("\nاكتب 'وافق' للتطبيق أو 'رفض' للإلغاء")
    return "\n".join(lines)

def apply_fix(pending_path: str) -> dict:
    with open(pending_path) as f:
        pending = json.load(f)
    fix       = pending["fix"]
    file_path = pending["file"]
    fix_type  = fix.get("fix_type","")

    if fix_type == "install_package":
        import subprocess
        cmd = fix.get("command","")
        if cmd:
            r = subprocess.run(cmd.split(), capture_output=True, text=True)
            success = r.returncode == 0
            pending["applied"]  = success
            pending["approved"] = True
            with open(pending_path,"w") as f:
                json.dump(pending, f, ensure_ascii=False, indent=2)
            if success:
                _learn_pattern(pending)
            return {"status":"success" if success else "failed",
                    "message": f"pip install: {'OK' if success else r.stderr[:100]}"}

    if fix_type == "replace_line" and os.path.exists(file_path):
        with open(file_path) as f:
            code = f.read()
        original  = fix.get("original","")
        suggested = fix.get("suggested","")
        matched = None
        if original:
            if original in code:
                matched = original
            else:
                alt = original.replace('"', "'") if '"' in original else original.replace("'", '"')
                if alt in code:
                    matched = alt
        if matched:
            new_code = code.replace(matched, suggested, 1)
            from lab_v4_dev.core.safe_io import safe_write
            write_result = safe_write(file_path, new_code,
                                        reason=f"repair: {fix.get('description','')}")
            if write_result["status"] != "success":
                return {"status":"failed","message":write_result.get("message","فشل الكتابة الآمنة")}
            pending["applied"]  = True
            pending["approved"] = True
            with open(pending_path,"w") as f:
                json.dump(pending, f, ensure_ascii=False, indent=2)
            _learn_pattern(pending)
            return {"status":"success","message":"تم التعديل","backup":write_result.get("backup")}

    return {"status":"needs_manual","message":"يحتاج تعديل يدوي"}

def list_pending() -> list:
    if not os.path.exists(PENDING_DIR):
        return []
    result = []
    for f in sorted(os.listdir(PENDING_DIR), reverse=True):
        if f.endswith(".json"):
            with open(os.path.join(PENDING_DIR, f)) as fp:
                p = json.load(fp)
            if not p.get("applied"):
                result.append({"file": f, "fix": p["fix"].get("description","?"),
                               "approved": p.get("approved",False)})
    return result
