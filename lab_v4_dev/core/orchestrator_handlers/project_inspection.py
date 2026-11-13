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


__all__ = ["handle_read_file"]
