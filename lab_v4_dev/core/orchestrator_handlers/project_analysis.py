"""Project dependency and impact query handlers."""

import os



def handle_dependency_map(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.awareness.dependency_map import get_critical_files, get_orphans
    from lab_v4_dev.core.project_context import get_active_project

    proj = get_active_project()
    map_path = os.path.join(proj.index_dir(), "dependency_map.json")
    if not os.path.exists(map_path):
        from lab_v4_dev.awareness.dependency_map import save_map
        save_map()
    critical = get_critical_files()[:5]
    orphans  = get_orphans()[:3]
    lines = ["الملفات الحرجة (الأكثر استخداماً):"]
    for f in critical:
        lines.append(f"  🔴 {f['file']} — يستخدمه {f['used_by']} ملف")
    if orphans:
        lines.append("\nملفات غير مرتبطة:")
        for f in orphans:
            lines.append(f"  ⚪ {f}")
    return {"status":"success","intent":intent,
            "text":"\n".join(lines)}

# ─── Read External Project (v5.9) ───



def handle_entry_point_query(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.awareness.dependency_engine import get_entry_points, get_critical_files, index_missing
    from lab_v4_dev.core.project_context import get_active_project
    if index_missing():
        _p = get_active_project()
        return {"status":"success","intent":intent,
                "text": f"لا يوجد فهرس لمشروع '{_p.name}' النشط حالياً.\nنفّذ 'اعمل على مشروع' أو 'اقرأ مشروع' أولاً لبنائه."}
    entries = get_entry_points()
    critical = get_critical_files()[:5]
    lines = ["نقطة الدخول للمشروع:"]
    for e in entries:
        lines.append(f"  🚀 {e}")
    lines.append("\nأهم الملفات (الأكثر استخداماً):")
    for c in critical:
        lines.append(f"  🔴 {c}")
    return {"status":"success","intent":intent,
            "text":"\n".join(lines)}


# ─── Dependents Query (v5.2.1 Dependency Engine) ───



def handle_dependents_query(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.awareness.dependency_engine import who_depends_on
    import re
    m = re.search(r"[\w./]+\.py", raw)
    q = m.group(0) if m else target or raw
    deps = who_depends_on(q)
    if not deps:
        return {"status":"success","intent":intent,
                "text":f"لا يوجد ملف يعتمد على {q} (وفق Dependency Engine)"}
    lines = [f"الملفات المعتمدة على {q}:"]
    for d in deps:
        lines.append(f"  📄 {d}")
    return {"status":"success","intent":intent,
            "text":"\n".join(lines)}


# ─── Dependencies Query (v5.5.1) ───



def handle_dependencies(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.awareness.dependency_engine import what_imports
    import re
    m = re.search(r"[\w./]+\.py", raw)
    q = m.group(0) if m else target or raw
    deps = what_imports(q)
    if not deps:
        return {"status":"success","intent":intent,
                "text":f"لا توجد اعتمادات لـ {q}"}
    lines = [f"اعتمادات {q}:"]
    for d in deps:
        lines.append(f"  📦 {d}")
    return {"status":"success","intent":intent,
            "text":"\n".join(lines)}

# ─── Impact Chain Query (v5.2.1 Impact Simulator) ───



def handle_impact_chain_query(orchestrator, intent, *, target=None, raw=None):
    from lab_v4_dev.awareness.dependency_engine import get_impact_chain
    import re
    m = re.search(r"[\w./]+\.py", raw)
    q = m.group(0) if m else target or raw
    chain = get_impact_chain(q)
    lines = [f"تحليل التأثير الشامل لـ {q}:"]
    lines.append(f"\nالتأثير المباشر ({len(chain['direct'])}):")
    for f in chain['direct']:
        lines.append(f"  🔴 {f}")
    if chain['indirect']:
        lines.append(f"\nالتأثير غير المباشر ({len(chain['indirect'])}):")
        for f in chain['indirect']:
            lines.append(f"  🟡 {f}")
    lines.append(f"\nإجمالي الملفات المتأثرة: {chain['total_affected']}")
    return {"status":"success","intent":intent,
            "text":"\n".join(lines)}




def handle_criticality_query(orchestrator, intent, *, target=None, raw=None):
    import re, sys
    sys.path.insert(0, "lab_v4_dev/awareness")
    from lab_v4_dev.awareness.query_engine import query_file, risk_level
    sys.path.insert(0, "lab_v4_dev/awareness")
    m = re.search(r"[\w./]+\.py", raw)
    q = m.group(0) if m else target or raw
    result = query_file(q)
    score = result["risk_score"]
    level = result["risk_level"]
    emoji = {"critical":"🔴","high":"🟠","medium":"🟡","low":"🟢"}.get(level,"⚪")
    lines = [f"تقرير خطورة {q}:"]
    lines.append(f"  {emoji} المستوى: {level}")
    lines.append(f"  📊 الدرجة: {score}/100")
    lines.append(f"  🔗 تأثير مباشر: {len(result['direct_dependencies'])}")
    lines.append(f"  🔗 تأثير غير مباشر: {len(result['indirect_dependencies'])}")
    lines.append(f"  📁 إجمالي المتأثرة: {result['total_affected']}")
    if result["is_entry_point"]:
        lines.append("  ⚠️  نقطة دخول رئيسية")
    return {"status":"success","intent":intent,"text":"\n".join(lines)}




__all__ = ["handle_dependency_map", "handle_entry_point_query", "handle_dependents_query", "handle_dependencies", "handle_impact_chain_query", "handle_criticality_query"]
