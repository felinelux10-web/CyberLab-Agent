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



__all__ = ["handle_read_file", "handle_project_scan", "handle_project_index"]
