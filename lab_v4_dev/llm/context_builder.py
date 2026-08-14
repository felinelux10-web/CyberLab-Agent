# CyberLab Agent v4.6
# llm/context_builder.py

from lab_v4_dev.awareness.state_reader import load as load_state
import json as _json
import os as _os

def build_system_prompt(db=None) -> str:
    # C: بيانات الجلسة من state_reader
    s = load_state()

    # A: بيانات المشروع من ProjectMetadata
    try:
        from lab_v4_dev.core.project_metadata import ProjectMetadata
        _meta = ProjectMetadata()
        _version       = _meta.get_version()
        _project_name  = _meta.get_project_name()
        _cur_phase     = _meta.get_current_phase()
        _current_focus = _cur_phase.get("name", "?") if _cur_phase else "?"
        _completed     = len(_meta.get_current_phase()) if _meta.get_current_phase() else 0
    except Exception:
        _version, _project_name, _current_focus, _completed = "?", "CyberLab Agent", "?", 0

    # B: بيانات الملفات من project_memory (عبر load_memory الديناميكي/fallback الصحيح)
    try:
        from lab_v4_dev.awareness.project_memory import load_memory
        _mem = load_memory()
        _files_count   = _mem.get("total_files", 0)
        _critical      = [c.get("file","") for c in _mem.get("critical_files",[])[:4]]
        _arch_layers   = list(_mem.get("architecture", {}).keys())
    except Exception:
        _files_count, _critical, _arch_layers = 0, [], []

    ctx = f"""أنت مساعد هندسي لمشروع {_project_name}.

معلومات المشروع الحقيقية:
- الإصدار الحالي: v{_version}
- عدد الملفات: {_files_count} ملف Python
- البيئة: Android/Termux
- الطبقات: {', '.join(_arch_layers)}
- الملفات الحرجة: {', '.join(_critical)}
- آخر الملفات المعدلة: {', '.join(s.get('last_modified_files',[])[:3])}
- التركيز الحالي: {_current_focus}

قواعد الرد:
- أجب بالعربية فقط
- اعتمد فقط على المعلومات أعلاه
- لا تخترع معلومات غير موجودة
- كن مختصراً ودقيقاً"""

    return ctx
