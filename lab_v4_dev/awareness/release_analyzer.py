# CyberLab Agent v4.7
# awareness/release_analyzer.py

import os
import re

RELEASES_DIR = "releases"

def _version_key(v: str):
    """مفتاح فرز رقمي للإصدارات مثل v5.9.10.A"""
    import re as _re
    parts = _re.split(r"[.\-]", v.lstrip("v"))
    result = []
    for p in parts:
        if p.isdigit():
            result.append((0, int(p), ""))
        else:
            try:
                result.append((0, int(p[:-1]), p[-1]))
            except:
                result.append((1, 0, p))
    return result

def get_available_versions() -> list:
    versions = []
    for d in os.listdir(RELEASES_DIR):
        if re.match(r"v\d+\.", d):
            versions.append(d)
    return sorted(versions, key=_version_key)

def load_release(version: str) -> dict:
    """يقرأ تقرير إصدار معين"""
    # نحاول FINAL_REPORT أولاً ثم RELEASE_REPORT
    for fname in ["FINAL_REPORT.md", "RELEASE_REPORT.md"]:
        path = os.path.join(RELEASES_DIR, version, fname)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return {
                "version" : version,
                "file"    : path,
                "content" : content,
                "size"    : len(content),
            }
    return {"version": version, "content": None, "error": "not found"}

def compare_versions(v1: str, v2: str) -> dict:
    """يقرأ إصدارين للمقارنة"""
    r1 = load_release(v1)
    r2 = load_release(v2)
    return {
        "v1"      : r1,
        "v2"      : r2,
        "both_ok" : r1["content"] is not None and r2["content"] is not None,
    }

def extract_version_from_text(text: str) -> str:
    """يستخرج رقم الإصدار من النص"""
    m = re.search(r"v?(\d+\.\d+)", text)
    if m:
        ver = m.group(1)
        # جرب بـ v وبدون v
        for fmt in [f"v{ver}", ver]:
            path = os.path.join(RELEASES_DIR, fmt)
            if os.path.exists(path):
                return fmt
    return None
