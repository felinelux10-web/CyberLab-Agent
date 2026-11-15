"""Cross-cutting Orchestrator policy gates and response profile shaping."""

def pre_handler_policy(orchestrator, intent, target, raw) -> dict | None:
    """Fail-closed profile and impact gates before effectful handlers run."""
    try:
        from lab_v4_dev.user_data.profile_loader import load_profile
        profile = load_profile()
    except Exception:
        profile = {}

    if not isinstance(profile, dict):
        profile = {}
    engineering = profile.get("engineering_style") or {}
    trust = profile.get("trust_policy") or {}
    target_path = str(target or "").strip()
    current_file = str(getattr(orchestrator.context, "current_file", None) or "").strip()
    last_result = getattr(orchestrator.context, "last_result", None) or {}

    # The profile's conservative defaults remain in force when it is
    # missing or unreadable; a failed read must never disable safeguards.
    allow_guessing = bool(trust.get("allow_guessing", False))

    if not allow_guessing:
        if intent in (Intent.MODIFY_CODE, Intent.DELETE_FILE) and not target_path and current_file:
            return {
                "status": "needs_clarification",
                "intent": intent,
                "source": "profile_no_implicit_target",
                "executed": False,
                "text": "حدّد الملف صراحة أو أشر إليه بوضوح؛ لن أستخدم آخر ملف تلقائيًا.",
            }
        if intent == Intent.REPAIR_APPROVE:
            pending_path = (
                last_result.get("pending_path", "")
                if isinstance(last_result, dict) else ""
            )
            if not pending_path and not target_path:
                return {
                    "status": "needs_clarification",
                    "intent": intent,
                    "source": "profile_no_implicit_repair_selection",
                    "executed": False,
                    "text": "حدّد اقتراح الإصلاح الذي تريد اعتماده؛ لن أختار أول إصلاح معلق تلقائيًا.",
                }

    if intent == Intent.MODIFY_CODE and engineering.get("analyze_before_modify", True):
        effective_target = target_path or current_file
        if not effective_target:
            return {
                "status": "needs_target",
                "intent": intent,
                "source": "profile_analysis_target_required",
                "executed": False,
                "text": "يلزم تحديد الملف وتحليله قبل تعديله.",
            }
        analyzed = getattr(self, "_analyzed_files", set())
        if effective_target not in analyzed:
            return {
                "status": "blocked",
                "intent": intent,
                "source": "profile_analysis_required",
                "executed": False,
                "text": "يجب تحليل الملف أولًا قبل التعديل: " + effective_target,
            }

    if (
        intent in (Intent.MODIFY_CODE, Intent.REPAIR_APPROVE)
        and engineering.get("require_impact_analysis", True)
    ):
        impact_target = target_path or current_file
        if intent == Intent.REPAIR_APPROVE:
            pending_path = (
                last_result.get("pending_path", "")
                if isinstance(last_result, dict) else ""
            )
            if pending_path:
                try:
                    import json
                    with open(pending_path, encoding="utf-8") as handle:
                        pending_record = json.load(handle)
                    impact_target = str(pending_record.get("file") or impact_target).strip()
                except Exception as exc:
                    return {
                        "status": "blocked",
                        "intent": intent,
                        "source": "profile_impact_evidence_unavailable",
                        "executed": False,
                        "text": "تعذر قراءة ملف اقتراح الإصلاح للتحقق من أثره: " + str(exc),
                    }

        if not impact_target:
            return {
                "status": "blocked",
                "intent": intent,
                "source": "profile_impact_target_required",
                "executed": False,
                "text": "لا يمكن متابعة التعديل دون تحديد الملف وإجراء تحليل أثره.",
            }

        impact_cache = getattr(self, "_impact_analyzed", set())
        if impact_target not in impact_cache:
            try:
                from lab_v4_dev.awareness.dependency_map import get_impact
                impact = get_impact(impact_target)
            except Exception as exc:
                return {
                    "status": "blocked",
                    "intent": intent,
                    "source": "profile_impact_analysis_failed",
                    "executed": False,
                    "text": "تعذر إكمال تحليل أثر الملف؛ أُوقف التنفيذ: " + str(exc),
                }

            if not isinstance(impact, dict) or impact.get("risk") == "unknown":
                return {
                    "status": "blocked",
                    "intent": intent,
                    "source": "profile_impact_analysis_incomplete",
                    "executed": False,
                    "text": "لم تنتج خريطة الاعتماديات دليل أثر صالحًا للملف؛ أُوقف التنفيذ.",
                }
            impact_cache.add(impact_target)

    return None

def apply_profile(result: dict, intent: str) -> dict:
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
