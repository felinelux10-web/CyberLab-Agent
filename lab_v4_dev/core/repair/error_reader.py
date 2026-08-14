# CyberLab Agent v5.1
# core/repair/error_reader.py

import re
import json
from datetime import datetime

def parse_traceback(stderr: str, file_path: str = "") -> dict:
    if not stderr:
        return {"type": "unknown", "message": "", "line": None, "severity": "low"}

    # استخرج رقم السطر
    line_match = re.search(r'line (\d+)', stderr)
    line_num   = int(line_match.group(1)) if line_match else None

    # صنف نوع الخطأ
    error_type = "runtime"
    if "SyntaxError" in stderr:
        error_type = "syntax"
    elif "ImportError" in stderr or "ModuleNotFoundError" in stderr:
        error_type = "dependency"
    elif "NameError" in stderr or "AttributeError" in stderr:
        error_type = "name"
    elif "TypeError" in stderr or "ValueError" in stderr:
        error_type = "type"
    elif "KeyError" in stderr or "IndexError" in stderr:
        error_type = "runtime"
    elif "FileNotFoundError" in stderr:
        error_type = "file"
    elif "PermissionError" in stderr:
        error_type = "permission"

    # حدد الخطورة
    severity = "high" if error_type in ["syntax","dependency"] else "medium"

    # استخرج رسالة الخطأ الأساسية
    lines   = stderr.strip().split("\n")
    message = lines[-1] if lines else stderr[:100]

    return {
        "type"     : error_type,
        "file"     : file_path,
        "line"     : line_num,
        "message"  : message,
        "severity" : severity,
        "raw"      : stderr[:500],
        "timestamp": datetime.now().isoformat(),
    }

def read_error_report(report_path: str) -> dict:
    try:
        with open(report_path) as f:
            data = json.load(f)
        stderr = data.get("error", "")
        file   = data.get("file", "")
        parsed = parse_traceback(stderr, file)
        parsed["report_path"] = report_path
        return parsed
    except Exception as e:
        return {"type":"unknown","message":str(e),"severity":"low"}

def get_latest_error() -> dict:
    import os
    log_dir = "workspace/error_log"
    if not os.path.exists(log_dir):
        return {}
    files = sorted(
        [f for f in os.listdir(log_dir) if f.endswith(".json")],
        reverse=True
    )
    if not files:
        return {}
    return read_error_report(os.path.join(log_dir, files[0]))
