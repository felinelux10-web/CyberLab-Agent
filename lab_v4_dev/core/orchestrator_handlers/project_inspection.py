"""Project-inspection handlers migrated without changing legacy read semantics."""

import os


def handle_read_file(orchestrator, intent, *, target=None, raw=None):
    if not target:
        return {"status": "needs_target", "message": "أي ملف؟"}
    try:
        full_path = os.path.expanduser(target)

        if not os.path.isfile(full_path):
            from lab_v4_dev.awareness.project_index import search_index
            from lab_v4_dev.core.project_context import get_active_project_root

            matches = search_index(target)
            active_root = os.path.realpath(os.path.expanduser(get_active_project_root()))

            if matches:
                candidate = matches[0].get("path", "")
                if candidate:
                    candidate_path = os.path.realpath(os.path.join(active_root, candidate))
                    try:
                        inside_project = os.path.commonpath([active_root, candidate_path]) == active_root
                    except ValueError:
                        inside_project = False
                    if inside_project and os.path.isfile(candidate_path):
                        full_path = candidate_path

        with open(full_path, encoding="utf-8") as source_file:
            content = source_file.read()
        from lab_v4_dev.core.project_context import get_active_project_root
        from lab_v4_dev.core.audit import emit_event
        emit_event(
            "project.file_read", source="orchestrator",
            context={"project_root": get_active_project_root(), "file_path": full_path},
            details={
                "characters_read": len(content),
                "bytes_read": len(content.encode("utf-8")),
                "output_truncated": len(content) > 2000,
            },
        )
        return {
            "status": "success", "intent": intent,
            "output": content[:2000], "file": full_path,
        }
    except FileNotFoundError:
        return {"status": "failed", "message": f"غير موجود: {target}"}


def handle_project_scan(orchestrator, intent, *, target=None, raw=None):
    raw_text = raw or ""
    if any(
        phrase in raw_text for phrase in ["كم مشروع", "عدد المشاريع", "كم عدد المشاريع"]
    ):
        from lab_v4_dev.project_registry.project_loader import list_registered_projects

        projects = list_registered_projects()
        unique = {}
        for project in projects:
            root = project.get("root")
            if root:
                unique[root] = project
        return {
            "status": "success",
            "intent": intent,
            "source": "local",
            "text": f"عدد المشاريع المسجلة: {len(unique)}",
        }

    from lab_v4_dev.awareness.dependency_engine import (
        get_entry_points, get_critical_files, get_snapshot,
    )
    from lab_v4_dev.awareness.project_index import get_layer_map
    from lab_v4_dev.core.project_context import get_active_project

    active = get_active_project()
    snapshot = get_snapshot()
    layers = get_layer_map()
    entries = get_entry_points()
    critical = get_critical_files()[:5]
    total = snapshot.get("total_files", 0)
    try:
        from lab_v4_dev.core.project_metadata import ProjectMetadata
        version = ProjectMetadata().get_version()
    except Exception:
        version = "?"

    lines = [
        f"المشروع: {active.name}",
        f"الإصدار: {version}",
        f"إجمالي الملفات: {total}",
        f"نقاط الدخول: {', '.join(entries)}",
        f"الملفات الحرجة: {', '.join(critical[:3])}",
        "",
        "الطبقات:",
    ]
    for layer, files in layers.items():
        lines.append(f"  {layer}: {len(files)} ملف")
    text = chr(10).join(lines)

    from lab_v4_dev.core.audit import emit_event
    emit_event(
        "project.scan",
        source="orchestrator",
        context={"project_root": active.root},
        details={
            "project_name": active.name,
            "total_files": total,
            "entry_points": list(entries),
            "critical_files": list(critical),
            "layers": {str(layer): len(files) for layer, files in layers.items()},
        },
    )
    return {
        "status": "success",
        "intent": intent,
        "source": "local",
        "text": text,
        "total_files": total,
        "critical": critical,
    }



def handle_project_index(orchestrator, intent, *, target=None, raw=None):
    # طلبات قائمة المشاريع المسجلة تُفصل عن "خريطة المشروع".
    _project_list_terms = (
        "اسماء المشاريع", "أسماء المشاريع", "اسماءها", "أسماءها",
        "اسماؤها", "أسماؤها", "اسناؤها", "اسناءها",
        "قائمة المشاريع", "المشاريع المسجلة", "عدد المشاريع", "كم مشروع",
        "ترتب المشاريع", "رتب المشاريع", "ترتيب المشاريع",
        "المشاريع التي تظهر", "المشاريع الموجودة",
    )
    _is_project_list = any(term in raw for term in _project_list_terms)

    if _is_project_list:
        from lab_v4_dev.project_registry.project_loader import (
            list_registered_projects,
        )

        projects = list_registered_projects()
        unique = {}
        for project in projects:
            root = project.get("root")
            if root:
                unique[root] = project
        projects = list(unique.values())

        _wants_count = any(
            term in raw for term in (
                "عدد المشاريع", "كم مشروع", "كم عدد المشاريع"
            )
        )
        _wants_names = any(
            term in raw for term in (
                "اسماء المشاريع", "أسماء المشاريع",
                "اسماءها", "أسماءها",
                "اسماؤها", "أسماؤها",
                "اسناؤها", "اسناءها",
                "قائمة المشاريع"
            )
        )

        _order = None
        if any(term in raw for term in (
            "حسب الحروف", "حسب الأبجدية", "أبجديا",
            "أبجديًا", "أبجدي"
        )):
            _order = "alphabetical"
        elif any(term in raw for term in (
            "حسب الحجم", "الحجم", "أكبر مشروع", "اصغر مشروع",
            "أكبر المشاريع", "أصغر المشاريع"
        )):
            _order = "size"
        elif any(term in raw for term in (
            "حسب العمل", "حسب ترتيب العمل",
            "حسب العمل عليها", "ترتيب العمل"
        )):
            _order = "work"

        # العدد وحده لا يحتاج إلى اختيار ترتيب.
        if _wants_count and not _wants_names and _order is None:
            return {
                "status": "success",
                "intent": intent,
                "source": "local",
                "text": f"عدد المشاريع المسجلة: {len(projects)}"
            }

        # طلب أسماء بلا ترتيب واضح يحتاج توضيحاً قبل العرض.
        if (_wants_names or _order is not None) and _order is None:
            return {
                "status": "needs_clarification",
                "intent": intent,
                "source": "local",
                "text": (
                    "بأي ترتيب تريد عرض المشاريع؟\n"
                    "1. حسب ترتيب العمل عليها\n"
                    "2. أبجديًا\n"
                    "3. حسب الحجم"
                )
            }

        if _order == "alphabetical":
            projects.sort(
                key=lambda x: (
                    str(x.get("name", "")).lower(),
                    str(x.get("root", "")).lower(),
                )
            )
            lines = []
            if _wants_count:
                lines.append(f"عدد المشاريع: {len(projects)}")
            lines.append("المشاريع أبجديًا:")
            for project in projects:
                lines.append(
                    f"- {project.get('name', '?')} — {project.get('root', '?')}"
                )
            return {
                "status": "success",
                "intent": intent,
                "source": "local",
                "text": "\n".join(lines),
            }

        if _order == "size":
            import os as _os

            def _project_size(root):
                total = 0
                try:
                    for dirpath, dirnames, filenames in _os.walk(root):
                        dirnames[:] = [
                            d for d in dirnames
                            if d not in {".git", "__pycache__", ".cache"}
                        ]
                        for fname in filenames:
                            try:
                                total += _os.path.getsize(
                                    _os.path.join(dirpath, fname)
                                )
                            except OSError:
                                pass
                except OSError:
                    pass
                return total

            for project in projects:
                project["_size"] = _project_size(project["root"])

            projects.sort(
                key=lambda x: (-x["_size"], x.get("root", ""))
            )

            def _fmt_size(value):
                units = ("B", "KB", "MB", "GB", "TB")
                size = float(value)
                for unit in units:
                    if size < 1024 or unit == units[-1]:
                        return f"{size:.1f} {unit}"
                    size /= 1024
                return "0 B"

            lines = []
            if _wants_count:
                lines.append(f"عدد المشاريع: {len(projects)}")
            lines.append("المشاريع حسب الحجم:")
            for project in projects:
                lines.append(
                    f"- {project.get('name', '?')} — "
                    f"{_fmt_size(project['_size'])} — "
                    f"{project.get('root', '?')}"
                )
            return {
                "status": "success",
                "intent": intent,
                "source": "local",
                "text": "\n".join(lines),
            }

        if _order == "work":
            from lab_v4_dev.awareness.project_knowledge import (
                get_project_history_list,
            )

            history = get_project_history_list()
            history_by_root = {
                item.get("root"): item
                for item in history
                if item.get("root") and item.get("last_used")
            }

            missing = [
                project for project in projects
                if project.get("root") not in history_by_root
            ]

            if missing:
                return {
                    "status": "needs_clarification",
                    "intent": intent,
                    "source": "local",
                    "text": (
                        "لا أستطيع ترتيب جميع المشاريع حسب ترتيب العمل "
                        "بأمان لأن بعض المشاريع لا تملك سجلًا موثقًا "
                        "لآخر استخدام. اختر ترتيبًا أبجديًا أو حسب الحجم."
                    )
                }

            projects.sort(
                key=lambda x: history_by_root[x["root"]]["last_used"],
                reverse=True,
            )
            lines = []
            if _wants_count:
                lines.append(f"عدد المشاريع: {len(projects)}")
            lines.append("المشاريع حسب آخر ترتيب عمل موثق:")
            for project in projects:
                lines.append(
                    f"- {project.get('name', '?')} — "
                    f"{project.get('root', '?')} — "
                    f"{history_by_root[project['root']].get('last_used', '?')}"
                )
            return {
                "status": "success",
                "intent": intent,
                "source": "local",
                "text": "\n".join(lines),
            }

    # السلوك الأصلي: خريطة طبقات المشروع.
    from lab_v4_dev.awareness.project_index import get_layer_map
    layers = get_layer_map()
    lines  = ["خريطة المشروع:"]
    for layer, files in layers.items():
        lines.append(f"  {layer:<12}: {len(files)} ملف")
    return {"status":"success","intent":intent,
            "text":"\n".join(lines)}



def handle_search(orchestrator, intent, *, target=None, raw=None):
    import re as _re2
    import os as _os2
    # استخرج اسم الملف أو الكلمة المفتاحية
    stop = ["هل","يوجد","ملف","دالة","كلاس","في","هل يوجد","ابحث","عن","أين"]
    words = [w for w in raw.split() if w not in stop and len(w) > 1]
    q = words[-1] if words else target or raw
    # ابحث في inventory.json أولاً
    found_files = []
    inv_path = "lab_v4_dev/project_knowledge/inventory.json"
    try:
        import json as _jj
        inv = _jj.load(open(inv_path, encoding="utf-8"))
        found_files = [
            f["path"] for f in inv.get("files", [])
            if q.lower() in f["path"].lower() or q.lower() in f["filename"].lower()
        ]
    except Exception:
        pass
    if found_files:
        lines = [f"✅ وجدت '{q}' في المشروع:"]
        for fp in found_files[:5]:
            lines.append(f"  📄 {fp}")
        if len(found_files) > 5:
            lines.append(f"  ... و{len(found_files)-5} نتيجة أخرى")
        return {"status":"success","intent":intent,"text":"\n".join(lines)}
    else:
        return {"status":"success","intent":intent,
                "text":f"❌ '{q}' غير موجود في ملفات المشروع"}



def handle_search_code(orchestrator, intent, *, target=None, raw=None, authorized_ask=None):
    from lab_v4_dev.awareness.project_index import search_index, save_index
    import re
    from lab_v4_dev.core.project_context import get_active_project_root, project_index_dir
    active_root = os.path.abspath(get_active_project_root())
    if not os.path.exists(os.path.join(
        project_index_dir(active_root), "project_index.json"
    )):
        save_index()
    # An explicit path is authoritative; never replace it with the
    # last natural-language token (e.g. "المشروع؟").
    explicit_target = str(target or "").strip().strip(".,،؛:!?؟()[]{}\"'")
    is_explicit_path = bool(
        explicit_target
        and ("/" in explicit_target or "\\" in explicit_target
             or re.search(r"\.[A-Za-z0-9_-]+$", explicit_target))
    )
    if is_explicit_path:
        candidate = os.path.abspath(
            os.path.expanduser(explicit_target)
            if os.path.isabs(os.path.expanduser(explicit_target))
            else os.path.join(active_root, explicit_target)
        )
        try:
            real_root = os.path.realpath(active_root)
            real_candidate = os.path.realpath(candidate)
            inside_root = os.path.commonpath([real_root, real_candidate]) == real_root
        except ValueError:
            inside_root = False
        if not inside_root or not os.path.isfile(candidate):
            return {
                "status": "success", "intent": intent,
                "text": f"❌ الملف '{explicit_target}' غير موجود في ملفات المشروع الحقيقية",
                "target": explicit_target,
                "evidence": "filesystem_check",
            }
        q = os.path.relpath(candidate, active_root).replace(os.sep, "/")
        results = search_index(q)
        if not results:
            results = [{"path": q, "role": "", "score": 0}]
        lines = [f"✅ الملف '{q}' موجود في المشروع الحقيقي:"]
        for item in results[:3]:
            role = f" — {item['role']}" if item.get("role") else ""
            lines.append(f"  📄 {item['path']}{role}")
        return {
            "status": "success", "intent": intent,
            "source": "local_index+filesystem", "target": q,
            "evidence": "filesystem_check_and_project_index",
            "text": "\n".join(lines),
        }

    # Keyword search remains available when no explicit path exists.
    stop_words = ["أين","اين","وين","يوجد","في","اي","ملف","ابحث","عن","عن","ما","الملف","المسؤول"]
    words = [w for w in raw.split() if w not in stop_words and len(w) > 2]
    q = words[-1] if words else raw
    results = search_index(q)
    if not results:
        return {"status":"success","intent":intent,
                "text":f"لم أجد '{q}' في ملفات المشروع الحقيقية"}
    from lab_v4_dev.llm.prompt_builder import build_search_prompt
    prompt = build_search_prompt(q, results)
    result = authorized_ask(prompt, system="أنت مساعد هندسي. أجب فقط بناءً على البيانات المعطاة.", max_tokens=200)
    # إضافة الملفات الحقيقية دائماً
    lines = [f"الملفات الحقيقية المرتبطة بـ '{q}':"]
    for r in results[:3]:
        role = f" — {r['role']}" if r['role'] else ""
        lines.append(f"  📄 {r['path']}{role}")
    if result.get("text"):
        lines.append(f"\n{result['text']}")
    return {"status":"success","intent":intent,"source":"local+" + get_active_provider(),
            "text":"\n".join(lines)}

# ─── Dependency Query ───


__all__ = ["handle_read_file", "handle_project_scan", "handle_project_index", "handle_search", "handle_search_code"]
