
# CyberLab Agent v4.6-prep
# core/orchestrator.py
# Coordination Layer — Phase 5 (Full Control)

from datetime import datetime
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.executor.safe_pipeline import SafePipeline
from lab_v4_dev.awareness.project_memory import load_memory, save_memory
from lab_v4_dev.planner.impact_analyzer import analyze_impact
from lab_v4_dev.core.logger import log
from lab_v4_dev.context.context_store import ContextStore
from lab_v4_dev.context.context_resolver import bind_context
from lab_v4_dev.core.contracts import Request, Context, Response
from lab_v4_dev.llm.router import route as llm_route, needs_llm
from lab_v4_dev.llm.gateway import ask
from lab_v4_dev.config.provider_config import get_active_provider
import os
import shutil

class Orchestrator:

    def __init__(self, agent, context=None):
        self.agent    = agent
        self.history  = []
        self.active   = True
        self.phase    = "5-full-control"
        self.pipeline = None

        # Canonical ContextStore is owned by Agent.
        # Fallback preserves standalone Orchestrator compatibility.
        self.context  = context if context is not None else ContextStore()
        self._analyzed_files  = set()
        self._impact_analyzed = set()
        # ─── تعيين المشروع النشط الصحيح عند البدء ───
        try:
            from lab_v4_dev.core.project_context import set_active_project
            import os
            _default = os.path.expanduser("~/cyberlab_agent")
            set_active_project(_default)
        except:
            pass

    def _get_pipeline(self):
        if not self.pipeline:
            self.pipeline = SafePipeline(self.agent.db)
        return self.pipeline

    def handle(self, request: str, parsed: dict | None = None) -> dict:
        request = Request.from_input(request)
        raw_request = request.raw_text

        # DNI-10: ربط task_chain.py (كان معزولاً تماماً — صفر استدعاء في كل المشروع)
        from lab_v4_dev.core.task_chain import is_chain, detect_chain, execute_chain
        if is_chain(raw_request):
            steps = detect_chain(raw_request)
            if len(steps) > 1:
                return execute_chain(steps, self)

        timestamp = datetime.now().isoformat()

        # Intent authority:
        # ConversationManager may already have resolved the request.
        # Never resolve the same request a second time.
        if parsed is None:
            parsed = parse(raw_request)

        intent    = parsed["intent"]
        target    = parsed["target"]
        ctx_hint  = parsed["context"]

        entry = {
            "timestamp": timestamp,
            "request"  : request,
            "intent"   : intent,
            "target"   : target,
            "context"  : ctx_hint,
            "status"   : "pending",
        }

        # INTENT REBUILD — PATCH 01
        #
        # parse() is the canonical Intent resolution boundary.
        #
        # Context binding may enrich target/context metadata, but the
        # Orchestrator MUST NOT replace the Intent already resolved by
        # the parser.
        #
        # Semantic Router remains available for compatibility elsewhere,
        # but it is not permitted to re-classify this request here.

        operational_context = Context.from_store(self.context)
        bound = bind_context(intent, raw_request, self.context)

        if bound.get("target"):
            target = bound["target"]
        # ─── Pre-handler Policy ───
        blocked = self._pre_handler_policy(intent, target, raw_request)
        if blocked:
            return blocked
        # ─── Runtime Execution (Series 9) ───
        _rt = getattr(self.agent, "runtime", None)
        if _rt:
            try:
                _rt.start(
                    operation=intent,
                    project="cyberlab_agent",
                    goal=intent,
                    phase="execution"
                )
                _rt.update_active_file(target)
            except:
                pass
        result = self._route(intent, target, ctx_hint, raw_request)
        if _rt:
            try:
                _rt.end({
                    "intent": intent,
                    "status": result.get("status")
                })
            except:
                pass
        # ─── Apply Profile ───
        result = self._apply_profile(result, intent)

        # v5.3.1 — إضافة تحذير تلقائي حسب مستوى الخطورة
        from lab_v4_dev.intent.risk_levels import get_warning
        warning = get_warning(intent)
        if warning and isinstance(result, dict):
            result["warning"] = warning

        entry["status"] = result.get("status", "unknown")
        # لا تحدث السياق عند show_last_result
        if intent != "show_last_result":
            self.context.update(intent, target, result)
        self.history.append(entry)

        log.debug(f"Orch[{self.phase}]: {intent} → {entry['status']}")
        return result

    def _pre_handler_policy(self, intent, target, raw) -> dict | None:
        """طبقة البصمة — قبل التنفيذ. ترجع dict إذا يجب الإيقاف، أو None إذا مسموح."""
        try:
            from lab_v4_dev.user_data.profile_loader import load_profile
            p = load_profile()
        except:
            return None
        eng  = p.get("engineering_style", {})
        mem  = p.get("memory_policy", {})
        trust= p.get("trust_policy", {})

        # analyze_before_modify
        if intent in ("modify_code","modify_file") and eng.get("analyze_before_modify", False):
            if target and target not in getattr(self, "_analyzed_files", set()):
                return {"status":"blocked","intent":intent,
                        "text": "❌ يجب تحليل الملف اولاً قبل التعديل. استخدم: حلل ملف " + str(target)}

        # require_impact_analysis — يشغّل التحليل تلقائياً بدل المنع
        if intent in ("modify_code","repair_approve") and eng.get("require_impact_analysis", False):
            if target and target not in getattr(self, "_impact_analyzed", set()):
                try:
                    from lab_v4_dev.awareness.dependency_map import get_impact
                    get_impact(target)
                    self._impact_analyzed.add(target)
                except:
                    pass

        # allow_guessing = false
        if not trust.get("allow_guessing", True):
            if intent in ("self_diagnose","full_diagnose","repair_analyze"):
                pass  # هذه لها مصادر حقيقية — مسموح

        # auto_save = false
        if not mem.get("auto_save", True):
            if intent == "save_kb":
                return {"status":"blocked","intent":intent,
                        "text":"💾 الحفظ التلقائي معطل. يجب الموافقة اليدوية أولاً."}

        return None

    def _apply_profile(self, result: dict, intent: str) -> dict:
        """طبقة البصمة — بعد التنفيذ. تعدل شكل النتيجة فقط."""
        try:
            from lab_v4_dev.user_data.profile_loader import load_profile
            p = load_profile()
        except:
            return result
        eng = p.get("engineering_style", {})

        # تذكير Smoke Test
        if intent in ("modify_code","generate_code","repair_approve"):
            if eng.get("smoke_test_required", False):
                result["profile_reminder"] = "🧪 تذكير: Smoke Test مطلوب حسب سياسة المستخدم."

        # تذكير versioning
        if intent in ("modify_code","repair_approve"):
            if eng.get("versioning_required", False):
                current = result.get("profile_reminder","")
                result["profile_reminder"] = current + "\n📦 تذكير: احفظ إصداراً جديداً بعد التعديل."

        return result

    def _route(self, intent, target, context, raw) -> dict:

        # ─── Response Cache ───
        from lab_v4_dev.intent.response_cache import get as rcache_get
        _cache_intents = ["analyze_code","project_scan","cyber_explain","health","self_diagnose"]
        if intent in _cache_intents:
            # لا نستخدم cache لـ analyze_code بدون target محدد (يمنع النتائج القديمة)
            _skip_cache = (intent == "analyze_code" and not target)
            if not _skip_cache:
                cached = rcache_get(str(intent), target or "")
                if cached:
                    return {"status":"success","intent":intent,"source":"cache","text":cached}

        # ─── قراءة ───
        if intent == Intent.READ_FILE:
            if not target:
                return {"status": "needs_target", "message": "أي ملف؟"}
            try:
                full_path = os.path.expanduser(target)

                if not os.path.isfile(full_path):
                    from lab_v4_dev.awareness.project_index import search_index

                    matches = search_index(target)

                    if matches:
                        candidate = matches[0].get("path", "")
                        if candidate:
                            full_path = os.path.expanduser(
                                f"~/cyberlab_agent/{candidate}"
                            )

                text = open(full_path, encoding="utf-8").read()

                return {"status": "success", "intent": intent,
                        "output": text[:2000], "file": full_path}

            except FileNotFoundError:
                return {"status": "failed", "message": f"غير موجود: {target}"}

        # ─── فحص المشروع — بيانات محلية أولاً ───
        elif intent == Intent.PROJECT_SCAN:
            from lab_v4_dev.awareness.dependency_engine import get_entry_points, get_critical_files, get_snapshot
            from lab_v4_dev.awareness.project_index import get_layer_map
            from lab_v4_dev.core.project_context import get_active_project
            active  = get_active_project()
            snap    = get_snapshot()
            layers  = get_layer_map()
            entries = get_entry_points()
            critical = get_critical_files()[:5]
            total   = snap.get("total_files", 0)
            # قراءة الإصدار من ProjectMetadata
            try:
                from lab_v4_dev.core.project_metadata import ProjectMetadata
                _version = ProjectMetadata().get_version()
            except:
                _version = "?"
            # بناء تقرير محلي
            lines = [
                f"المشروع: {active.name}",
                f"الإصدار: {_version}",
                f"إجمالي الملفات: {total}",
                f"نقاط الدخول: {', '.join(entries)}",
                f"الملفات الحرجة: {', '.join(critical[:3])}",
                "",
                "الطبقات:",
            ]
            for layer, files in layers.items():
                lines.append(f"  {layer}: {len(files)} ملف")
            text = chr(10).join(lines)
            return {
                "status"     : "success",
                "intent"     : intent,
                "source"     : "local",
                "text"       : text,
                "total_files": total,
                "critical"   : critical,
            }

        # ─── تحليل تأثير ───
        elif intent == Intent.IMPACT_ANALYSIS:
            if not target:
                return {"status": "needs_target", "message": "أي ملف؟"}
            impact = analyze_impact(target)
            if impact:
                self._impact_analyzed.add(target)
            return {"status": "success", "intent": intent, "impact": impact}

        # ─── التغييرات ───
        elif intent == Intent.SHOW_CHANGES:
            tasks = self.agent.memory.recent_tasks(10)
            lines = ["آخر التعديلات:"]
            for t in tasks:
                icon = "✅" if t["status"] == "success" else "❌"
                lines.append(f"  {icon} {t['intent'][:40]}")
            return {
                "status": "success",
                "intent": intent,
                "text"  : chr(10).join(lines),
                "tasks" : [{"intent": t["intent"][:40],
                            "status": t["status"]} for t in tasks],
            }

        # ─── تنظيف ───
        elif intent == Intent.CLEAN or intent == Intent.CLEAN_DEVICE:
            from lab_v4_dev.core.cleaner import run_full_clean
            result = run_full_clean()
            lines = ["=== تنظيف الهاتف ==="]
            lines.append(f"📦 المساحة قبل : {result['before_mb']} MB")
            lines.append(f"📦 المساحة بعد : {result['after_mb']} MB")
            lines.append(f"🗑️ تم تحرير   : {result['freed_mb']} MB ({result['freed_kb']} KB)")
            lines.append("─── التفاصيل ───")
            for d in result["details"]:
                lines.append(f"  {d['type']}: حذف {d['removed']} عنصر — {d['size_kb']} KB")
            return {"status":"success","intent":intent,"text":chr(10).join(lines)}

        # ─── مساحة ───
        elif intent == Intent.SPACE:
            total, used, free = shutil.disk_usage(os.path.expanduser("~"))
            return {
                "status": "success", "intent": intent,
                "total" : f"{total//(1024**3)}GB",
                "used"  : f"{used//(1024**2)}MB",
                "free"  : f"{free//(1024**2)}MB",
            }

        # ─── حالة ───
        elif intent == Intent.STATUS:
            s = self.agent.state
            h = self.agent.session.summary()
            lines = [
                f"الوضع     : {s.mode}",
                f"المهام    : {h['tasks_done']}",
                f"الأخطاء   : {h['error_count']}",
                f"الإخفاقات : {s.consecutive_failures}",
            ]
            return {
                "status"  : "success", "intent": intent,
                "text"    : chr(10).join(lines),
                "mode"    : s.mode,
                "failures": s.consecutive_failures,
                "tasks"   : h["tasks_done"],
                "errors"  : h["error_count"],
            }

        # ─── صحة النظام ───
        elif intent == Intent.HEALTH:
            from lab_v4_dev.monitor.health_check import check_health
            h = check_health(self.agent.state)
            return {"status": "success", "intent": intent, "health": h}

        # ─── تقرير ───
        elif intent in [Intent.REPORT, Intent.SESSION_REPORT]:
            h   = self.agent.session.summary()
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            return {
                "status"  : "success", "intent": intent,
                "time"    : now,
                "session" : h,
            }

        # ─── ذاكرة المشروع ───
        elif intent == Intent.MEMORY_STATUS:
            memory = load_memory()
            return {
                "status"      : "success", "intent": intent,
                "total_files" : memory.get("total_files", 0),
                "last_updated": memory.get("last_updated", "unknown"),
            }

        # ─── تقارير المشروع ───
        elif intent in [Intent.PROGRESS_REPORT, Intent.REMAINING_WORK,
                        Intent.PROJECT_REPORT]:
            memory  = load_memory()
            total   = memory.get("total_files", 0)
            from lab_v4_dev.llm.prompt_builder import build_project_context
            system  = build_project_context()
            result  = ask(raw, system=system, max_tokens=400)
            return {
                "status": result["status"],
                "intent": intent,
                "source": result.get("provider_used", get_active_provider()),
                "text"  : result.get("text",""),
            }

        # ─── Groq للمهام المعقدة ───
        elif needs_llm(intent):
            from lab_v4_dev.llm.prompt_builder import build_project_context
            system = build_project_context()
            result = ask(raw, system=system, max_tokens=300)
            return {
                "status" : result["status"],
                "intent" : intent,
                "source" : result.get("provider_used", get_active_provider()),
                "route"  : result.get("provider_used", get_active_provider()),
                "text"   : result.get("text", result.get("message", "")),
                "tokens" : result.get("tokens", 0),
            }

        # ─── تقرير السياق ───
        elif intent == Intent.CONTEXT_REPORT:
            from lab_v4_dev.core.project_metadata import ProjectMetadata
            _meta = ProjectMetadata()
            tasks = self.agent.memory.recent_tasks(10)
            releases = sorted([
                d for d in os.listdir("releases")
                if os.path.isdir(f"releases/{d}")
            ]) if os.path.exists("releases") else []
            _cur_phase = _meta.get_current_phase()
            return {
                "status"  : "success",
                "intent"  : intent,
                "version" : _meta.get_version(),
                "focus"   : _meta.get_project_name(),
                "phases"  : [_cur_phase.get("name","?")] if _cur_phase else [],
                "releases": releases,
                "tasks"   : [{"status": t["status"],
                              "intent": t["intent"][:60]}
                             for t in tasks],
            }

        # ─── نتيجة آخر أمر ───
        elif intent == "show_last_result":
            data = self.context.last_result
            if not data:
                return {"status":"success","intent":intent,
                        "text":"لا يوجد نتيجة سابقة"}
            # عرض النتيجة السابقة
            output = data.get("text") or data.get("output") or str(data)[:300]
            return {"status":"success","intent":intent,"text":output}

        # ─── سجل المهام ───
        elif intent == Intent.HISTORY:
            tasks = self.agent.memory.recent_tasks(10)
            return {
                "status": "success",
                "intent": intent,
                "tasks" : [{"status": t["status"],
                            "intent": t["intent"][:50]} for t in tasks],
            }

        # ─── آخر مشروع ───
        elif intent == Intent.LAST_PROJECT:
            from lab_v4_dev.awareness.project_knowledge import get_project_history
            hist = get_project_history()
            last = hist.get("last_project","?")
            last_root = hist.get("last_root","?")
            history = hist.get("history",[])
            lines = [f"آخر مشروع: {last}", f"المسار: {last_root}", ""]
            if len(history) > 1:
                lines.append("المشاريع السابقة:")
                for h in history[1:4]:
                    lines.append(f"  - {h['name']} ({h['last_used']})")
            return {"status":"success","intent":intent,"text":chr(10).join(lines)}

        # ─── الإصدار الحالي ───
        elif intent == Intent.CURRENT_VERSION:
            from lab_v4_dev.awareness.project_knowledge import get_current_version
            version = get_current_version()
            return {"status":"success","intent":intent,
                    "text":f"الإصدار الحالي: {version}"}

        # ─── قائمة الإصدارات ───
        elif intent == Intent.RELEASE_INDEX:
            from lab_v4_dev.awareness.release_analyzer import get_available_versions
            versions = get_available_versions()
            return {
                "status"  : "success",
                "intent"  : intent,
                "text"    : "الإصدارات المتاحة: " + ", ".join(versions),
                "versions": versions,
            }

        # ─── تحليل إصدار معين ───
        elif intent == Intent.ANALYZE_RELEASE:
            from lab_v4_dev.awareness.release_analyzer import (
                load_release, extract_version_from_text
            )
            ver = extract_version_from_text(target or raw)
            if not ver:
                ver = self.context.current_version
            if not ver:
                return {"status":"needs_target","message":"أي إصدار؟ مثال: حلل الإصدار 4.1"}
            release = load_release(ver)
            if not release["content"]:
                return {"status":"failed","message":f"لا يوجد تقرير للإصدار {ver}"}
            content = release["content"][:800]
            from lab_v4_dev.llm.prompt_builder import build_release_prompt
            prompt  = build_release_prompt(ver, content, raw)
            result  = ask(prompt, system="أنت مساعد هندسي. أجب فقط من التقرير المعطى.", max_tokens=400)
            self.context.current_version = ver
            self.context.current_subject = f"version_{ver}"
            return {
                "status" : result["status"],
                "intent" : intent,
                "source" : result.get("provider_used", get_active_provider()),
                "version": ver,
                "text"   : result.get("text",""),
            }

        # ─── مقارنة إصدارين ───
        elif intent == Intent.COMPARE_FILES:
            # Resolve comparison operands through the canonical project index.
            # This follows the same project-file resolution contract used by
            # READ_FILE and avoids stale/static inventory snapshots.
            import re as _re3
            from pathlib import Path as _Path
            from lab_v4_dev.awareness.project_index import search_index

            _files = _re3.findall(
                r"[A-Za-z0-9_./~-]+\.[A-Za-z0-9_]+",
                raw
            )

            if len(_files) < 2:
                return {
                    "status": "needs_target",
                    "intent": intent,
                    "message": (
                        "حدد ملفين للمقارنة. مثال: "
                        "ما الفرق بين orchestrator.py و agent.py"
                    ),
                }

            _f1, _f2 = _files[0], _files[1]

            def _resolve_compare_file(name):
                candidate = _Path(name).expanduser()

                # 1. Explicit absolute path.
                if candidate.is_absolute() and candidate.is_file():
                    return candidate.resolve()

                # 2. Direct path relative to CyberLab-Agent.
                _project_root = (_Path.home() / "cyberlab_agent").resolve()
                direct = (_project_root / name).resolve()

                try:
                    direct.relative_to(_project_root)
                    if direct.is_file():
                        return direct
                except ValueError:
                    pass

                # 3. Canonical project index lookup.
                try:
                    matches = search_index(name)
                except Exception:
                    matches = []

                for match in matches:
                    candidate_path = match.get("path", "")
                    if candidate_path:
                        resolved = _Path(candidate_path).expanduser().resolve()
                        if resolved.is_file():
                            return resolved

                # 4. Dynamic fallback over the actual CyberLab-Agent tree.
                # This handles basename requests such as cleaner.py/state.py
                # when the active project index points elsewhere.
                try:
                    matches = []

                    for path in _project_root.rglob(candidate.name):
                        if not path.is_file():
                            continue

                        rel = path.resolve().relative_to(_project_root)
                        rel_s = str(rel).replace("\\", "/")

                        # Ignore generated/archive trees.
                        if any(
                            part in rel.parts
                            for part in ("__pycache__", ".git", "releases", "stable")
                        ):
                            continue

                        wanted = str(candidate).replace("\\", "/").lstrip("./")

                        if (
                            rel_s == wanted
                            or rel_s.endswith("/" + wanted)
                            or candidate.name == path.name
                        ):
                            matches.append(path.resolve())

                    if matches:
                        return sorted(
                            matches,
                            key=lambda x: len(str(x.relative_to(_project_root)))
                        )[0]

                except Exception:
                    pass

                return None

            _full1 = _resolve_compare_file(_f1)
            _full2 = _resolve_compare_file(_f2)

            if not _full1 or not _full2:
                missing = _f1 if not _full1 else _f2
                return {
                    "status": "failed",
                    "intent": intent,
                    "text": f"❌ لم أجد '{missing}' في ملفات المشروع",
                }

            try:
                _c1 = _full1.read_text(encoding="utf-8")
                _c2 = _full2.read_text(encoding="utf-8")
            except Exception as _e:
                return {
                    "status": "failed",
                    "intent": intent,
                    "message": str(_e),
                }

            prompt = (
                "قارن بين هذين الملفين من مشروع Python:\n\n"
                f"=== {_full1} ===\n{_c1[:6000]}\n\n"
                f"=== {_full2} ===\n{_c2[:6000]}\n\n"
                "أجب بالعربية: ما الفروقات الرئيسية "
                "في الوظيفة والمسؤولية؟"
            )

            system = (
                "أنت مساعد هندسي. قارن فقط بناءً على الكود المعطى. "
                "لا تخترع معلومات."
            )

            result = ask(
                prompt,
                system=system,
                max_tokens=400
            )

            return {
                "status": result["status"],
                "intent": intent,
                "source": result.get(
                    "provider_used",
                    get_active_provider()
                ),
                "text": result.get("text", ""),
            }

        elif intent == Intent.COMPARE_VERSIONS:
            from lab_v4_dev.awareness.release_analyzer import (
                compare_versions, extract_version_from_text
            )
            import re
            versions = re.findall(r"v?4\.\d", raw)
            if len(versions) < 2:
                return {"status":"needs_target","message":"حدد إصدارين. مثال: قارن بين 4.4 و 4.6"}
            v1 = f"v{versions[0]}" if not versions[0].startswith("v") else versions[0]
            v2 = f"v{versions[1]}" if not versions[1].startswith("v") else versions[1]
            data = compare_versions(v1, v2)
            if not data["both_ok"]:
                return {"status":"failed","message":f"لا يوجد تقرير لأحد الإصدارين"}
            prompt = (
                f"قارن بين الإصدارين:\n\n"
                f"=== {v1} ===\n{data['v1']['content'][:400]}\n\n"
                f"=== {v2} ===\n{data['v2']['content'][:400]}\n\n"
                f"أجب بالعربية: ما الفروقات الرئيسية؟"
            )
            system = "أنت مساعد هندسي متخصص في تحليل إصدارات البرمجيات. أجب بإيجاز."
            result = ask(prompt, system=system, max_tokens=400)
            return {
                "status": result["status"],
                "intent": intent,
                "source": result.get("provider_used", get_active_provider()),
                "v1"    : v1,
                "v2"    : v2,
                "text"  : result.get("text",""),
            }

        # ─── Work Tracker ───
        elif intent in [Intent.WORK_STATUS, Intent.REMAINING_TASKS, Intent.NEXT_TASK]:
            from lab_v4_dev.data.work_tracker import get_status, get_next_task, get_remaining
            s = get_status()
            if intent == Intent.NEXT_TASK:
                return {"status":"success","intent":intent,
                        "text": f"المهمة التالية: {get_next_task()}"}
            if intent == Intent.REMAINING_TASKS:
                remaining = get_remaining()
                text = "المتبقي:\n" + "\n".join(f"  - {t}" for t in remaining)
                return {"status":"success","intent":intent,"text":text}
            # WORK_STATUS
            lines = [
                f"الإصدار: {s['version']}",
                f"التركيز: {s['current_focus']}",
                f"مكتمل  : {', '.join(s['completed']) or 'لا شيء'}",
                f"نشط    : {', '.join(s['active']) or 'لا شيء'}",
                f"مخطط   : {', '.join(s['planned']) or 'لا شيء'}",
            ]
            if s['blocked']:
                lines.append(f"محظور  : {', '.join(s['blocked'])}")
            return {"status":"success","intent":intent,"text":"\n".join(lines)}



        # ─── Plan Change (PIE) ───
        elif intent == Intent.PLAN_CHANGE:
            import re as _re_pie
            m = _re_pie.search(r'[\w./]+\.py', raw)
            if not m:
                return {"status":"needs_clarification","intent":intent,
                        "text":"أي ملف تريد تخطيط تعديله؟ مثال: خطط لتعديل core/agent.py"}
            target_file = m.group(0)
            try:
                from lab_v4_dev.project_knowledge.analysis_engine import AnalysisEngine
                from lab_v4_dev.project_knowledge.change_planner import ChangePlanner
                engine = AnalysisEngine()
                if os.path.exists(target_file):
                    engine.analyze_file(target_file)
                plan = ChangePlanner().create_plan(target_file)
                impacted = plan.get('impacted', [])
                exec_plan = plan.get('execution_plan', [])
                lines = ["خطة تعديل " + target_file + ":"]
                if impacted:
                    lines.append("الملفات المتأثرة (" + str(len(impacted)) + "):")
                    for f2 in impacted[:5]:
                        lines.append("  ⚠️  " + f2)
                else:
                    lines.append("✅ لا توجد ملفات متأثرة مباشرة")
                if exec_plan:
                    lines.append("خطوات التنفيذ (" + str(len(exec_plan)) + "):")
                    for step in exec_plan[:3]:
                        lines.append("  [" + str(step.get('step','?')) + "] " + step.get('file','') + " — " + step.get('action','') + " (" + step.get('priority','') + ")")
                lines.append("ℹ️ هذه خطة معاينة فقط — لا يتم أي تعديل حتى الآن.")
                return {"status":"success","intent":intent,"source":"pie",
                        "text":"\n".join(lines)}
            except Exception as _e_pie:
                return {"status":"failed","intent":intent,
                        "text":"خطأ في PIE: " + str(_e_pie)}

        # ─── Capabilities ───
        elif intent == Intent.CAPABILITIES:
            from lab_v4_dev.core.project_context import get_active_project as _gap
            _proj = _gap()
            _mem  = load_memory()
            _total = _mem.get("total_files", 0)
            _lines = [
                "=== CyberLab Agent ===",
                "",
                "فهم المشاريع: Python وTypeScript • الاعتماديات • نقاط الدخول • الملفات الحرجة",
                "تحليل الأخطاء: كشف • تحليل • إصلاح • تعلم تلقائي",
                "كتابة الكود: سكريبتات Python • تشغيل وتحليل",
                "الأمن السيبراني: شرح مفاهيم • حفظ محلي",
                "الذاكرة: حفظ الجلسات • سياق العمل",
                "",
                f"المشروع الحالي: {_proj.name} ({_total} ملف)",
            ]
            return {"status":"success","intent":intent,"source":"local",
                    "text":"\n".join(_lines)}

        # ─── Self Diagnostics ───
        elif intent in [Intent.SELF_DIAGNOSE, Intent.FULL_DIAGNOSE]:
            from lab_v4_dev.monitor.self_diagnostics import (
                run_diagnostics, format_quick, format_full
            )
            quick  = (intent == Intent.SELF_DIAGNOSE)
            result = run_diagnostics(quick=quick)
            text   = format_quick(result) if quick else format_full(result, self.context)
            return {
                "status": "success",
                "intent": intent,
                "text"  : text,
                "health": result["health"],
            }

        # ─── Project Index ───
        elif intent == Intent.PROJECT_INDEX:
            from lab_v4_dev.awareness.project_index import get_layer_map
            layers = get_layer_map()
            lines  = ["خريطة المشروع:"]
            for layer, files in layers.items():
                lines.append(f"  {layer:<12}: {len(files)} ملف")
            return {"status":"success","intent":intent,
                    "text":"\n".join(lines)}

        elif intent == Intent.SEARCH:
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

        elif intent == Intent.SEARCH_CODE:
            from lab_v4_dev.awareness.project_index import search_index, save_index
            import re
            if not os.path.exists("project_data/project_index.json"):
                save_index()
            # استخرج الكلمة المفتاحية من الأمر
            stop_words = ["أين","اين","وين","يوجد","في","اي","ملف","ابحث","عن","عن","ما","الملف","المسؤول"]
            words = [w for w in raw.split() if w not in stop_words and len(w) > 2]
            q = words[-1] if words else target or raw
            results = search_index(q)
            if not results:
                return {"status":"success","intent":intent,
                        "text":f"لم أجد '{q}' في ملفات المشروع الحقيقية"}
            from lab_v4_dev.llm.prompt_builder import build_search_prompt
            prompt = build_search_prompt(q, results)
            result = ask(prompt, system="أنت مساعد هندسي. أجب فقط بناءً على البيانات المعطاة.", max_tokens=200)
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
        elif intent == Intent.FILE_IMPACT and any(w in raw for w in ["تعتمد على","يعتمد على","تستخدم","يستخدم","من يستورد","تستورد"]):
            from lab_v4_dev.awareness.dependency_map import get_impact
            import re
            if not os.path.exists("project_data/dependency_map.json"):
                from lab_v4_dev.awareness.dependency_map import save_map
                save_map()
            # استخرج اسم الملف
            m = re.search(r"[\w./]+\.py", raw)
            q = m.group(0) if m else target or raw
            impact = get_impact(q)
            imported_by = impact.get("imported_by", [])
            if not imported_by:
                return {"status":"success","intent":intent,
                        "text":f"لا يوجد ملف يعتمد على {q} بشكل مباشر"}
            lines = [f"الملفات التي تعتمد على {q}:"]
            for f in imported_by:
                lines.append(f"  📄 {f}")
            return {"status":"success","intent":intent,
                    "text":"\n".join(lines)}

        # ─── Dependency Map ───
        elif intent == Intent.DEPENDENCY_MAP:
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
        elif intent == Intent.READ_EXTERNAL_PROJECT:
            import re as _re, sys
            m = _re.search(r'(~/\S+|/\S+)', raw)
            if m:
                path = os.path.expanduser(m.group(1))
            else:
                path = os.path.expanduser("~/external_projects/dynamic-lab-app")
            if not os.path.exists(path):
                return {"status":"success","intent":intent,
                        "text":f"المسار غير موجود: {path}"}
            sys.path.insert(0, os.path.expanduser("~/cyberlab_agent/lab_v4_dev/awareness"))
            from ts_reader import scan_project
            snapshot = scan_project(path)
            from lab_v4_dev.core.project_context import set_active_project
            set_active_project(path)
            lines = [f"تم قراءة المشروع: {path}"]
            lines.append(f"النوع: {snapshot['project_type']}")
            lines.append(f"الملفات: {snapshot['total_files']}")
            lines.append(f"نقاط الدخول: {', '.join(snapshot['entry_points'])}")
            lines.append(f"أهم الملفات:")
            for f in snapshot['critical_files'][:5]:
                lines.append(f"  🔴 {f}")
            return {"status":"success","intent":intent,
                    "text":"\n".join(lines)}

        # ─── Cyber Explain (v5.9.1-B) ───
        elif intent == Intent.CYBER_EXPLAIN:
            from lab_v4_dev.awareness.knowledge_base import search, store, hit
            cached = search(raw)
            if cached:
                hit(raw)
                self.context.current_subject = raw
                return {
                    "status": "success",
                    "intent": intent,
                    "source": "local_kb",
                    "text"  : f"[من الذاكرة المحلية]\n{cached}",
                }
            # ─── Hallucination Guard ───
            import re as _re
            _fake_pattern = _re.compile(r'[A-Z0-9_]{6,}', _re.UNICODE)
            _words = raw.replace("اشرح","").replace("شرح","").replace("ميزة","").replace("ما هو","").replace("ما هي","").strip()
            _has_fake = bool(_fake_pattern.search(_words))
            if _has_fake:
                _found_in_project = False
                try:
                    import json as _json
                    _mem_path = "lab_v4_dev/cache/project_memory.json"
                    with open(_mem_path, encoding="utf-8") as _f:
                        _mem = _json.load(_f)
                    _mem_str = _json.dumps(_mem, ensure_ascii=False).lower()
                    _found_in_project = _words.lower() in _mem_str
                except:
                    pass
                if not _found_in_project:
                    return {
                        "status": "success",
                        "intent": intent,
                        "source": "guard",
                "text": f"❌ '{_words}' غير موجودة في المشروع ولا في قاعدة المعرفة. لا أستطيع الإجابة بدون مصدر حقيقي.",
                    }
            # ─── كشف ملفات المشروع عبر project_index ───
            _project_file_code = None

            if target and str(target).endswith(".py"):
                _candidates = [
                    target,
                    os.path.join("lab_v4_dev", target),
                ]

                # البحث المباشر
                for _c in _candidates:
                    if os.path.exists(_c):
                        try:
                            _project_file_code = open(_c, encoding="utf-8").read()[:3000]
                        except:
                            pass
                        break

                # البحث عبر فهرس المشروع
                if not _project_file_code:
                    try:
                        import json as _json
                        from lab_v4_dev.awareness.project_index import _index_file

                        with open(_index_file(), encoding="utf-8") as _f:
                            _idx = _json.load(_f)

                        for _path, _info in _idx.items():
                            if os.path.basename(_path) == os.path.basename(target):
                                _real = _info.get("path", "")
                                if _real and os.path.exists(_real):
                                    _code = open(
                                        _real,
                                        encoding="utf-8"
                                    ).read()[:3000]

                                    _functions = _info.get("functions", [])
                                    _role = _info.get("role", "")

                                    _project_file_code = f"""
FILE PATH:
{_path}

PROJECT ROLE:
{_role}

KNOWN FUNCTIONS:
{_functions}

SOURCE CODE:
{_code}
"""
                                    target = _path
                                    break
                    except Exception:
                        pass

            # DNI-10: احتياطي — إن لم يُحدَّد target كملف صريح، استخدم آخر ملف
            # من سياق السلسلة (current_file المحقون من task_chain.py أو الخطوات السابقة)
            if not _project_file_code and getattr(self.context, "current_file", None):
                _cf = self.context.current_file
                for _c in [_cf, os.path.join("lab_v4_dev", _cf)]:
                    if os.path.exists(_c):
                        try:
                            _project_file_code = open(_c, encoding="utf-8").read()[:3000]
                            target = _c
                        except Exception:
                            pass
                        break

            # ─── البصمة الشخصية ───
            try:
                from lab_v4_dev.user_data.profile_loader import load_profile
                _profile = load_profile()
                _style = _profile.get("explanation_style", {})
            except:
                _style = {}
            _instructions = []
            if _style.get("step_by_step", True):
                _instructions.append("اشرح خطوة بخطوة مرقمة")
            if _style.get("show_risks", True):
                _instructions.append("اذكر المخاطر والتداعيات دائماً")
            if _style.get("examples_required", True):
                _instructions.append("أعطِ مثالاً عملياً (كود أو سيناريو)")
            if _style.get("show_reasoning", True):
                _instructions.append("وضح سبب كل خطوة")
            _extra = "\n".join(f"- {i}" for i in _instructions)

            if _project_file_code:
                system = f"""أنت مهندس برمجيات خبير يحلل ملفات مشروع Python.

مهمتك تحليل الملف الموجود أدناه فقط.
ممنوع:
- اختراع دوال غير موجودة
- افتراض مكتبات أو ملفات غير ظاهرة
- إعطاء شرح عام عن اسم الملف فقط

اتبع هذا الترتيب:
1. وظيفة الملف حسب الكود الحقيقي.
2. الدوال الموجودة فعلياً فقط.
3. العلاقات مع المشروع إذا ظهرت من الكود.
4. ملخص قصير.

إذا لم تجد معلومة في الكود قل: غير موجود في الملف.


قواعد الشرح الصارمة:
- اعتمد فقط على المسار والـ metadata والكود الحقيقي.
- لا تستخدم كلمات مثل: يبدو، قد يكون، ربما.
- لا تستنتج ملفات أو علاقات غير موجودة في البيانات.
- لا تضف مخاطر أو هجمات أو أمثلة خارج الملف.
- إذا لم تكن العلاقة موجودة في الكود قل: غير موجود في البيانات المتاحة.
الكود الحقيقي:
{_project_file_code}"""
            else:
                system = f"""أنت محلل كود Python في مشروع CyberLab Agent.

قواعد صارمة:
- اعتمد فقط على المسار والـ metadata والكود الحقيقي المعطى.
- لا تخترع دوال أو ملفات أو علاقات غير موجودة.
- لا تضف أمثلة هجوم أو مخاطر أمنية عامة.
- لا تستخدم كلمات: يبدو، قد يكون، ربما.
- إذا لم توجد معلومة في الكود قل: غير موجود في الملف.

اتبع الترتيب:
1. وظيفة الملف حسب الكود الحقيقي.
2. الدوال الموجودة فعلياً فقط.
3. العلاقات مع المشروع إذا ظهرت من الكود.
4. ملخص قصير.

الكود الحقيقي:
{_project_file_code}"""
            result = ask(
                raw,
                system=system,
                max_tokens=2000
            )
            answer = result.get("text","لم أتمكن من الإجابة")
            if result.get("status") != "success":
                answer = f"LLM ERROR DEBUG: {result}"
            # ─── حفظ الموضوع في السياق ───
            if result.get("status") == "success":
                self.context.current_subject = raw
            return {
                "status"       : result.get("status","failed"),
                "intent"       : intent,
                "source"       : get_active_provider(),
                "text"         : answer,
                "pending_save" : raw if result.get("status") == "success" else None,
                "save_prompt"  : "💾 هل تحفظ هذا الشرح في الذاكرة المحلية؟ (نعم / لا / تجاوز)",
            }

        # ─── Entry Point Query (v5.2.0 Project Reader) ───
        elif intent == Intent.ENTRY_POINT_QUERY:
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
        elif intent == Intent.DEPENDENTS_QUERY:
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
        elif intent == Intent.DEPENDENCIES:
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
        elif intent == Intent.IMPACT_CHAIN_QUERY:
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

        elif intent == Intent.CRITICALITY_QUERY:
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


        elif intent == Intent.FILE_IMPACT:
            import re as _re2
            stop = ["ما","تاثير","تعديل","ماذا","يحدث","لو","عدلت","على","في"]
            words = [w for w in raw.split() if w not in stop and len(w) > 2]
            q = words[-1] if words else target or raw
            from lab_v4_dev.core.project_context import get_active_project, CYBERLAB_ROOT
            _active = get_active_project()
            _is_external = not _active.root.startswith(CYBERLAB_ROOT)
            if _is_external:
                import json as _j
                try:
                    _g = _j.load(open("workspace/external_index/dependency_graph.json", encoding="utf-8"))
                    _imp = _g.get("imports", {})
                    _rev = _g.get("reverse_imports", {})
                    _matches = [k for k in list(_imp.keys()) + list(_rev.keys()) if q in k]
                    _key = _matches[0] if _matches else q
                    _imported_by = _rev.get(_key, [])
                    _imports = _imp.get(_key, [])
                    _risk = "high" if len(_imported_by) >= 3 else "medium" if len(_imported_by) >= 1 else "low"
                    impact = {"file": _key, "imports": _imports, "imported_by": _imported_by, "risk": _risk}
                except Exception as _e:
                    impact = {"file": q, "imports": [], "imported_by": [], "risk": "unknown"}
            else:
                from lab_v4_dev.awareness.dependency_map import get_impact
                if not os.path.exists("project_data/dependency_map.json"):
                    from lab_v4_dev.awareness.dependency_map import save_map
                    save_map()
                impact = get_impact(q)
            risk_icon = "🔴" if impact["risk"]=="high" else "🟡" if impact["risk"]=="medium" else "🟢"
            if not isinstance(impact, dict):
                impact = {}
            imports     = impact.get("imports", [])
            imported_by = impact.get("imported_by", [])
            lines = [
                f"تأثير تعديل: {impact.get('file', q)}",
                f"الخطورة: {risk_icon} {impact.get('risk','unknown')}",
                f"يستورد من: {', '.join(imports[:3]) or 'لا شيء'}",
                f"يستخدمه  : {', '.join(imported_by[:3]) or 'لا أحد'}",
            ]
            if target:
                self._impact_analyzed.add(target)
            return {"status":"success","intent":intent,
                    "text":"\n".join(lines)}

        # ─── Project Timeline ───
        elif intent == Intent.PROJECT_TIMELINE:
            from lab_v4_dev.data.project_timeline import (
                init_timeline, get_full_history, get_version_events
            )
            init_timeline()
            # هل يسأل عن إصدار محدد؟
            ver = self.context.current_version
            import re
            m = re.search(r"v?4\.\d", raw)
            if m:
                ver = m.group(0) if m.group(0).startswith("v") else "v"+m.group(0)
            if ver:
                events = get_version_events(ver)
                text = f"أحداث {ver}:\n"
                text += "\n".join(f"  - {e['event']}" for e in events) or "لا توجد أحداث"
            else:
                text = get_full_history()
            return {"status":"success","intent":intent,"text":text}

        # ─── Session Restore ───
        elif intent == Intent.SESSION_RESTORE:
            from lab_v4_dev.memory.session_state import load_session
            s = load_session()
            if not s:
                return {"status":"success","intent":intent,
                        "text":"لا توجد جلسة سابقة محفوظة"}
            lines = [
                "=== آخر جلسة محفوظة ===",
                f"التاريخ  : {s.get('timestamp','?')[:16]}",
                f"الهدف    : {s.get('active_goal','?')}",
                f"الخطوة   : {s.get('next_step','?')}",
                f"الملفات  : {', '.join(s.get('last_files',[])) or 'لا شيء'}",
                "",
                "💡 للسياق الكامل والتفصيلي اكتب: سياق العمل",
            ]
            return {"status":"success","intent":intent,
                    "text":"\n".join(lines)}

        # ─── Session Save ───
        elif intent == Intent.SESSION_SAVE:
            from lab_v4_dev.memory.session_state import save_session
            from lab_v4_dev.data.project_timeline import add_event
            s = save_session(
                active_goal = self.context.current_subject or "عمل جاري",
                next_step   = (f"استكمال: {self.context.current_subject}" if self.context.current_subject else "غير محددة"),
                last_files  = [self.context.current_file] if self.context.current_file else [],
                version     = self.agent._meta.get_version()
            )
            add_event(self.agent._meta.get_version(), f"Session saved: {s['active_goal']}")
            return {"status":"success","intent":intent,
                    "text":f"تم حفظ الجلسة\nالهدف: {s['active_goal']}\nID: {s['session_id']}"}

        # ─── Code Engine ───
        elif intent == Intent.GENERATE_CODE:
            from lab_v4_dev.core.code_engine import generate_code
            # نمرر raw دائماً لأنه يحتوي الوصف الكامل
            result = generate_code(raw)
            if result["status"] != "success":
                return {"status":"failed","intent":intent,
                        "text":"فشل في كتابة الكود"}
            self.context.current_file = result["saved_to"]
            self.context.current_subject = f"كتابة سكريبت: {raw[:60]}"
            return {
                "status"     : "success",
                "intent"     : intent,
                "text"       : result["explanation"][:600],
                "code"       : result["code"],
                "saved_to"   : result["saved_to"],
            }

        elif intent == Intent.ANALYZE_CODE:
            from lab_v4_dev.core.code_engine import analyze_code
            code_text = self.context.last_result.get("code","") if self.context.last_result else ""
            # إذا لم يحدد المستخدم ملفاً ولا يوجد كود سابق → طلب توضيح
            vague = ["هذا الملف","الملف","الكود","هذا","هذا الكود","حلل"]
            if not code_text and not target and any(v == raw.strip() for v in vague):
                return {"status":"needs_clarification","intent":intent,
                        "text":"أي ملف تريد تحليله؟ اكتب اسم الملف أو مساره."}
            if not code_text and target:
                # قراءة ملف محدد
                try:
                    full = os.path.expanduser(target)
                    code_text = open(full, encoding="utf-8", errors="ignore").read()[:3000]
                except:
                    return {"status":"failed","text":f"لا يمكن قراءة: {target}"}
            if not code_text:
                # لا كود محدد → اقرأ الملفات الحرجة فعلياً
                memory = load_memory()
                critical = [c["file"] for c in memory.get("critical_files",[])][:4]
                if not critical:
                    critical = ["lab_v4_dev/core/orchestrator.py","lab_v4_dev/core/agent.py"]
                parts = []
                for cf in critical:
                    try:
                        fp = os.path.expanduser(f"~/cyberlab_agent/{cf}")
                        content = open(fp, encoding="utf-8", errors="ignore").read()[:800]
                        parts.append("=== " + cf + " ===\n" + content)
                    except:
                        pass
                code_text = "\n\n".join(parts)
            prompt = f"أنت خبير أمن سيبراني وبرمجة. حلل الكود التالي وأجب على: {raw}\n\nالكود:\n{code_text}"
            result = ask(prompt, max_tokens=600)
            text = result.get("text","")
            if text:
                from lab_v4_dev.intent.response_cache import save as rcache_save
                rcache_save(str(intent), target or "", text)
            # ─── تسجيل الملف كمحلل ───
            if target and result.get("status") == "success":
                self._analyzed_files.add(target)
            # ─── حفظ الموضوع في السياق ───
            if text and result.get("status") == "success":
                self.context.current_subject = raw
            return {
                "status" : result.get("status","success"),
                "intent" : intent,
                "source" : result.get("provider_used", get_active_provider()),
                "text"   : text,
            }

        elif intent == Intent.MODIFY_CODE:
            from lab_v4_dev.core.symbol_resolver import resolve as sym_resolve
            from lab_v4_dev.core.surgical_editor import extract_symbol, patch_symbol
            from lab_v4_dev.core.code_engine import modify_code

            words = raw.strip().split()
            if len(words) < 4:
                return {"status":"needs_target","intent":intent,
                        "text":"\u0645\u0627\u0630\u0627 \u062a\u0631\u064a\u062f \u0623\u0646 \u0623\u0639\u062f\u0644\u061f"}

            resolved = sym_resolve(raw, target or "")
            if not resolved["found"]:
                return {"status":"needs_target","intent":intent,
                        "text":"\u0644\u0645 \u0623\u062c\u062f \u0627\u0644\u0645\u0644\u0641 \u0623\u0648 \u0627\u0644\u062f\u0627\u0644\u0629"}

            fp = resolved["file"]
            symbol = resolved["symbol"]

            if symbol:
                sym_data = extract_symbol(fp, symbol)
                code_text = sym_data.get("code", "")
                is_surgical = bool(code_text)
            else:
                try:
                    code_text = open(fp, encoding="utf-8", errors="ignore").read()
                except:
                    return {"status":"failed","intent":intent,"text":"\u0644\u0627 \u064a\u0645\u0643\u0646 \u0642\u0631\u0627\u0621\u0629 \u0627\u0644\u0645\u0644\u0641"}
                is_surgical = False

            if not code_text:
                return {"status":"failed","intent":intent,"text":"\u0644\u0627 \u064a\u0648\u062c\u062f \u0643\u0648\u062f"}

            result = modify_code(code_text, raw)
            if result["status"] != "success" or not result.get("code"):
                return {"status":result["status"],"intent":intent,
                        "text":result.get("text",result.get("explanation",""))}

            with open(fp, encoding="utf-8") as _vf:
                _orig_source = _vf.read()

            if is_surgical:
                from lab_v4_dev.core.surgical_editor import clean_llm_output
                clean_code = clean_llm_output(result["code"], symbol)
                final_code = patch_symbol(_orig_source, symbol,
                                          clean_code,
                                          sym_data["start_line"],
                                          sym_data["end_line"])
            else:
                final_code = result["code"]

            # تحقق من صحة الـ patch بعد الدمج
            from lab_v4_dev.core.surgical_editor import validate_patch
            _vcheck = validate_patch(_orig_source, final_code)
            if not _vcheck["ok"]:
                return {"status":"failed","intent":intent,
                        "text":"\u274c \u063a\u064a\u0631 \u0622\u0645\u0646: " + str(_vcheck)}

            try:
                from lab_v4_dev.executor.safe_pipeline import SafePipeline
                _db = self.agent.db
                if _db.conn is None: _db.connect()
                pipeline = SafePipeline(_db)
                plan = {"files": [fp], "reason": raw}
                pipe_result = pipeline.execute(plan, {fp: final_code})
                mode = "surgical" if is_surgical else "full"
                if pipe_result.get("status") == "success":
                    return {"status":"success","intent":intent,
                            "text":"\u2705 [" + mode + "] " + (symbol or fp.split("/")[-1])}
                else:
                    return {"status":"failed","intent":intent,
                            "text":"\u274c " + str(pipe_result.get("reason",""))}
            except Exception as e:
                return {"status":"failed","intent":intent,"text":str(e)}

        elif intent == Intent.LIST_SCRIPTS:

            scripts = []
            for folder in ["scripts","modified","analysis"]:
                path = os.path.join("workspace", folder)
                if os.path.exists(path):
                    for f in os.listdir(path):
                        scripts.append(f"{folder}/{f}")
            if not scripts:
                return {"status":"success","intent":intent,
                        "text":"لا توجد سكريبتات محفوظة بعد"}
            text = "السكريبتات المحفوظة:\n" + "\n".join(f"  📄 {s}" for s in scripts)
            return {"status":"success","intent":intent,"text":text}

        # ─── Sandbox Executor ───
        elif intent == Intent.RUN_SCRIPT:
            from lab_v4_dev.core.sandbox_executor import run_code

            # استخرج اسم الملف
            scripts = sorted([f for f in os.listdir("workspace/scripts") if f.endswith(".py")], key=lambda x: os.path.getmtime(f"workspace/scripts/{x}"), reverse=True) if os.path.exists("workspace/scripts") else []
            if not scripts:
                return {"status":"failed","intent":intent,"text":"لا توجد سكريبتات محفوظة"}
            # إذا ذكر اسم محدد استخدمه
            target_script = None
            for s in scripts:
                if s in raw:
                    target_script = f"workspace/scripts/{s}"
                    break
            # استخدم آخر سكريبت تم كتابته في هذه الجلسة
            if not target_script and self.context.last_result:
                saved = self.context.last_result.get("saved_to","")
                if saved and os.path.exists(saved):
                    target_script = saved
            # آخر ملف في المجلد
            if not target_script:
                target_script = f"workspace/scripts/{scripts[0]}"
            r = run_code(target_script, timeout=10)
            if r["status"] == "success":
                meta = f"⏱ {r.get('duration','?')}s | exit: {r.get('exit_code',0)}"
                return {
                    "status": "success", "intent": intent,
                    "text"  : f"✅ {target_script}\n{meta}\n\n{r.get('output','لا يوجد output')}",
                }
            else:
                meta = f"⏱ {r.get('duration','?')}s | exit: {r.get('exit_code','?')}"
                return {
                    "status": "error", "intent": intent,
                    "text"  : f"❌ {target_script}\n{meta}\n{r.get('error','')}\nتقرير: {r.get('report','')}",
                }

        elif intent == Intent.ERROR_REPORT:
            from lab_v4_dev.core.sandbox_executor import list_error_reports
            reports = list_error_reports()
            if not reports:
                return {"status":"success","intent":intent,"text":"لا توجد أخطاء مسجلة ✅"}
            lines = ["=== سجل الأخطاء ==="]
            for r in reports[-5:]:
                approved = "✅" if r["approved"] else "⏳"
                lines.append(f"{approved} {r['file']}")
                lines.append(f"   {r['error'][:60]}")
            return {"status":"success","intent":intent,"text":"\n".join(lines)}

        # ─── Dry Run ───
        elif intent == Intent.DRY_RUN:
            from lab_v4_dev.core.sandbox_executor import dry_run

            scripts = sorted(
                [f for f in os.listdir("workspace/scripts") if f.endswith(".py")],
                key=lambda x: os.path.getmtime(f"workspace/scripts/{x}"),
                reverse=True
            ) if os.path.exists("workspace/scripts") else []
            if not scripts:
                return {"status":"failed","intent":intent,"text":"لا توجد سكريبتات"}
            last = f"workspace/scripts/{scripts[0]}"
            r    = dry_run(last)
            return {"status":"success","intent":intent,
                    "text":f"فحص: {last}\n{r['message'] if r['status']=='ok' else r['error']}"}

        # ─── Run History ───
        elif intent == Intent.RUN_HISTORY:
            from lab_v4_dev.core.execution_history import get_history
            history = get_history(10)
            if not history:
                return {"status":"success","intent":intent,"text":"لا يوجد تاريخ تشغيل بعد"}
            lines = ["=== سجل التشغيل ==="]
            for r in history[:5]:
                icon = "✅" if r["status"]=="success" else "❌"
                lines.append(f"{icon} {r['script'].split('/')[-1]} — {r['duration']}s")
            return {"status":"success","intent":intent,"text":"\n".join(lines)}

        # ─── Repair Engine ───
        elif intent == Intent.REPAIR_ANALYZE:
            from lab_v4_dev.core.repair.error_reader import get_latest_error
            from lab_v4_dev.core.repair.error_analyzer import analyze
            from lab_v4_dev.core.repair.fix_generator import generate_fix
            from lab_v4_dev.core.repair.diff_approval import show_fix_proposal, save_pending_fix
            error = get_latest_error()
            if not error or not error.get("message"):
                return {"status":"success","intent":intent,
                        "text":"لا توجد أخطاء مسجلة ✅"}
            analysis = analyze(error)
            if not analysis.get("fixable", False):
                return {"status":"success","intent":intent,
                        "text":f"الخطأ: {error.get('message','')}\nيحتاج مراجعة يدوية"}
            fix      = generate_fix(error, analysis)
            proposal = show_fix_proposal(fix, error)
            path     = save_pending_fix(error.get("file",""), fix, error, analysis)
            self.context.last_result = {"pending_path": path, "fix": fix}
            return {"status":"success","intent":intent,"text":proposal}

        elif intent == Intent.REPAIR_APPROVE:
            from lab_v4_dev.core.repair.diff_approval import apply_fix, list_pending
            last = self.context.last_result or {}
            pending_path = last.get("pending_path","")
            if not pending_path:
                pending = list_pending()
                if pending:
        
                    pending_path = os.path.join("workspace/pending_fixes", pending[0]["file"])
            if not pending_path:
                return {"status":"failed","intent":intent,
                        "text":"لا يوجد إصلاح معلق"}
            result = apply_fix(pending_path)
            return {"status":result["status"],"intent":intent,
                    "text":f"{'✅' if result['status']=='success' else '❌'} {result['message']}"}

        elif intent == Intent.REPAIR_REJECT:
            self.context.last_result = None
            return {"status":"success","intent":intent,
                    "text":"تم رفض الإصلاح — لم يتم تعديل أي شيء"}

        elif intent == Intent.PENDING_FIXES:
            from lab_v4_dev.core.repair.diff_approval import list_pending
            pending = list_pending()
            if not pending:
                return {"status":"success","intent":intent,
                        "text":"لا توجد إصلاحات معلقة ✅"}
            lines = ["=== الإصلاحات المعلقة ==="]
            for p in pending:
                lines.append(f"⏳ {p['fix']}")
            return {"status":"success","intent":intent,"text":"\n".join(lines)}

        # ─── Switch Project ───
        elif intent == Intent.SWITCH_PROJECT:
            from lab_v4_dev.core.project_context import (
                get_active_project, set_active_project
            )
            # استخرج المسار من النص
            words = raw.split()
            path = None
            for w in words:
                if "/" in w or w in ["~", "."]:
                    path = w
            if not path:
                proj = get_active_project()
                return {"status":"success","intent":intent,
                        "text": f"المشروع النشط حالياً: {proj.name} ({proj.root})"}
            r = set_active_project(path)
            if r["status"] != "success":
                return {"status":"failed","intent":intent,"text":r["message"]}
            p = r["project"]
            # بناء فهرس المشروع الجديد تلقائياً (project_index + dependency_graph)
            try:
                from lab_v4_dev.core.project_context import project_index_dir
                import os as _os
                proj_root = r["project"]["root"]
                idx_dir = project_index_dir(proj_root)
                _os.makedirs(idx_dir, exist_ok=True)
                # اكتشاف نوع المشروع: Python أم TypeScript
                has_py = any(f.endswith(".py") for _, _, fs in _os.walk(proj_root)
                             for f in fs if "node_modules" not in _ and ".git" not in _)
                has_ts = _os.path.exists(_os.path.join(proj_root, "package.json"))
                if has_ts and not has_py:
                    import sys as _sys
                    _sys.path.insert(0, _os.path.expanduser(
                        "~/cyberlab_agent/lab_v4_dev/awareness"))
                    from ts_reader import scan_project as _scan_ts
                    snapshot = _scan_ts(proj_root)
                    # نسخ مخرجات ts_reader إلى مجلد الفهرس الصحيح لهذا المشروع
                    import shutil as _shutil, json as _json
                    src_dir = _os.path.expanduser(
                        "~/cyberlab_agent/workspace/external_index")
                    for fname in ["project_index.json","dependency_graph.json",
                                  "project_snapshot.json"]:
                        sp = _os.path.join(src_dir, fname)
                        if _os.path.exists(sp):
                            _shutil.copy(sp, _os.path.join(idx_dir, fname))
                    # critical_files.json لا ينتجه ts_reader، نبنيه من snapshot
                    with open(_os.path.join(idx_dir,"critical_files.json"),"w",
                              encoding="utf-8") as cf:
                        _json.dump({"critical": snapshot.get("critical_files",[])},
                                   cf, ensure_ascii=False)
                    indexed = " (تم فهرسته كـ TypeScript ✅)"
                else:
                    from lab_v4_dev.awareness.project_index import save_index
                    from lab_v4_dev.awareness.project_reader import ProjectReader
                    reader = ProjectReader()
                    reader.scan_files()
                    reader.build_graph()
                    reader.generate_outputs()
                    save_index()
                    indexed = " (تم فهرسته ✅)"
            except Exception as e:
                indexed = f" (فشل الفهرسة: {e})"
            # حفظ سجل المشاريع — عبر project_knowledge
            try:
                from lab_v4_dev.awareness.project_knowledge import get_project_history, save_project_history
                hist = get_project_history()
                if not isinstance(hist, dict):
                    hist = {"last_project": None, "last_root": None, "history": []}
                entry = {"name": p["name"], "root": p["root"], "last_used": datetime.now().isoformat()[:16]}
                hist["last_project"] = p["name"]
                hist["last_root"] = p["root"]
                hist["history"] = [e for e in hist.get("history", []) if e.get("name") != p["name"]]
                hist["history"].insert(0, entry)
                hist["history"] = hist["history"][:10]
                save_project_history(hist)
            except: pass
            return {"status":"success","intent":intent,
                    "text": f"✅ تم التبديل إلى: {p['name']}\nالمسار: {p['root']}{indexed}"}

        # ─── Audit Log ───
        elif intent == Intent.AUDIT_LOG:
            from lab_v4_dev.core.safe_io import get_audit_log
            events = get_audit_log(10)
            if not events:
                return {"status":"success","intent":intent,
                        "text":"لا توجد عمليات كتابة مسجلة بعد ✅"}
            lines = ["=== سجل العمليات (آخر 10) ==="]
            for e in events:
                status_icon = "✅" if e.get("status")=="success" else "❌"
                ts = e.get("timestamp","")[:16]
                lines.append(f"{status_icon} {ts} | {e.get('path','')}")
                if e.get("reason"):
                    lines.append(f"    سبب: {e['reason']}")
                if e.get("backup"):
                    lines.append(f"    نسخة احتياطية: {e['backup']}")
            return {"status":"success","intent":intent,"text":"\n".join(lines)}

        # ─── Save/Skip Knowledge Base ───
        elif intent == Intent.SAVE_KB:
            from lab_v4_dev.awareness.knowledge_base import store
            pending = getattr(self.context, "pending_save", None)
            last = self.context.last_result or {}
            topic = pending or last.get("pending_save")
            answer = last.get("text", "")
            if topic and answer:
                store(topic, answer)
                self.context.pending_save = None
                return {"status":"success","intent":intent,
                        "text":"✅ تم الحفظ في الذاكرة المحلية"}
            return {"status":"success","intent":intent,
                    "text":"⚠️ لا يوجد شرح معلق للحفظ"}

        elif intent == Intent.SKIP_KB:
            self.context.pending_save = None
            return {"status":"success","intent":intent,
                    "text":"⏭️ تم التجاوز — لن يُحفظ هذا الشرح"}

        # ─── Security Log (v5.6) ───
        elif intent == Intent.SECURITY_LOG:
            from lab_v4_dev.core.security_guard import get_security_log
            events = get_security_log(20)
            if not events:
                return {"status":"success","intent":intent,
                        "text":"✅ لا توجد تهديدات مسجلة"}
            lines = ["=== سجل الأمان ==="]
            for e in events:
                ts = e.get("timestamp","")[:16]
                lines.append(f"⚠️ {ts} | {e.get('type','')} | {e.get('value','')[:50]}")
                lines.append(f"    تطابق: {e.get('matched','')}")
            return {"status":"success","intent":intent,"text":"\n".join(lines)}

        # ─── Clean Device (v5.8) ───
        elif intent == Intent.CLEAN_DEVICE:
            from lab_v4_dev.core.cleaner import run_full_clean
            result = run_full_clean()
            lines = ["=== تنظيف الهاتف ==="]
            lines.append(f"📦 المساحة قبل : {result['before_mb']} MB")
            lines.append(f"📦 المساحة بعد : {result['after_mb']} MB")
            lines.append(f"🗑️ تم تحرير   : {result['freed_mb']} MB ({result['freed_kb']} KB)")
            lines.append("─── التفاصيل ───")
            for d in result["details"]:
                lines.append(f"  {d['type']}: حذف {d['removed']} عنصر — {d['size_kb']} KB")
            return {"status":"success","intent":intent,"text":"\n".join(lines)}

        # ─── Work Context Report ───
        elif intent == Intent.WORK_CONTEXT:
            lines = ["=== سياق العمل ==="]

            # 1. آخر FINAL_REPORT.md
            rel_dir = "releases"
            latest_report = None
            latest_ver = None
            if os.path.exists(rel_dir):
                for d in sorted(os.listdir(rel_dir), reverse=True):
                    p = os.path.join(rel_dir, d, "FINAL_REPORT.md")
                    if os.path.exists(p):
                        latest_report = p
                        latest_ver = d
                        break
            if latest_report:
                with open(latest_report, "r", encoding="utf-8") as f:
                    content = f.read()
                lines.append(f"\n📄 آخر تقرير ({latest_ver}):")
                lines.append(content[:1200])
            else:
                lines.append("\nلا يوجد تقرير محفوظ")

            # 2. آخر المهام
            tasks = self.agent.memory.recent_tasks(5)
            if tasks:
                lines.append("\n📋 آخر المهام:")
                for t in tasks:
                    lines.append(f"  [{t['status']}] {t['intent'][:50]}")

            # 3. الإصلاحات المعلقة
            from lab_v4_dev.core.repair.diff_approval import list_pending
            pending = list_pending()
            if pending:
                lines.append(f"\n⏳ إصلاحات معلقة ({len(pending)}):")
                for p in pending:
                    lines.append(f"  - {p['fix']}")

            return {"status":"success","intent":intent,"text":"\n".join(lines)}

        # ─── System Status Report ───
        elif intent == Intent.SYSTEM_STATUS:
            import subprocess
            script = os.path.join(os.path.expanduser("~/cyberlab_agent"), "project_status.py")
            try:
                r = subprocess.run(["python3", script], capture_output=True, text=True, timeout=15)
                output = r.stdout or r.stderr or "لا يوجد ناتج"
            except Exception as e:
                output = f"فشل تشغيل التقرير: {e}"
            return {"status":"success","intent":intent,"text":output}


        # ─── Delete File ───
        elif intent == Intent.DELETE_FILE:
            try:
                from lab_v4_dev.core.safe_io import safe_delete

                target_path = target or self.context.current_file

                if not target_path:
                    return {
                        "status": "failed",
                        "intent": intent,
                        "message": "لم يتم تحديد الملف"
                    }

                result = safe_delete(target_path, "user request")

                return {
                    "status": result.get("status"),
                    "intent": intent,
                    "text": f"تم حذف {target_path}",
                    "backup": result.get("backup"),
                    "snapshot": result.get("snapshot"),
                }

            except Exception as e:
                return {
                    "status": "failed",
                    "intent": intent,
                    "message": str(e)
                }

        # ─── fallback ───
        else:
            return {
                "status"  : "unsupported",
                "intent"  : intent,
                "message" : f"لم أفهم الأمر: {raw[:50]}",
                "executed": False,
            }

    def get_last(self)    -> dict: return self.history[-1] if self.history else {}
    def get_history(self) -> list: return self.history

    def summary(self) -> dict:
        intents  = {}
        statuses = {}
        for h in self.history:
            i = h.get("intent", "?")
            s = h.get("status", "?")
            intents[i]  = intents.get(i, 0) + 1
            statuses[s] = statuses.get(s, 0) + 1
        return {
            "total"   : len(self.history),
            "phase"   : self.phase,
            "intents" : intents,
            "statuses": statuses,
        }
