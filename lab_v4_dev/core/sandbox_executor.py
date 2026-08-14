# CyberLab Agent v5.0
# core/sandbox_executor.py

import subprocess
import os
import json
import time
from datetime import datetime

WORKSPACE = "workspace"
ERROR_LOG = "workspace/error_log"

def run_code(file_path, timeout=10):
    from lab_v4_dev.core.project_context import get_active_project_root
    os.makedirs(ERROR_LOG, exist_ok=True)
    if not os.path.exists(file_path):
        return {"status":"failed","error":"الملف غير موجود: " + file_path}
    start = time.time()
    try:
        result = subprocess.run(
            ["python3", file_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=get_active_project_root()
        )
        duration = round(time.time() - start, 2)
        stdout   = result.stdout.strip()
        stderr   = result.stderr.strip()

        # حفظ في history
        from lab_v4_dev.core.execution_history import save_run
        if result.returncode == 0:
            save_run(file_path, "success", duration, 0)
            return {
                "status"   : "success",
                "output"   : stdout,
                "file"     : file_path,
                "duration" : duration,
                "exit_code": 0,
            }
        else:
            save_run(file_path, "error", duration, result.returncode, stderr)
            report = _save_error_report(file_path, stderr, stdout)
            return {
                "status"    : "error",
                "output"    : stdout,
                "error"     : stderr,
                "file"      : file_path,
                "duration"  : duration,
                "exit_code" : result.returncode,
                "report"    : report,
            }
    except subprocess.TimeoutExpired:
        duration = round(time.time() - start, 2)
        from lab_v4_dev.core.execution_history import save_run
        save_run(file_path, "timeout", duration, -1)
        return {"status":"timeout","error":"تجاوز الوقت","file":file_path,"duration":duration}
    except Exception as e:
        return {"status":"failed","error":str(e),"file":file_path}

def dry_run(file_path):
    if not os.path.exists(file_path):
        return {"status":"failed","error":"الملف غير موجود"}
    result = subprocess.run(
        ["python3", "-m", "py_compile", file_path],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return {"status":"ok","message":"الكود صحيح — لا أخطاء في الصياغة"}
    else:
        return {"status":"error","error":result.stderr.strip()}

def _save_error_report(file_path, stderr, stdout):
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp"  : datetime.now().isoformat(),
        "file"       : file_path,
        "error"      : stderr,
        "output"     : stdout,
        "auto_fixed" : False,
        "fix_applied": None,
        "approved"   : False,
    }
    path = os.path.join(ERROR_LOG, "error_" + ts + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path

def list_error_reports():
    if not os.path.exists(ERROR_LOG):
        return []
    reports = []
    for f in sorted(os.listdir(ERROR_LOG), reverse=True):
        if f.endswith(".json"):
            with open(os.path.join(ERROR_LOG, f)) as fp:
                r = json.load(fp)
            reports.append({
                "file"     : f,
                "timestamp": r.get("timestamp","?"),
                "error"    : r.get("error","?")[:80],
                "approved" : r.get("approved", False),
            })
    return reports
