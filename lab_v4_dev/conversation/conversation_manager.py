"""
Conversation Manager — Unified Conversation/Intent Routing.

Authority contract:

ModeDetector
    -> conversational shape only.

IntentParser
    -> canonical semantic resolver for the current text, without implicit
       persistent context.

Context
    -> enriches references/targets only.

ConversationManager
    -> authorizes context transitions before final resolution and chooses
       ONE execution owner.

Orchestrator
    -> sole execution owner for operational requests.

LLM
    -> conversational and evidence-backed knowledge responder for
       non-operational turns, including context-authorized project continuations.

Important:
FOLLOW_UP is a conversational MODE, not an automatic LLM route.
Explicit executable intents go to Orchestrator. A contextual project
continuation that was promoted to CYBER_EXPLAIN only because the active
branch is a PROJECT remains a knowledge-backed conversational response,
unless the current turn explicitly requests an operation.
"""

import re

from lab_v4_dev.conversation.mode_detector import detect_mode
from lab_v4_dev.conversation.assistant_style import format_response, single_question
from lab_v4_dev.conversation.local_response_engine import answer_local_social
from lab_v4_dev.conversation.unified_local_response import answer_local_response
from lab_v4_dev.conversation.semantic_contract import (
    CONTEXTUAL_TRANSITIONS,
    ContextTransition,
    build_semantic_request,
)
from lab_v4_dev.llm.prompt_builder import build_chat_prompt
from lab_v4_dev.llm.gateway import ask as gateway_ask
from lab_v4_dev.awareness.agent_self_knowledge import build_agent_self_knowledge
from lab_v4_dev.awareness.knowledge_retriever import (
    ProjectScope,
    QuestionClassifier,
    resolve_project_scope,
    retrieve_for_question,
)
from lab_v4_dev.intent.intent_parser import parse
from lab_v4_dev.intent.intents import Intent
from lab_v4_dev.nlu.context_resolver import is_incomplete
from lab_v4_dev.nlu.conversation_semantics import (
    is_social_act,
    is_style_act,
    normalize_text,
)


_AGENT_SELF_INTENTS = {
    Intent.AGENT_IDENTITY,
    Intent.AGENT_CAPABILITIES,
    Intent.AGENT_ARCHITECTURE,
    Intent.AGENT_EXECUTION_FLOW,
    Intent.AGENT_LIMITS,
}

_NON_EXECUTABLE_INTENTS = {
    Intent.UNCLEAR,
    Intent.PERSONAL_CHAT,
    Intent.UNSUPPORTED,
    Intent.HELP,
    *_AGENT_SELF_INTENTS,
    "unclear",
    "unsupported",
    "help",
}


class ConversationManager:

    def __init__(self, orchestrator, dialogue_memory=None, dni=None):
        self.orchestrator = orchestrator
        self.dialogue_memory = dialogue_memory
        self.dni = dni

    @staticmethod
    def _is_project_progress_request(text: str) -> bool:
        """Recognize project-state questions by combining intent cues, not a single keyword."""
        normalized = normalize_text(str(text or ""))
        status_cues = (
            "اين توقف", "اين وصل", "اين انتهي العمل", "حاله العمل",
            "حاله المشروع", "سياق العمل", "عن سياق العمل", "نفس سياق العمل",
            "في نفس سؤال", "نفس سؤال", "اكمل الشرح", "استكمل الشرح",
            "تابع الشرح", "تقدم العمل", "ما انجز", "ماذا انجز",
            "ما المتبقي", "الخطوه التاليه", "اخر خطوه",
            "where did we stop", "project status", "next step",
        )
        plan_cues = (
            "خطه العمل", "خطه تطوير", "الخطه القادمه", "ما الخطه",
            "ماهي الخطه", "ما هي خطه", "what is the plan", "project roadmap",
        )

        # Questions about what we were developing are project-progress
        # questions, not generic architecture questions. Require both a
        # project artefact (layer/function/module/file/feature) and a
        # collaborative development action so ordinary theory questions do
        # not become current-project lookups.
        development_entities = (
            "طبقه", "طبقات", "وظيفه", "وظائف", "وضائف", "وضيفه",
            "مكون", "مكونات", "وحده", "وحدات", "ميزه", "ميزات",
            "ملف", "ملفات", "مسار", "مسارات",
        )
        development_actions = (
            "كنا نطور", "كنا نعدل", "كنا نصلح", "كنا نعمل",
            "نحن نطور", "نحن نعدل", "نحن نصلح", "التي نطور",
            "التي نعمل", "التي نعدل", "نطورها", "نعدلها",
            "نعمل على", "نشتغل على",
        )
        development_inventory = (
            any(cue in normalized for cue in development_entities)
            and any(cue in normalized for cue in development_actions)
        )
        return (
            any(cue in normalized for cue in status_cues + plan_cues)
            or development_inventory
        )

    def _local_project_progress_answer(
        self,
        text: str,
        parsed: dict,
        context_entity: dict | None,
    ) -> dict | None:
        """Answer explicit project progress/plan questions from the local project-state record."""
        normalized_request = normalize_text(str(text or ""))
        explicitly_general_scope = any(marker in normalized_request for marker in (
            "بصفه عامه", "بشكل عام", "بصوره عامه", "عموما",
            "محادثه وديه", "دردشه وديه", "خارج بنية المشروع",
            "لا نتحدث عن مشروع", "ليس عن مشروع",
            "بلا علاقه بالمشروع", "not about cyberlab",
            "outside cyberlab", "general discussion",
        ))
        if (
            not self._is_project_progress_request(text)
            or explicitly_general_scope
        ):
            return None

        if self.dialogue_memory:
            get_active_context = getattr(
                self.dialogue_memory, "active_context_entity", None
            )
            active_context = get_active_context() if callable(get_active_context) else None
            active_is_project = (
                isinstance(active_context, dict)
                and str(active_context.get("entity_type") or "").upper() == "PROJECT"
            )
            passed_is_project = (
                isinstance(context_entity, dict)
                and (
                    str(context_entity.get("entity_type") or "").upper() == "PROJECT"
                    or str(context_entity.get("conversation_domain") or "").casefold() == "project"
                )
            )
            if active_is_project and not passed_is_project:
                # The project branch itself is the authorization anchor for
                # "what were we developing?" questions. Do not trust a fresh
                # generic/unknown lexical target over the active project owner.
                context_entity = active_context

        context_parts = [str(text or "")]
        if isinstance(parsed, dict):
            context_parts.extend((
                str(parsed.get("target") or ""),
                str(parsed.get("conversation_domain") or ""),
            ))
        if isinstance(context_entity, dict):
            context_parts.extend((
                str(context_entity.get("entity") or ""),
                str(context_entity.get("conversation_domain") or ""),
            ))
        scope_text = " ".join(part for part in context_parts if part)
        intent = (parsed or {}).get("intent")
        scope = resolve_project_scope(scope_text, intent=intent)
        # Preserve explicit external/generic/historical scope even when an
        # older project branch remains active in dialogue memory.
        if scope in {
            ProjectScope.EXTERNAL_PROJECT,
            ProjectScope.GENERIC_PROJECT,
            ProjectScope.HISTORICAL_PROJECT,
        }:
            return None
        parsed_domain = str(
            (parsed or {}).get("conversation_domain") or ""
        ).casefold()
        context_authorizes_project = (
            parsed_domain == "project"
            or (
                isinstance(context_entity, dict)
                and (
                    str(context_entity.get("conversation_domain") or "").casefold() == "project"
                    or str(context_entity.get("entity_type") or "").upper() == "PROJECT"
                )
            )
        )
        if scope != ProjectScope.CURRENT_PROJECT and context_authorizes_project:
            scope = ProjectScope.CURRENT_PROJECT
        if scope != ProjectScope.CURRENT_PROJECT:
            return None

        try:
            from lab_v4_dev.awareness.project_knowledge import get_project_state
            state = get_project_state()
        except Exception as exc:
            state = {}
            retrieval_error = type(exc).__name__
        else:
            retrieval_error = ""

        state = state if isinstance(state, dict) else {}

        def usable(value):
            if value is None:
                return False
            if isinstance(value, str):
                return value.strip().casefold() not in {"", "?", "unknown", "غير معروف", "غير متاح"}
            if isinstance(value, (list, tuple, set, dict)):
                return bool(value)
            return True

        lines = ["وفق سجل حالة المشروع المحلي:"]
        fields = (
            ("current_focus", "التركيز الحالي"),
            ("last_goal", "آخر هدف محفوظ"),
            ("last_step", "الخطوة التالية المسجلة"),
        )
        evidence_count = 0
        for key, label in fields:
            value = state.get(key)
            if usable(value):
                lines.append(f"- {label}: {value}")
                evidence_count += 1

        for key, label in (("active", "الأعمال النشطة"), ("planned", "الأعمال المخططة")):
            values = state.get(key)
            if usable(values):
                rendered = [str(item).strip() for item in values if str(item).strip()]
                if rendered:
                    lines.append(f"- {label}: " + "؛ ".join(rendered[:5]))
                    evidence_count += 1

        completed_count = state.get("completed_count")
        if isinstance(completed_count, int) and completed_count > 0:
            lines.append(f"- العناصر المكتملة المسجلة: {completed_count}")
            evidence_count += 1

        if not evidence_count:
            detail = (
                f" تعذر قراءة السجل بسبب {retrieval_error}."
                if retrieval_error else
                " السجل لا يحتوي على تركيز أو خطوة تالية أو عناصر عمل موثقة."
            )
            return {
                "status": "needs_clarification",
                "intent": intent or Intent.PERSONAL_CHAT,
                "source": "local_project_knowledge",
                "text": (
                    "حددت أن السؤال عن حالة مشروع CyberLab Agent، لكن لا توجد "
                    "بيانات محلية كافية لإثبات نقطة التوقف أو الخطة الحالية." + detail
                    + " لن أخمّن حالة العمل. يلزم تحديث roadmap.json أو session_state.json "
                    "بآخر خطوة مؤكدة."
                ),
                "executed": False,
            }

        lines.append(
            "هذه معلومات من سجل الحالة المحفوظ، وليست إثباتًا على حالة تشغيل لحظية. "
            "إذا كان السجل قديمًا فقد يحتاج إلى تحديث."
        )
        return {
            "status": "success",
            "intent": intent or Intent.PERSONAL_CHAT,
            "source": "local_project_knowledge",
            "text": "\n".join(lines),
            "project_state": state,
            "executed": False,
        }

    @staticmethod
    def _is_bare_confirmation(text: str) -> bool:
        return str(text).strip().casefold() in {
            "نعم", "أجل", "اجل", "بلى", "لا", "كلا",
            "yes", "no",
        }

    @staticmethod
    def _is_explicit_stop_request(text: str) -> bool:
        """Recognize direct conversational stop requests without invoking execution."""
        normalized = " ".join(str(text or "").casefold().split()).strip(" .!؟?")
        return normalized in {
            "توقف", "توقف عن العمل", "توقف عن الشرح", "توقف عن المتابعة",
            "كفى توقف", "stop", "stop working", "stop explaining",
        }

    @classmethod
    def _is_explicit_diagnostic_request(cls, text: str) -> bool:
        """Allow diagnostics only for a direct, unambiguous system request."""
        normalized = cls._normalize_transition_text(text).strip(" .!؟?")
        direct = (
            "شغل التشخيص", "تشغيل التشخيص", "شخص النظام", "شخّص النظام",
            "شخص صحة النظام", "شخّص صحة النظام", "افحص صحة النظام",
            "فحص صحة النظام", "تحقق من صحة النظام", "اختبر صحة النظام",
            "health check",
        )
        direct_question = {
            "هل النظام سليم", "هل النظام يعمل", "هل النظام يعمل بشكل سليم",
            "ما حالة النظام",
        }
        return normalized in direct_question or any(marker in normalized for marker in direct)

    @staticmethod
    def _explicit_dialogue_topic(text: str) -> str | None:
        """Extract the subject of an explicit independent dialogue opening."""
        import re

        value = str(text or "").strip()
        match = re.match(
            r"^\s*(?:دعنا|خلينا|هيا|لن)\s+"
            r"(?:نتحدث|نتكلم|نناقش|نتحاور)\s+(?:عن|حول)\s+"
            r"(.+?)\s*[.!؟?،]*\s*$",
            value,
            flags=re.IGNORECASE,
        )
        if not match:
            # A compact topic declaration ("موضوع الرسم والنحت") opens a
            # dialogue branch; it is not merely a noun phrase to explain anew.
            match = re.match(
                r"^\s*(?:موضوع|فكرة)\s+(?!السابق\b|السابقه\b|الرئيسي\b|الرئيسيه\b)(.+?)\s*[.!؟?،]*\s*$",
                value,
                flags=re.IGNORECASE,
            )
        if not match:
            # Natural dialogue commonly declares a subject as "عن موضوع X" or
            # simply "عن X". Exclude retrospective references so they remain
            # owned by the history/restore path.
            match = re.match(
                r"^\s*(?:مثلا\s+)?(?:عن|حول)\s+(?:موضوع\s+)?(.+?)\s*[.!؟?،]*\s*$",
                value,
                flags=re.IGNORECASE,
            )
            if match and any(marker in match.group(1).casefold() for marker in (
                "السابق", "قبل", "كنا", "نتحدث", "تحدثنا", "الموضوع الذي",
            )):
                match = None
        if not match:
            # A short noun list can be the continuation of a friendly topic,
            # not an instruction to execute or explain a new task.
            normalized = value.casefold()
            if any(marker in normalized for marker in ("فن", "رسم", "نحت", "نقش")) and not any(
                marker in normalized for marker in ("اشرح", "وضح", "نفذ", "شغل", "؟", "?")
            ):
                return value.strip(" \t\r\n.,،؛:!?؟")
        if not match:
            # Topic changes are often phrased as "let's move to X", not as
            # "let's talk about X". Treat the subject as dialogue unless a
            # later operational cue explicitly claims it.
            match = re.match(
                r"^\s*(?:حسنا\s+)?(?:دعنا|خلينا)?\s*(?:لننتقل|ننتقل|انتقل)\s+"
                r"(?:(?:الى|إلى)\s+|ل)(?:موضوع\s+)?(.+?)\s*[.!؟?،]*\s*$",
                value,
                flags=re.IGNORECASE,
            )
        if not match:
            return None
        subject = match.group(1).strip(" \t\r\n.,،؛:!?؟")
        subject = re.sub(r"^(?:مفهوم|موضوع|فكرة)\s+", "", subject).strip()
        return subject or None

    @staticmethod
    def _explicit_explanation_topic(text: str) -> str | None:
        """Extract an explicit explain/define request, not a resume reference."""
        import re

        value = str(text or "").strip()
        if any(marker in value.casefold() for marker in (
            "ارجع", "نرجع", "عد إلى", "عد الى", "اكمل", "أكمل",
            "استكمل", "تابع", "واصل", "continue", "resume",
        )):
            return None
        normalized_value = value.casefold()
        if any(marker in normalized_value for marker in (
            "عرف عن نفسك", "عرّف عن نفسك", "اشرح معمارية المشروع",
            "اشرح بنية المشروع", "اشرح بنية النظام",
        )):
            return None
        match = re.match(
            r"^\s*(?:اشرح|شرح|وضح|عرّف|عرف|explain|describe)\s+"
            r"(.+?)\s*[.!؟?،]*\s*$",
            value,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        subject = match.group(1).strip(" \t\r\n.,،؛:!?؟")
        subject = re.split(
            r"\s+(?=بالتفصيل|باختصار|بأسلوب(?:\s|$)|بصيغة(?:\s|$)|بشكل(?:\s|$)|أكاديمي(?:\s|$)|رسمي(?:\s|$)|ثم(?:\s|$)|وتوقف|توقف|و(?:\s|$))",
            subject,
            maxsplit=1,
        )[0].strip()
        # Short elaboration phrases are contextual references, not new topics.
        if subject.casefold().strip() in {
            "اكثر", "أكثر", "المزيد", "تفصيل اكثر", "تفصيل أكثر",
            "مزيد من التفاصيل", "more", "more detail", "further",
        }:
            return None
        normalized_subject = ConversationManager._normalize_transition_text(subject)
        if normalized_subject in {
            "هذا", "هذه", "ذلك", "تلك", "هذا الامر", "ذلك الامر",
            "لي هذا", "لي هذه", "عن هذا", "عن هذه",
        }:
            return None
        if any(marker in normalized_subject for marker in (
            "المشروع", "معماريه المشروع", "بنيه المشروع", "بنيه النظام",
        )):
            return None
        return subject or None

    def _pending_confirmation_intent(self, text: str):
        """Resolve bare confirmations only against an explicit pending operation."""
        if not self._is_bare_confirmation(text):
            return None
        context = getattr(self.orchestrator, "context", None)
        last_result = getattr(context, "last_result", None) if context else None
        last_result = last_result if isinstance(last_result, dict) else {}
        pending = last_result.get("pending_confirmation")
        if not pending and last_result.get("pending_save"):
            pending = {"kind": "save_kb"}
        if isinstance(pending, str):
            pending = {"kind": pending}
        if not isinstance(pending, dict):
            return None
        affirmative = str(text).strip().casefold() not in {"لا", "كلا", "no"}
        kind = pending.get("kind")
        if kind == "save_kb":
            return Intent.SAVE_KB if affirmative else Intent.SKIP_KB
        if kind == "resume":
            return Intent.RESUME if affirmative else Intent.CANCEL
        return None

    def _clear_unrelated_execution_file(self, transition, parsed):
        """Do not let an old execution file become a new generic question target."""
        if transition != ContextTransition.NEW_INDEPENDENT:
            return
        if (parsed or {}).get("intent") in {
            Intent.MODIFY_CODE,
            Intent.MODIFY_FILE,
            Intent.GENERATE_CODE,
        }:
            return
        context = getattr(self.orchestrator, "context", None)
        if context is not None:
            context.current_file = None

    @staticmethod
    def _is_fragmentary_turn(text: str) -> bool:
        """Reject isolated letters/unknown two-letter fragments before context inheritance."""
        normalized = normalize_text(str(text or ""))
        compact = "".join(
            char for char in normalized
            if char.isalnum() or "\u0600" <= char <= "\u06ff"
        ).strip()
        if not compact:
            return False
        if len(compact) == 1:
            return True
        if len(compact) != 2:
            return False
        # These are valid short Arabic words/particles; leave their normal
        # conversational and clarification routes intact.
        common_short_words = {
            "لا", "ما", "من", "في", "عن", "هل", "هو", "هي", "كم", "كل",
            "لم", "لن", "قد", "بل", "يا", "مع", "به", "له", "هم", "هن",
            "اي", "اذ", "ثم",
        }
        return compact not in common_short_words and all(
            "\u0600" <= char <= "\u06ff" for char in compact
        )

    @staticmethod
    def _is_new_dialogue_session_request(text: str) -> bool:
        """Recognize explicit natural-language requests to start an isolated dialogue."""
        normalized = " ".join(
            str(text or "").casefold()
            .replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
            .replace("ـ", "")
            .strip(" .,،؛:!?؟'()[]{}")
            .split()
        )
        exact = {
            "جلسة جديدة", "جلسه جديده", "new session", "ابدأ جلسة جديدة",
            "ابدا جلسه جديده", "ابدأ حوارا جديدا", "ابدا حوارا جديدا",
            "بدء جلسة جديدة", "بدء حوار جديد",
        }
        if normalized in exact:
            return True
        explicit_starts = (
            "اريد بدء جلسة حوار جديدة",
            "اريد بدء جلسه حوار جديده",
            "اريد بدء جلسة جديدة ومستقلة",
            "اريد بدء حوار جديد ومستقل",
            "ابدأ جلسة حوار جديدة",
            "ابدا جلسه حوار جديده",
            "انشئ جلسة حوار جديدة",
            "انشئ جلسه حوار جديده",
            "ابدأ جلسة جديدة ومستقلة",
            "ابدا جلسه جديده ومستقله",
        )
        if any(normalized.startswith(prefix) for prefix in explicit_starts):
            return True

        # Spoken examples and discourse-prefixed requests still express a real
        # session boundary ("قلت نبدا حوار ودي جديد مثلا"). Detect the semantic
        # combination rather than requiring the request to start with a template.
        tokens = set(normalized.split())
        has_dialogue_object = bool(tokens & {
            "جلسة", "جلسه", "حوار", "محادثة", "محادثه", "دردشة", "دردشه", "حديث",
        })
        has_new_marker = bool(tokens & {
            "جديد", "جديدة", "جديده", "جديدا", "مستقل", "مستقلة", "مستقله",
        }) or "من جديد" in normalized
        has_start_marker = bool(tokens & {
            "ابدأ", "ابدا", "نبدا", "نبدأ", "لنبدأ", "لنبدأ", "بدء",
            "انشئ", "انشاء", "خلينا", "نفتح", "نبدأ", "ننشئ",
        })
        return has_dialogue_object and has_new_marker and has_start_marker

    def process(self, user_input: str, *, _restore_context: dict | None = None) -> dict:
        # Session boundaries take precedence over pending clarifications and all
        # NLU/context resolution. A new dialogue must never inherit old state.
        if self._is_new_dialogue_session_request(user_input):
            reset = getattr(self.orchestrator, "reset_conversation_context", None)
            if callable(reset):
                reset()
            else:
                agent = getattr(self.orchestrator, "agent", None)
                reset = getattr(agent, "reset_conversation_context", None)
                if callable(reset):
                    reset()
            memory_reset = getattr(self.dialogue_memory, "reset", None)
            if callable(memory_reset):
                memory_reset()
            return {
                "status": "success",
                "intent": Intent.RESTART,
                "source": "conversation_manager",
                "text": "بدأت جلسة حوار جديدة ومستقلة. لم يتم إنشاء أو تنفيذ أي مهمة، ولم أستعد سياق الجلسة السابقة.",
                "executed": False,
            }

        selected_saved_session_id = None
        # Resolve saved-session ambiguity before NLU sees this turn.
        if self.dialogue_memory:
            state = getattr(self.dialogue_memory, "state", None)
            pending = getattr(state, "pending_clarification", None)
            if isinstance(pending, dict) and pending.get("kind") == "saved_session_choice":
                from lab_v4_dev.memory.session_state import resolve_saved_session_choice
                candidates = pending.get("candidates") or []
                selected_saved_session_id = resolve_saved_session_choice(user_input, candidates)
                if selected_saved_session_id:
                    state.pending_clarification = None
                else:
                    normalized_choice = self._normalize_transition_text(user_input)
                    refers_to_saved_session = any(marker in normalized_choice for marker in (
                        "جلسة", "جلسه", "ملخص", "ملخصات", "لخص", "تلخيص",
                        "تقرير", "استرجع", "استعد", "هذه", "التي عرضتها",
                        "اختصر", "اكمل", "الفن", "الرسم", "النحت", "النقش",
                    ))
                    if refers_to_saved_session:
                        lines = [
                            "لم أحدد جلسة واحدة بعد؛ لن أختار جلسة مختلفة بالتخمين.",
                            "اختر رقم الخيار الظاهر أو أرسل معرّف الجلسة:",
                        ]
                        for number, item in enumerate(candidates, 1):
                            title = str(item.get("title") or item.get("topic") or "جلسة بلا عنوان")
                            session_id = str(item.get("session_id") or "?")
                            lines.append(f"- الخيار {number}: {title} [{session_id}]")
                            if item.get("summary"):
                                lines.append(f"  الملخص: {item['summary']}")
                        return {
                            "status": "needs_clarification",
                            "intent": Intent.SESSION_RESTORE,
                            "source": "saved_session_selector",
                            "executed": False,
                            "text": "\n".join(lines),
                        }
                    state.pending_clarification = None

            # Preserve project-list ordering clarification behavior.
            pending = getattr(state, "pending_clarification", None)
            if isinstance(pending, dict) and pending.get("kind") == "project_order":
                choice = str(user_input).strip()
                orders = {
                    "1": "حسب ترتيب العمل عليها",
                    "2": "أبجديًا",
                    "3": "حسب الحجم",
                }
                order = orders.get(choice)
                if order:
                    base_request = str(pending.get("request", "")).strip()
                    state.pending_clarification = None
                    user_input = f"{base_request} {order}".strip()

        mode = detect_mode(user_input)
        # A direct stop request is a conversation control, not an executable
        # task. Do not send it through the parser fallback or Orchestrator.
        if self._is_explicit_stop_request(user_input):
            return {
                "status": "success",
                "intent": Intent.STOP,
                "source": "conversation_manager",
                "text": "سأتوقف عن متابعة الطلب الحالي؛ لم أرسل أمر إلغاء إلى أي مهمة تنفيذية.",
                "executed": False,
            }

        # Incomplete fragments must not inherit a prior continuation act or
        # stale target. Asking for the missing text is read-only: do not append
        # it to dialogue history, update the active topic, or call a provider.
        if self._is_fragmentary_turn(user_input):
            return {
                "status": "needs_clarification",
                "intent": Intent.PERSONAL_CHAT,
                "source": "conversation_manager",
                "text": (
                    "وصلتني رسالة قصيرة أو مبتورة ولم يتضح المقصود منها. "
                    "اكتب الفكرة كاملة أو وضّح ما تريد متابعته."
                ),
                "executed": False,
            }

        # Parse the current turn without any persistent NLU context first.
        # The transition decision below is the sole authority that may grant
        # the active DialogueMemory topic to a second canonical parse.
        confirmation_intent = self._pending_confirmation_intent(user_input)
        candidate = (
            {
                "intent": confirmation_intent,
                "target": "",
                "context": "general",
                "confidence": 1.0,
                "raw": user_input,
                "source": "pending_confirmation",
                "entity_type": "CONFIRMATION",
                "semantic_pattern": "PENDING_CONFIRMATION",
            }
            if confirmation_intent is not None
            else self._safe_parse(user_input)
        )
        if _restore_context:
            candidate = {
                "intent": Intent.PERSONAL_CHAT,
                "target": str(_restore_context.get("entity") or "").strip(),
                "context": "general",
                "confidence": 1.0,
                "raw": user_input,
                "source": "authorized_dialogue_restore",
                "entity_type": _restore_context.get("entity_type", "CONCEPT"),
                "conversation_domain": _restore_context.get("conversation_domain", "general"),
                "conversation_act": "TOPIC_RETURN",
                "conversation_confidence": 1.0,
                "response_attributes": {"dialogue_recovery": "named_topic_return"},
                "semantic_pattern": "AUTHORIZED_DIALOGUE_RESTORE",
            }
        normalized_command = " ".join(
            str(user_input or "").casefold()
            .replace("أ", "ا").replace("إ", "ا")
            .strip(" \t\r\n.,،؛:!?؟")
            .split()
        )
        if normalized_command in {
            "تحقق", "تحقق اولا", "تحقق من فضلك", "تحقق اولا من فضلك",
            "verify", "verify first",
        } and not str(candidate.get("target") or "").strip():
            return {
                "status": "needs_clarification",
                "intent": Intent.VERIFY_FIX,
                "source": "conversation_manager",
                "text": (
                    "ما الذي تريدني أن أتحقق منه تحديدًا؟ "
                    "اذكر الإصلاح أو الاختبار أو المعلومة المقصودة."
                ),
                "executed": False,
            }

        if confirmation_intent is None and self._is_bare_confirmation(user_input):
            # A bare yes/no without a pending operation is dialogue, not a new
            # executable intent and not a reason to overwrite the active topic.
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "REFERENCE",
                "conversation_domain": "social",
                "conversation_act": "SOCIAL_ACKNOWLEDGEMENT",
                "conversation_confidence": 0.90,
                "response_attributes": {},
                "semantic_pattern": "BARE_CONFIRMATION_NO_PENDING",
                "source": "bare_confirmation",
            })
        # `parse()` is the single semantic interpretation boundary for this
        # turn.  Do not classify the same text again here: a second semantic
        # pass can disagree with the canonical parse and let a later branch
        # steal ownership of the response.
        raw_signal = self._semantic_signal_from_parsed(candidate)
        from lab_v4_dev.memory.session_state import session_selector
        selected_session = session_selector(user_input)
        if selected_saved_session_id:
            selected_session = {
                "kind": "id",
                "session_id": selected_saved_session_id,
                "report_mode": "standard",
            }
        normalized_session_request = self._normalize_transition_text(user_input).strip(
            " .,،؛:!?؟"
        )
        live_state = getattr(self.dialogue_memory, "state", None)
        live_dialogue_archive = bool(
            self.dialogue_memory
            and (
                getattr(live_state, "exchange_archive", [])
                or getattr(live_state, "history", [])
                or getattr(live_state, "last_topic", None)
            )
        )
        # The session selector is authoritative once it has identified a
        # previous saved dialogue. Reclassifying that decision as live-history
        # retrieval based on missing phrase markers made equivalent questions
        # ("آخر موضوع ناقشناه سابقًا", "ماذا كنا نقول في الجلسة السابقة")
        # select different memory owners. Only the intentionally ambiguous
        # generic "استرجع الجلسة السابقة" selector may prefer live continuity.
        prefer_live_dialogue = (
            selected_session.get("kind") == "latest"
            and live_dialogue_archive
            and "استرجع الجلسة السابقة" in normalized_session_request
            and not any(marker in normalized_session_request for marker in (
                "ملخص", "تقرير", "سياق", "حالة",
            ))
        )
        # Explicit saved-session language has precedence over the generic
        # dialogue-history act. Otherwise phrases such as "what were we saying
        # in the previous session?" are answered from the live dialogue and the
        # persisted-session selector never reaches the orchestrator. The selector
        # is deliberately phrase-based and returns "none" for ordinary history
        # questions, so those remain in the dialogue-memory path.
        if (
            selected_session.get("kind") != "none"
            and not prefer_live_dialogue
            and not _restore_context
        ):
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.SESSION_RESTORE,
                "target": "",
                "context": "system",
                "session_selector": selected_session,
                "conversation_domain": "system",
                "conversation_act": "ASSISTANT_STATE_QUERY",
                "source": "session_selector",
            })
        saved_session_request = (
            selected_session.get("kind") != "none"
            and not prefer_live_dialogue
            and not _restore_context
        )
        if (
            selected_session.get("kind") == "none"
            and raw_signal.get("conversation_act") == "SAVED_SESSION_RESTORE_REQUEST"
        ):
            pending = getattr(self, "_pending_work_sessions", None)
            if pending is None:
                pending = getattr(
                    getattr(self.orchestrator, "agent", None),
                    "_pending_work_sessions",
                    [],
                ) or []
            choices = "، ".join(
                f"{item.get('number')} ({str((item.get('report') or {}).get('topic') or 'جلسة بلا عنوان')[:45]})"
                for item in pending
                if item.get("number") is not None
            )
            detail = (
                f"الجلسات المتاحة: {choices}."
                if choices
                else "لا توجد جلسات عمل محفوظة قابلة للاختيار حاليًا."
            )
            return {
                "status": "needs_clarification",
                "intent": Intent.SESSION_RESTORE,
                "source": "session_selector",
                "text": "اذكر رقم الجلسة التي تريد استرجاعها. " + detail,
                "executed": False,
                "semantic_request": {
                    "conversation_act": "SAVED_SESSION_RESTORE_REQUEST",
                    "response_attributes": {"saved_session_request": True},
                },
            }
        # A structurally enumerated multi-part message is one compound dialogue
        # request, not an agent-self/capability query merely because its framing
        # mentions testing the assistant. Preserve the whole request for one answer.
        compound_request = self._is_compound_multi_part_request(user_input)
        if compound_request:
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "UNKNOWN",
                "conversation_domain": "general",
                "conversation_act": "NONE",
                "response_attributes": {"compound_request": True},
                "semantic_pattern": "COMPOUND_DIALOGUE_REQUEST",
                "source": "compound_dialogue_request",
            })
            raw_signal = {
                "conversation_domain": "general",
                "conversation_act": "NONE",
                "confidence": 0.95,
                "response_attributes": {"compound_request": True},
                "conversational": True,
            }

        # A contextual acknowledgement such as "نعم أعرف" is not a new
        # executable request. Interpret it as continuation only when the latest
        # same-session assistant turn was itself asking a dialogue question.
        # This keeps the phrase context-sensitive instead of making it a global
        # continuation keyword.
        normalized_ack = self._normalize_transition_text(user_input).strip(
            " .,،؛:!?؟"
        )
        if (
            normalized_ack in {
                "نعم اعرف", "اي اعرف", "اعرف", "نعم اعلم", "اي اعلم",
                "نعم", "اجل", "اي", "ايه", "نعم اكمل", "اجل اكمل",
            }
            and self.dialogue_memory
        ):
            state = getattr(self.dialogue_memory, "state", None)
            session_id = str(getattr(state, "session_id", "") or "")
            recent_assistant = next(
                (
                    turn for turn in reversed(getattr(state, "history", []) or [])
                    if isinstance(turn, dict)
                    and turn.get("role") == "assistant"
                    and (
                        not session_id
                        or str(turn.get("session_id") or "") == session_id
                    )
                    and str(turn.get("context_kind") or "").casefold()
                    not in {"work", "system", "execution"}
                ),
                None,
            )
            prior_question = str(
                (recent_assistant or {}).get("content") or ""
            ).casefold()
            is_dialogue_question = bool(recent_assistant) and any(
                marker in prior_question
                for marker in (
                    "؟", "?", "هل", "تقصد", "اختر", "ما رأيك",
                    "شنو رأيك", "أي موضوع", "اي موضوع",
                )
            )
            if is_dialogue_question:
                raw_signal = dict(raw_signal or {})
                raw_signal.update({
                    "conversation_domain": "general",
                    "conversation_act": "CONVERSATION_CONTINUATION",
                    "confidence": 0.90,
                    "response_attributes": {},
                    "conversational": True,
                })
                candidate = dict(candidate or {})
                candidate.update({
                    "intent": Intent.PERSONAL_CHAT,
                    "target": "",
                    "entity_type": "REFERENCE",
                    "conversation_domain": "general",
                    "conversation_act": "CONVERSATION_CONTINUATION",
                    "conversation_confidence": 0.90,
                    "response_attributes": {},
                    "semantic_pattern": "CONTEXTUAL_DIALOGUE_ACKNOWLEDGEMENT",
                    "source": "contextual_dialogue_acknowledgement",
                })

        explicit_topic = self._explicit_dialogue_topic(user_input)
        if explicit_topic:
            # Explicit topic openings create a dialogue branch even if the LLM
            # provider later fails. The old branch is not inherited as context.
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": explicit_topic,
                "entity_type": "CONCEPT",
                "conversation_domain": raw_signal.get("conversation_domain", "general"),
                "conversation_act": "SOCIAL_OPENING",
                "conversation_confidence": 0.95,
                "semantic_pattern": "EXPLICIT_DIALOGUE_TOPIC",
                "source": "explicit_dialogue_topic",
            })
        explicit_explanation = self._explicit_explanation_topic(user_input)
        normalized_social_text = str(user_input or "").casefold()
        explicit_casual_opening = any(marker in normalized_social_text for marker in (
            "بغيت نهضر معاك", "بغيت نهضر", "موضوع خفيف", "كيفاش داز نهارك",
            "كيف داز نهارك", "كيف كان نهارك", "كيف قضيت يومك", "خلينا نهضرو",
            "نهدرو شوية", "نهضر معاك شوية", "حوار ودي", "حوار عادي",
            "محادثة ودية", "محادثه وديه", "دردشة ودية", "دردشه وديه",
            "نريد أن نتحدث فقط", "نريد ان نتحدث فقط", "دردشة فقط",
        ))
        if explicit_casual_opening and not explicit_explanation:
            # An explicit casual opener is independent of a previously active
            # technical branch; do not inherit its target or prompt history.
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "REFERENCE",
                "conversation_domain": "social",
                "conversation_act": "CASUAL_CONVERSATION",
                "conversation_confidence": 0.98,
                "response_attributes": {},
                "semantic_pattern": "EXPLICIT_CASUAL_OPENING",
                "source": "explicit_casual_opening",
            })
        if explicit_explanation:
            # An explicit explain request is a fresh answer request, not an
            # implicit continuation merely because the sentence contains
            # "نقطة" or persisted dialogue state names the same topic.
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.CYBER_EXPLAIN,
                "target": explicit_explanation,
                "entity_type": "CONCEPT",
                "conversation_domain": "technical",
                "conversation_act": (
                    raw_signal.get("conversation_act")
                    if is_style_act(raw_signal.get("conversation_act"))
                    else "NONE"
                ),
                "conversation_confidence": (
                    raw_signal.get("confidence", 0.0)
                    if is_style_act(raw_signal.get("conversation_act"))
                    else 0.95
                ),
                "response_attributes": (
                    dict(raw_signal.get("response_attributes") or {})
                    if is_style_act(raw_signal.get("conversation_act"))
                    else {}
                ),
                "semantic_pattern": "EXPLICIT_EXPLANATION_START",
                "source": "explicit_explanation_start",
            })
        # A correction such as "لا، قلت موضوع الكتب" names the branch to
        # restore. It must not fall through to a generic current-dialogue
        # summary, which can otherwise point at a greeting or the last reply.
        normalized_correction = self._normalize_transition_text(user_input)
        named_return = re.search(
            r"(?:قلت|اقصد|المقصود)\s+(?:موضوع\s+)?(الكتب|كتب|الفن|الرسم|النحت)",
            normalized_correction,
        )
        if named_return and any(marker in normalized_correction for marker in (
            "لا", "قلت", "اقصد", "المقصود", "كنا نناقش", "كنا نتحدث",
        )):
            named_topic = named_return.group(1)
            if named_topic == "كتب":
                named_topic = "الكتب"
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": named_topic,
                "entity_type": "REFERENCE",
                "conversation_domain": "general",
                "conversation_act": "TOPIC_RETURN",
                "response_attributes": {"dialogue_recovery": "named_topic_return"},
                "semantic_pattern": "NAMED_DIALOGUE_TOPIC_RETURN",
                "source": "named_dialogue_topic_return",
            })
        raw_act = raw_signal.get("conversation_act")
        if raw_act == "CORRECTION":
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "REFERENCE",
                "conversation_domain": "general",
                "conversation_act": "CORRECTION",
                "conversation_confidence": raw_signal.get("confidence", 0.0),
                "response_attributes": dict(raw_signal.get("response_attributes") or {}),
                "semantic_pattern": "DIALOGUE_CORRECTION_OVERRIDE",
                "source": "dialogue_correction_override",
            })
        interrupted_recovery = str(
            (raw_signal.get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold() == "interrupted_branch"
        if raw_act in {
            "CONVERSATION_HISTORY_QUERY",
            "CONVERSATION_CONTINUATION",
            "TOPIC_RETURN",
        } and not explicit_explanation and (
            not explicit_casual_opening
            or raw_act == "CONVERSATION_CONTINUATION"
        ) and not named_return and not self._is_explicit_targeted_proposal(user_input):
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "REFERENCE",
                "conversation_domain": raw_signal.get("conversation_domain", "general"),
                "conversation_act": raw_act,
                "conversation_confidence": raw_signal.get("confidence", 0.0),
                "response_attributes": dict(raw_signal.get("response_attributes") or {}),
                "semantic_pattern": "DIALOGUE_SEMANTIC_OVERRIDE",
                "source": "dialogue_semantic_override",
            })
            if (
                raw_act == "CONVERSATION_CONTINUATION"
                and self.dialogue_memory
                and not (
                    (raw_signal.get("response_attributes") or {}).get("dialogue_recovery")
                    == "interrupted_branch"
                )
            ):
                get_active_context = getattr(
                    self.dialogue_memory, "active_context_entity", None
                )
                active_context = (
                    get_active_context() if callable(get_active_context) else None
                )
                if isinstance(active_context, dict) and active_context.get("entity"):
                    active_action = str(active_context.get("action") or "").casefold()
                    active_type = str(active_context.get("entity_type") or "CONCEPT").upper()
                    technical_continuation = (
                        raw_signal.get("conversation_domain") in {"technical", "project"}
                        or active_action in {"cyber_explain", "explain"}
                        or active_type in {"FILE", "COMPONENT", "PROJECT"}
                    )
                    candidate.update({
                        "intent": (
                            Intent.CYBER_EXPLAIN
                            if technical_continuation
                            else Intent.PERSONAL_CHAT
                        ),
                        "target": active_context["entity"],
                        "entity_type": active_type,
                        "conversation_domain": (
                            "technical"
                            if technical_continuation
                            else raw_signal.get("conversation_domain", "general")
                        ),
                    })
                elif raw_act == "CONVERSATION_CONTINUATION":
                    # Social turns can intentionally clear active_context. For
                    # a bare "اكمل", recover only the latest explicitly named
                    # dialogue topic; never invent a topic from free-form text.
                    archive = getattr(
                        getattr(self.dialogue_memory, "state", None),
                        "exchange_archive",
                        [],
                    ) or []
                    archived_topic = next(
                        (
                            item for item in reversed(archive)
                            if isinstance(item, dict)
                            and str(item.get("target") or "").strip()
                            and item.get("context_kind") not in {"work", "system", "execution"}
                        ),
                        None,
                    )
                    if archived_topic:
                        candidate.update({
                            "target": str(archived_topic.get("target") or "").strip(),
                            "entity_type": "CONCEPT",
                            "conversation_domain": "general",
                        })
        # Preserve an explicitly named creative branch even when the sentence
        # is phrased as a negated correction ("لا أريد أن نعود إلى...").
        # Without this extraction the semantic layer sees only CONTINUATION
        # and the active branch remains the unrelated social conversation.
        normalized_topic_request = self._normalize_transition_text(user_input)
        if (
            raw_act == "CONVERSATION_CONTINUATION"
            and any(marker in normalized_topic_request for marker in ("فن", "رسم", "نحت", "نقش"))
        ):
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "الفن والرسم والنحت والنقش",
                "entity_type": "CONCEPT",
                "conversation_domain": "general",
                "conversation_act": "TOPIC_RETURN",
                "response_attributes": {"dialogue_recovery": "named_topic_return"},
                "semantic_pattern": "NAMED_DIALOGUE_TOPIC_RETURN",
                "source": "named_dialogue_topic_return",
            })
        ordinal_exchange = self._ordinal_dialogue_exchange(user_input)
        if ordinal_exchange and str(ordinal_exchange.get("target") or "").strip():
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": str(ordinal_exchange.get("target") or "").strip(),
                "entity_type": "CONCEPT",
                "conversation_domain": "general",
                "conversation_act": "TOPIC_RETURN",
                "response_attributes": {"dialogue_recovery": "ordinal_topic_return"},
                "semantic_pattern": "ORDINAL_DIALOGUE_TOPIC_RETURN",
                "source": "ordinal_dialogue_topic_return",
            })
        generic_social_topic_return = False
        normalized_return_request = self._normalize_transition_text(user_input)
        explicit_topic_return = any(marker in normalized_return_request for marker in (
            "ارجع الى الموضوع", "ارجع لموضوع", "نرجع الى الموضوع",
            "نرجع لموضوع", "عد الى الموضوع", "عد لموضوع",
            "الموضوع السابق", "الموضوع الاول", "الموضوع الثاني",
            "previous topic", "return to the topic", "back to the topic",
        ))
        generic_topic = (
            None
            if (
                _restore_context
                or
                raw_act == "CONVERSATION_HISTORY_QUERY"
                and not explicit_topic_return
            )
            or explicit_casual_opening
            or (interrupted_recovery and not explicit_topic_return)
            else self._resolve_generic_topic_reference(user_input)
        )
        if generic_topic:
            candidate = dict(candidate or {})
            is_ordinal_return = any(marker in str(user_input or "").casefold() for marker in (
                "الأول", "الاول", "الثاني", "الثانى", "first", "second",
                "ارجع", "عد إلى", "عد الى", "نرجع",
            ))
            state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
            archive = getattr(state, "exchange_archive", []) if state is not None else []
            normalized_topic = self._normalize_transition_text(generic_topic)
            restored_exchange = next(
                (
                    item for item in reversed(archive or [])
                    if isinstance(item, dict)
                    and not item.get("recall_only")
                    and (
                        self._normalize_transition_text(item.get("target") or "") == normalized_topic
                        or self._normalize_transition_text(item.get("user") or "") == normalized_topic
                    )
                ),
                None,
            )
            restored_domain = str(
                (restored_exchange or {}).get("conversation_domain") or "general"
            ).casefold()
            restored_kind = str(
                (restored_exchange or {}).get("context_kind") or "dialogue"
            ).casefold()
            restored_intent = str(
                (restored_exchange or {}).get("intent") or ""
            ).casefold()
            restored_social = (
                restored_domain not in {"technical", "project", "work", "system", "execution"}
                and restored_kind in {"dialogue", "social", "unknown"}
            )
            history_reference = (
                raw_act == "CONVERSATION_HISTORY_QUERY"
                and bool((candidate.get("response_attributes") or {}).get("dialogue_response_mode"))
            )
            generic_social_topic_return = bool(restored_social)
            candidate.update({
                "intent": (
                    Intent.PERSONAL_CHAT
                    if restored_social or history_reference
                    else (
                        restored_intent
                        if restored_intent and restored_intent not in {
                            "personal_chat", "chat", "discussion", "question", "unclear",
                        }
                        else Intent.CYBER_EXPLAIN
                    )
                ),
                "target": generic_topic,
                "entity_type": "REFERENCE" if restored_social else "CONCEPT",
                "semantic_pattern": "GENERIC_TOPIC_REFERENCE",
                "conversation_domain": "general" if history_reference else (restored_domain if restored_social else (
                    "technical" if restored_domain == "general" else restored_domain
                )),
                "conversation_act": (
                    "TOPIC_RETURN" if is_ordinal_return or raw_act == "TOPIC_RETURN"
                    else "COMPOUND_REFERENCE"
                ),
                "conversation_confidence": 0.95,
            })
            if explicit_topic_return:
                response_attributes = dict(candidate.get("response_attributes") or {})
                response_attributes.pop("dialogue_recovery", None)
                candidate["response_attributes"] = response_attributes
        # A short additive follow-up belongs to the immediately preceding
        # dialogue exchange, not to a fresh social topic. Apply this only when
        # the latest archived exchange is dialogue-safe; never borrow work,
        # system, or execution context.
        normalized_follow_up = self._normalize_transition_text(user_input).strip(
            " .,،؛:!?؟"
        )
        # Arabic diacritics (e.g. tanween in "أيضًا") are orthographic,
        # not semantic; remove them for exact short-follow-up matching.
        normalized_follow_up = "".join(
            char for char in normalized_follow_up
            if not "\u064b" <= char <= "\u065f"
            and char != "\u0670"
            and not "\u06d6" <= char <= "\u06ed"
        )
        additive_follow_ups = {
            "ماذا ايضا", "ما ايضا", "وايضا", "وايش ايضا",
            "وماذا ايضا", "وماذا بعد", "ماذا بعد", "ما بعد",
            "شيء اخر", "شيئا اخر", "شي اخر", "شيئا اضافيا",
            "anything else", "what else", "and what else", "more",
        }
        if normalized_follow_up in additive_follow_ups and self.dialogue_memory:
            archived = getattr(
                getattr(self.dialogue_memory, "state", None),
                "exchange_archive",
                [],
            ) or []
            previous_exchange = next(
                (
                    item for item in reversed(archived)
                    if isinstance(item, dict)
                    and str(item.get("assistant") or "").strip()
                ),
                None,
            )
            previous_kind = str(
                (previous_exchange or {}).get("context_kind") or ""
            ).casefold()
            previous_domain = str(
                (previous_exchange or {}).get("conversation_domain") or ""
            ).casefold()
            if (
                previous_exchange
                and previous_kind in {"dialogue", "social"}
                and previous_domain not in {"work", "system", "execution"}
                and not self._is_explicit_targeted_proposal(user_input)
            ):
                candidate = dict(candidate or {})
                candidate.update({
                    "intent": Intent.PERSONAL_CHAT,
                    "target": "",
                    "entity_type": "REFERENCE",
                    "conversation_domain": "general",
                    "conversation_act": "CONVERSATION_CONTINUATION",
                    "conversation_confidence": 0.90,
                    "response_attributes": {},
                    "semantic_pattern": "CONTEXTUAL_ADDITIVE_FOLLOW_UP",
                    "source": "contextual_additive_follow_up",
                })

        transition = self._classify_context_transition(mode, candidate, text=user_input)
        interrupted_anchor = ""
        if interrupted_recovery and not generic_topic:
            # The wording describes a past topic switch, not a new switch now.
            # Restore the archived side branch when its subject is known;
            # otherwise keep the recovery request conversational and use the
            # bounded branch-selection fallback below.
            previous_context = (
                self.dialogue_memory.previous_context_entity()
                if self.dialogue_memory
                and callable(getattr(self.dialogue_memory, "previous_context_entity", None))
                else None
            )
            branch_exchanges = (
                self.dialogue_memory.interrupted_branch_exchanges()
                if self.dialogue_memory
                and callable(getattr(self.dialogue_memory, "interrupted_branch_exchanges", None))
                else []
            )
            if branch_exchanges:
                anchor_item = next(
                    (
                        item for item in branch_exchanges
                        if str(item.get("target") or item.get("user") or "").strip()
                    ),
                    {},
                )
                interrupted_anchor = " ".join(
                    part for part in (
                        str(anchor_item.get("target") or "").strip(),
                        str(anchor_item.get("user") or "").strip(),
                        str(anchor_item.get("assistant") or "").strip(),
                    ) if part
                )
                # Archive-only recovery must work even when the short visible
                # turn window or context_history no longer contains the branch.
                archived_target = next(
                    (
                        str(item.get("target") or "").strip()
                        for item in reversed(branch_exchanges)
                        if str(item.get("target") or "").strip()
                    ),
                    "",
                )
                if archived_target:
                    get_context = getattr(self.dialogue_memory, "context_for_topic", None)
                    archived_context = get_context(archived_target) if callable(get_context) else None
                    if not isinstance(archived_context, dict):
                        archived_exchange = next(
                            (
                                item for item in reversed(branch_exchanges)
                                if str(item.get("target") or "").strip() == archived_target
                            ),
                            {},
                        )
                        archived_context = {
                            "entity": archived_target,
                            "action": str(archived_exchange.get("intent") or "cyber_explain"),
                            "entity_type": (
                                "CONCEPT"
                                if str(archived_exchange.get("conversation_domain") or "").casefold() == "technical"
                                else "UNKNOWN"
                            ),
                        }
                    previous_context = archived_context
                    candidate = dict(candidate or {})
                    candidate["target"] = archived_target
                    restored_entity_type = str(
                        archived_context.get("entity_type") or "CONCEPT"
                    ).upper()
                    restored_action = str(
                        archived_context.get("action") or ""
                    ).casefold()
                    candidate["entity_type"] = restored_entity_type

                    # The semantic override initially labels a generic return
                    # as personal_chat. Once interrupted-branch recovery has
                    # resolved a concrete archived branch, restore that
                    # branch's canonical action instead of dispatching the
                    # recovery utterance as chat.
                    if restored_action not in {
                        "", "personal_chat", "chat", "discussion",
                        "question", "unclear",
                    }:
                        candidate["intent"] = archived_context["action"]
                    elif (
                        restored_entity_type in {"CONCEPT", "COMPONENT", "FILE", "PROJECT"}
                        and str(
                            archived_context.get("conversation_domain") or
                            ("technical" if restored_entity_type == "CONCEPT" else "")
                        ).casefold() in {"technical", "project"}
                    ):
                        candidate["intent"] = Intent.CYBER_EXPLAIN

                    if restored_entity_type in {"CONCEPT", "COMPONENT"}:
                        candidate["conversation_domain"] = "technical"
            transition = (
                ContextTransition.RESTORE
                if branch_exchanges or (
                    isinstance(previous_context, dict) and previous_context.get("entity")
                )
                else ContextTransition.AMBIGUOUS
            )
        if (
            explicit_casual_opening
            and not explicit_explanation
            and raw_act != "CONVERSATION_CONTINUATION"
        ):
            # Social openings are independent turns: never attach the previous
            # technical entity or its prompt history to the semantic request.
            transition = ContextTransition.NEW_INDEPENDENT
        # An explicit independent-topic marker overrides a parser-produced
        # compound/reference act. The old branch must not enter a new topic's
        # prompt or trigger privacy blocking because of stale content.
        if not interrupted_recovery and (
            self._is_explicit_independent_topic(user_input, candidate)
            or self._is_explicit_topic_switch(user_input)
        ):
            # Independent-topic intent and explicit topic-switch wording are
            # separate signals. An active branch alone must not turn every
            # independent request into EXPLICIT_SWITCH.
            transition = (
                ContextTransition.EXPLICIT_SWITCH
                if self._is_explicit_topic_switch(user_input)
                else ContextTransition.NEW_INDEPENDENT
            )
            # The legacy context resolver may have already inherited the old
            # target before the transition marker was evaluated. Recover the
            # explicit subject after an explanation or dialogue-switch phrase.
            import re as _re
            independent_subject = _re.search(
                r"(?:اشرح|عن|حول|explain|ننتقل|انتقل)\s+(?:(?:الى|إلى)\s+|ل)?([^،,.؟?]+)",
                user_input,
                flags=_re.IGNORECASE,
            )
            if independent_subject:
                subject = independent_subject.group(1).strip()
                subject = _re.split(
                    r"\s+(?=بالتفصيل|باختصار|ثم(?:\s|$)|و(?:\s|$))",
                    subject,
                    maxsplit=1,
                )[0]
                if subject:
                    candidate = dict(candidate or {})
                    candidate["target"] = subject
                    candidate["intent"] = (
                        Intent.PERSONAL_CHAT if explicit_topic else Intent.CYBER_EXPLAIN
                    )
                    candidate["entity_type"] = "CONCEPT"
                    candidate["conversation_domain"] = (
                        "general" if explicit_topic else "technical"
                    )
            else:
                # Do not carry an inherited target into a new subjectless topic.
                candidate = dict(candidate or {})
                candidate["target"] = ""
                candidate["entity_type"] = "UNKNOWN"
                if not explicit_explanation:
                    candidate["intent"] = Intent.PERSONAL_CHAT
                    candidate["conversation_domain"] = "social"
        if (
            selected_session.get("kind") != "none"
            and not prefer_live_dialogue
            and not _restore_context
        ):
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.SESSION_RESTORE,
                "target": "",
                "context": "system",
                "session_selector": selected_session,
                "conversation_domain": "system",
                "conversation_act": "ASSISTANT_STATE_QUERY",
                "source": "session_selector",
            })
        # Reassert compound-test ownership after every legacy override above;
        # an incidental friendly phrase or session keyword inside one numbered
        # item must not steal the whole message's route.
        if compound_request:
            candidate = dict(candidate or {})
            candidate.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": "",
                "entity_type": "UNKNOWN",
                "conversation_domain": "general",
                "conversation_act": "NONE",
                "response_attributes": {"compound_request": True},
                "semantic_pattern": "COMPOUND_DIALOGUE_REQUEST",
                "source": "compound_dialogue_request",
            })
            transition = ContextTransition.NEW_INDEPENDENT

        self._clear_unrelated_execution_file(transition, candidate)
        resolved_input = (
            f"{interrupted_anchor} {user_input}".strip()
            if interrupted_recovery and interrupted_anchor
            else user_input
        )
        parsed = candidate
        context_entity = None
        if self.dialogue_memory:
            if transition == ContextTransition.RESTORE:
                get_context = getattr(
                    self.dialogue_memory,
                    "context_for_topic",
                    None,
                )
                if callable(get_context):
                    context_entity = get_context(candidate.get("target"))
                if context_entity is None and not generic_social_topic_return:
                    get_previous = getattr(
                        self.dialogue_memory,
                        "previous_context_entity",
                        None,
                    )
                    if callable(get_previous):
                        context_entity = get_previous()
            elif transition.value in CONTEXTUAL_TRANSITIONS:
                get_active_context = getattr(
                    self.dialogue_memory,
                    "active_context_entity",
                    None,
                )
                if callable(get_active_context):
                    context_entity = get_active_context()

        active_branch = context_entity
        get_branch = getattr(self.dialogue_memory, "active_dialogue_branch", None) if self.dialogue_memory else None
        if callable(get_branch):
            active_branch = get_branch() or context_entity
        branch_domain = str((active_branch or {}).get("conversation_domain") or "general").casefold()
        branch_action = str((active_branch or {}).get("action") or "").casefold()
        branch_is_dialogue = bool(active_branch) and (
            branch_domain not in {"technical", "project", "work", "system", "execution"}
            or branch_action in {"personal_chat", "chat", "discussion"}
        )
        parsed_intent_value = str(
            getattr(parsed.get("intent"), "value", parsed.get("intent")) or ""
        ).casefold()
        # A short ordinal question (e.g. "ما الاقتراح الأول؟") is a contextual
        # dialogue reference only when a dialogue branch is already active.
        # Do not let a targetless proposal parser turn it into a new operation.
        if (
            branch_is_dialogue
            and self._is_contextual_ordinal_follow_up(user_input)
            and not self._is_explicit_topic_switch(user_input)
        ):
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": active_branch.get("entity") or "",
                "entity_type": active_branch.get("entity_type", "REFERENCE"),
                "conversation_domain": "general",
                "conversation_act": "TOPIC_CONTINUATION_QUERY",
                "response_attributes": {},
                "semantic_pattern": "DIALOGUE_ORDINAL_FOLLOW_UP",
            })
            transition = ContextTransition.CONTINUE
            parsed_intent_value = "personal_chat"

        diagnostic_intents = {"health", "self_diagnose", "full_diagnose", "run_diagnostics"}
        if (
            branch_is_dialogue
            and not str(parsed.get("target") or "").strip()
            and str(parsed.get("conversation_act") or "").upper()
            in {"CASUAL_CONVERSATION", "GENERAL_CHAT", "SOCIAL_FOLLOW_UP"}
            and not self._is_explicit_topic_switch(user_input)
        ):
            parsed = dict(parsed or {})
            parsed.update({
                "target": active_branch.get("entity") or "",
                "entity_type": active_branch.get("entity_type", "REFERENCE"),
                "conversation_act": "CONVERSATION_CONTINUATION",
                "semantic_pattern": "DIALOGUE_OWNER_SOCIAL_CONTINUATION_GUARD",
            })
            transition = ContextTransition.CONTINUE
        if (
            branch_is_dialogue
            and parsed_intent_value in diagnostic_intents
            and not self._is_explicit_diagnostic_request(user_input)
        ):
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": active_branch.get("entity") or "",
                "entity_type": active_branch.get("entity_type", "REFERENCE"),
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_CONTINUATION",
                "semantic_pattern": "DIALOGUE_OWNER_DIAGNOSTIC_GUARD",
            })
            transition = ContextTransition.CONTINUE
            parsed_intent_value = "personal_chat"

        normalized_turn = self._normalize_transition_text(user_input)
        if (
            branch_is_dialogue
            and parsed_intent_value in {
                getattr(item, "value", item).casefold() for item in _AGENT_SELF_INTENTS
            }
            and "هل تستطيع" in normalized_turn
            and any(marker in normalized_turn for marker in ("تشخيص", "فحص", "تحليل"))
        ):
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": active_branch.get("entity") or "",
                "entity_type": active_branch.get("entity_type", "REFERENCE"),
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_CONTINUATION",
                "semantic_pattern": "DIALOGUE_OWNER_CAPABILITY_GUARD",
            })
            transition = ContextTransition.CONTINUE
            parsed_intent_value = "personal_chat"

        if (
            branch_is_dialogue
            and transition in {ContextTransition.CONTINUE, ContextTransition.REFERENCE}
            and parsed_intent_value in {"cyber_explain", "plan", "propose_solution", "lab_plan"}
            and not self._explicit_explanation_topic(user_input)
            and not self._is_explicit_topic_switch(user_input)
            and not self._is_explicit_targeted_proposal(user_input)
        ):
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": active_branch.get("entity") or "",
                "entity_type": active_branch.get("entity_type", "REFERENCE"),
                "conversation_domain": "general",
                "conversation_act": "CONVERSATION_CONTINUATION",
                "semantic_pattern": "DIALOGUE_OWNER_CONTINUATION_GUARD",
            })
            parsed_intent_value = "personal_chat"

        normalized_reference = self._normalize_transition_text(user_input)
        if active_branch and normalized_reference in {
            "هذا", "هذه", "ذلك", "تلك", "ماذا يعني هذا", "ما معنى هذا",
            "اشرح لي هذا", "وضح هذا",
        }:
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PERSONAL_CHAT,
                "target": active_branch.get("entity") or "",
                "entity_type": active_branch.get("entity_type", "REFERENCE"),
                "conversation_domain": branch_domain if branch_domain in {"social", "general"} else "general",
                "conversation_act": "CONVERSATION_CONTINUATION",
                "semantic_pattern": "DIALOGUE_REFERENCE_RESOLUTION",
            })
            transition = ContextTransition.CONTINUE

        style_request = is_style_act(candidate.get("conversation_act"))
        recovery_mode = str(
            (candidate.get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold()
        unnamed_branch_return = recovery_mode == "interrupted_branch"
        if (
            self.dialogue_memory
            and context_entity
            and not generic_social_topic_return
            and transition.value in CONTEXTUAL_TRANSITIONS
            and not style_request
            and not unnamed_branch_return
            and not self._is_explicit_targeted_proposal(user_input)
            and (
                not candidate.get("target")
                or str(candidate.get("entity_type", "")).upper()
                in {"REFERENCE", "ELABORATION"}
                or (
                    str(candidate.get("conversation_act") or "").upper()
                    in {"CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY"}
                    and str(context_entity.get("action") or "").casefold()
                    in {"cyber_explain", "explain"}
                )
                or recovery_mode == "ordinal_topic_return"
            )
        ):
            resolved_input = self.dialogue_memory.resolve_references(
                user_input,
                context_entity=context_entity,
            )
            # ELABORATION is an explicit contextual follow-up. If the resolver
            # leaves it unchanged, make the authorized reference explicit before
            # the second canonical parse (without doing this for ambiguous turns).
            if (
                resolved_input == user_input
                and str(parsed.get("entity_type") or "").upper() == "ELABORATION"
                and context_entity.get("entity")
            ):
                resolved_input = f"{context_entity['entity']} {user_input}".strip()
            context_action = str(context_entity.get("action") or "").casefold()
            social_active_context = (
                context_action not in {"cyber_explain", "explain"}
                and str(context_entity.get("entity_type") or "").upper()
                not in {"FILE", "COMPONENT", "PROJECT"}
            )
            if resolved_input != user_input and not social_active_context:
                parsed = self._safe_parse(
                    resolved_input,
                    context_entity=context_entity,
                )
            elif social_active_context and transition == ContextTransition.CONTINUE:
                # The active social branch owns this follow-up. Re-parsing a
                # synthetic string such as "الفن ... اكمل" lets legacy
                # explanation rules seize it as cyber_explain.
                parsed = dict(parsed or {})
                parsed["intent"] = Intent.PERSONAL_CHAT
                parsed["target"] = context_entity.get("entity")
                parsed["entity_type"] = context_entity.get("entity_type", "CONCEPT")
                parsed["conversation_domain"] = "general"
                parsed["conversation_act"] = "CONVERSATION_CONTINUATION"

        if (
            context_entity
            and transition.value in CONTEXTUAL_TRANSITIONS
            and not style_request
            and parsed.get("intent") in _NON_EXECUTABLE_INTENTS
            and str(context_entity.get("entity_type", "")).upper() in {"FILE", "COMPONENT", "PROJECT"}
        ):
            parsed = dict(parsed or {})
            parsed["intent"] = Intent.CYBER_EXPLAIN
            parsed["target"] = context_entity.get("entity")
            parsed["entity_type"] = context_entity.get("entity_type")
            parsed["conversation_domain"] = "project"

        if (
            context_entity
            and transition == ContextTransition.CONTINUE
            and not style_request
            and str(context_entity.get("action") or "").casefold()
            in {"cyber_explain", "explain"}
            and parsed.get("intent") in _NON_EXECUTABLE_INTENTS
        ):
            parsed = dict(parsed or {})
            parsed["intent"] = Intent.CYBER_EXPLAIN
            parsed["target"] = context_entity.get("entity")
            parsed["entity_type"] = context_entity.get("entity_type", "CONCEPT")
            parsed["conversation_domain"] = "technical"

        # Normalize generic reference words after, not before, the memory
        # owner has supplied the authorized subject. With no subject, erase
        # the parser's lexical placeholder so the executor cannot receive it
        # as a real target.
        normalized_target = self._normalize_transition_text(parsed.get("target"))
        if normalized_target in {
            "هذا", "هذه", "ذلك", "تلك", "هذا الامر", "ذلك الامر",
            "الامر", "الفكرة", "الموضوع", "الشرح", "النقطة",
        }:
            parsed = dict(parsed or {})
            if context_entity and context_entity.get("entity"):
                parsed["target"] = context_entity["entity"]
                parsed["entity_type"] = context_entity.get("entity_type", "REFERENCE")
            else:
                parsed["target"] = ""

        # A saved-session selector is an explicit routing decision. Context
        # enrichment above may re-parse a synthetic reference and discard
        # selector metadata, so reassert saved-session ownership immediately
        # before semantic construction and keep the request isolated from the
        # active dialogue branch.
        if saved_session_request:
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.SESSION_RESTORE,
                "target": "",
                "context": "system",
                "session_selector": selected_session,
                "conversation_domain": "system",
                "conversation_act": "ASSISTANT_STATE_QUERY",
                "source": "session_selector",
            })
            transition = ContextTransition.NEW_INDEPENDENT
            context_entity = None
            chat_history = []
        else:
            chat_history = self._history_for_transition(transition, parsed)

        parsed = dict(parsed or {})
        conversation_act = str(parsed.get("conversation_act") or "NONE")
        if transition == ContextTransition.RESTORE:
            conversation_act = "TOPIC_RETURN"
        elif transition == ContextTransition.EXPLICIT_SWITCH:
            conversation_act = "TOPIC_SHIFT"
        elif (
            transition.value in CONTEXTUAL_TRANSITIONS
            and conversation_act == "NONE"
        ):
            conversation_act = "CONVERSATION_CONTINUATION"
        parsed["conversation_act"] = conversation_act
        parsed.setdefault("conversation_domain", "general")
        parsed.setdefault("conversation_confidence", 0.0)
        parsed.setdefault("response_attributes", {})

        # Generic targetless proposals are dialogue, even when the fallback parser
        # labels their domain as execution. Preserve execution ownership only when
        # the user actually asks to run/execute/deploy something or names a target.
        proposal_intent = str(
            getattr(parsed.get("intent"), "value", parsed.get("intent")) or ""
        ).casefold()
        proposal_domain = str(parsed.get("conversation_domain") or "general").casefold()
        proposal_target = str(parsed.get("target") or "").strip()
        normalized_proposal_text = self._normalize_transition_text(user_input)
        explicit_execution_markers = (
            "نفذ", "نفذ الامر", "ابدأ التنفيذ", "ابدا التنفيذ",
            "شغل", "تشغيل", "انشر", "تنفيذ", "execute", "run", "deploy",
        )
        if (
            proposal_intent in {"propose_solution", "plan"}
            and not proposal_target
            and proposal_domain == "execution"
            and not any(
                marker in normalized_proposal_text
                for marker in explicit_execution_markers
            )
        ):
            parsed["conversation_domain"] = "general"

        # Explicit targeted proposals are independent requests. Reassert this
        # ownership after legacy context/continuation overrides so the active
        # social branch cannot rewrite a concrete proposal as casual dialogue.
        if self._is_explicit_targeted_proposal(user_input):
            normalized_proposal = self._normalize_transition_text(user_input)
            target_match = re.search(
                r"(?:لمشكلة|بخصوص|حول|عن)\s+(.+)$",
                normalized_proposal,
            )
            proposal_target = (
                str((target_match.group(1) if target_match else "") or "").strip()
                or str((parsed or {}).get("target") or "").strip()
                or str(user_input or "").strip()
            )
            parsed = dict(parsed or {})
            parsed.update({
                "intent": Intent.PROPOSE_SOLUTION,
                "target": proposal_target,
                "entity_type": "CONCEPT",
                "conversation_domain": "technical",
                "conversation_act": "NONE",
                "semantic_pattern": "EXPLICIT_TARGETED_PROPOSAL",
                "source": "explicit_targeted_proposal",
            })
            transition = ContextTransition.NEW_INDEPENDENT
            context_entity = None
            chat_history = []

        # Canonical semantic request follows the context-authorized parse and
        # is established before selecting the execution owner.
        semantic = build_semantic_request(
            user_input,
            mode,
            intent=getattr(parsed.get("intent"), "value", parsed.get("intent")),
            conversation_domain=parsed.get("conversation_domain", "general"),
            conversation_act=conversation_act,
            conversation_confidence=float(
                parsed.get("conversation_confidence", 0.0) or 0.0
            ),
            response_attributes=parsed.get("response_attributes") or {},
            confidence=(
                float(parsed.get("confidence", 0.0))
                if parsed else 0.0
            ),
            target=(
                parsed.get("target")
                or (
                    context_entity.get("entity")
                    if context_entity and transition.value in CONTEXTUAL_TRANSITIONS
                    else None
                )
            ),
            requires_context=(transition.value in CONTEXTUAL_TRANSITIONS),
            context_transition=transition,
            context_kind=self._context_kind(user_input, parsed, transition),
        )

        # A generic return with no recoverable dialogue branch must fail
        # closed instead of being treated as a successful chat response.
        if raw_act == "TOPIC_RETURN" and not generic_topic and not _restore_context and self.dialogue_memory:
            state = getattr(self.dialogue_memory, "state", None)
            has_dialogue = bool(
                getattr(state, "history", [])
                or getattr(state, "exchange_archive", [])
                or getattr(state, "context_history", [])
                or getattr(state, "last_topic", None)
            )
            if not has_dialogue:
                return {
                    "status": "needs_clarification",
                    "intent": Intent.MEMORY_DUMP,
                    "source": "dialogue_memory",
                    "text": "لا يوجد موضوع سابق مسجل أستطيع الرجوع إليه في هذه الجلسة. اذكر الموضوع الذي تريد استعادته.",
                    "executed": False,
                    "semantic_request": semantic.as_dict(),
                }

        # Strong project-progress requests must be resolved before broad
        # dialogue-history rules see words such as "كنا". This is still a
        # project-state read, not a dialogue-memory summary. Explicit saved
        # session restores and explicitly requested general scopes keep their
        # existing owners.
        # Project progress is a local knowledge request, not generic chat or dialogue recall.
        # Resolve scope from the current turn plus an already-authorized active branch.
        local_project_answer = self._local_project_progress_answer(
            user_input, parsed, context_entity
        )
        if local_project_answer is not None and not saved_session_request and not _restore_context:
            # Anchor the saved branch to the actual project, not a stale technical target
            # inherited by a parser fallback on a short continuation.
            from dataclasses import replace as dataclass_replace
            project_parsed = dict(parsed or {})
            project_parsed.update({
                "target": "CyberLab Agent",
                "entity_type": "PROJECT",
                "conversation_domain": "project",
            })
            project_semantic = dataclass_replace(
                semantic,
                conversation_domain="project",
                context_kind="project",
                target="CyberLab Agent",
            )
            local_project_answer["semantic_request"] = project_semantic.as_dict()
            local_project_answer = self._finalize_local_dialogue_result(
                local_project_answer, mode, project_parsed, project_semantic
            )
            if self.dialogue_memory and hasattr(self.dialogue_memory, "update"):
                self.dialogue_memory.update(
                    user_input, local_project_answer, mode=mode, parsed=project_parsed,
                    context_transition=transition,
                )
            return local_project_answer


        # Ownership is decided before any generic/local responder. A history
        # query must never fall through to clarification, social chat, generic
        # topic resolution, or the LLM merely because the memory renderer has
        # no matching branch. An empty/insufficient archive is still a memory
        # answer with a memory-owned source.
        explicit_topic_reference = self._resolve_generic_topic_reference(user_input)
        named_topic_return = bool(re.search(
            r"(?:قلت|اقصد|المقصود)\s+(?:موضوع\s+)?(?:الكتب|كتب|الفن|الرسم|النحت)",
            self._normalize_transition_text(user_input),
        ))
        normalized_history_request = self._normalize_transition_text(user_input)
        history_output_request = (
            self._dialogue_recall_requested(user_input, parsed)
            and any(marker in normalized_history_request for marker in (
                "ماذا كنا نقول", "ماذا كنا نتحدث", "ما كنا نقول",
                "الردود السابقة", "الردود السابقه", "قبل قليل",
                "ملخص الحوار", "اكتب ملخص", "لخص الحوار",
                "مضمون الجلسة", "مضمون الجلسه", "محتوى الجلسة",
                "محتوى الجلسه", "الموضوع الذي ناقشناه سابقا",
            ))
        )
        # A request to print/summarize the dialogue archive outranks a vague
        # reference to "the topic". Only an actual named/ordinal topic return
        # should bypass the history renderer.
        specific_dialogue_return = bool(
            not history_output_request
            and (
                explicit_topic_reference
                or self._ordinal_dialogue_exchange(user_input)
                or named_topic_return
            )
        )
        if (
            (
                raw_act == "CONVERSATION_HISTORY_QUERY"
                or self._dialogue_recall_requested(user_input, parsed)
            )
            and not specific_dialogue_return
            and not saved_session_request
        ):
            history_result = self._conversation_history_answer(user_input, parsed)
            if history_result is None:
                history_result = {
                    "status": "needs_clarification",
                    "intent": Intent.MEMORY_DUMP,
                    "source": "dialogue_memory",
                    "text": (
                        "لا توجد بيانات كافية في ذاكرة الحوار للإجابة عن طلب الاسترجاع. "
                        "اذكر الموضوع أو اطلب ملخص الحوار الحالي."
                    ),
                    "executed": False,
                }
            history_result["semantic_request"] = semantic.as_dict()
            history_result = self._finalize_local_dialogue_result(
                history_result, mode, parsed, semantic
            )
            # Retrieval is read-only: do not archive the retrieval request as a
            # new dialogue exchange or make it the next active topic.
            return history_result

        # Keep the unified responder scoped to greetings and closings.
        # Social openings, casual dialogue, acknowledgements, continuations, and
        # history requests retain their established owners below; otherwise this
        # helper can bypass social finalization, archive ownership, or provider
        # failure recovery.
        unified_act = str(
            (parsed or {}).get("conversation_act")
            or semantic.conversation_act
            or ""
        ).strip().upper()
        local_unified = (
            answer_local_response(
                user_input,
                parsed,
                semantic.as_dict(),
                history=chat_history,
                context_entity=context_entity,
            )
            if not saved_session_request
            and unified_act in {
                "SOCIAL_GREETING",
                "SOCIAL_CLOSING",
            }
            else None
        )
        if local_unified is not None:
            local_unified["semantic_request"] = semantic.as_dict()
            local_unified = self._finalize_local_dialogue_result(
                local_unified, mode, parsed, semantic
            )
            if (
                local_unified.get("status") == "success"
                and self.dialogue_memory
                and hasattr(self.dialogue_memory, "update")
            ):
                self.dialogue_memory.update(
                    user_input, local_unified, mode=mode, parsed=parsed,
                    context_transition=transition,
                )
            return local_unified

        # Explicit persisted-session requests belong to Orchestrator. A local
        # social responder may otherwise consume ASSISTANT_STATE_QUERY and
        # return a generic greeting/history answer before session restoration.
        social_history = chat_history
        if not social_history and not saved_session_request and self.dialogue_memory:
            # An opener may be classified as a new independent conversational
            # turn while still benefiting from recent same-session dialogue.
            # The local composer itself enforces domain boundaries so technical
            # and project history cannot leak into a general social reply.
            social_history = self._history_for_transition(
                ContextTransition.CONTINUE, parsed
            )
        local_social = (
            None
            if saved_session_request
            else self._local_social_answer(
                user_input, parsed, history=social_history
            )
        )
        if local_social is not None:
            local_social["semantic_request"] = semantic.as_dict()
            local_social = self._finalize_local_dialogue_result(
                local_social, mode, parsed, semantic
            )
            if self.dialogue_memory and hasattr(self.dialogue_memory, "update"):
                self.dialogue_memory.update(
                    user_input, local_social, mode=mode, parsed=parsed,
                    context_transition=transition,
                )
            return local_social

        # ----------------------------------------------------
        # أسئلة تاريخ الحوار تُجاب من DialogueMemory محليًا، لا من سياق
        # المشروع أو مزود النموذج.
        conversation_history_answer = (
            None
            if generic_topic or _restore_context or saved_session_request
            else self._conversation_history_answer(user_input, parsed)
        )
        recovery_mode = str(
            (parsed.get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold()
        if (
            conversation_history_answer is None
            and not _restore_context
            and not saved_session_request
            and self._dialogue_recall_requested(user_input, parsed)
            and not self._resolve_generic_topic_reference(user_input)
            and not self._ordinal_dialogue_exchange(user_input)
            and not re.search(
                r"(?:قلت|اقصد|المقصود)\s+(?:موضوع\s+)?(?:الكتب|كتب|الفن|الرسم|النحت)",
                self._normalize_transition_text(user_input),
            )
            and recovery_mode not in {
                "interrupted_branch", "named_topic_return", "ordinal_topic_return",
            }
        ):
            conversation_history_answer = {
                "status": "needs_clarification",
                "intent": Intent.MEMORY_DUMP,
                "source": "dialogue_memory",
                "text": (
                    "لا أجد موضوعًا حواريًا واضحًا لاستعادته في هذه الجلسة. "
                    "هل تقصد آخر موضوع تعليمي أم سياق العمل؟"
                ),
                "executed": False,
            }
        if self._ambiguous_resume_without_domain(user_input, parsed):
            return {
                "status": "needs_clarification",
                "intent": parsed.get("intent") or Intent.RESUME,
                "source": "conversation_manager",
                "text": (
                    "هل تريد استكمال الحوار السابق أم استكمال العمل في جلسة أو ملف؟"
                ),
                "executed": False,
                "semantic_request": semantic.as_dict(),
            }
        if conversation_history_answer is not None:
            result = conversation_history_answer
            result["semantic_request"] = semantic.as_dict()
            result = self._finalize_local_dialogue_result(
                result, mode, parsed, semantic
            )
            if self.dialogue_memory and hasattr(self.dialogue_memory, "update"):
                self.dialogue_memory.update(
                    user_input, result, mode=mode, parsed=parsed,
                    context_transition=transition,
                )
            return result

        # An interrupted-branch recovery is a grounded dialogue request. Even
        # when the archived branch was technical, do not execute the recovery
        # sentence as a fresh technical command; let the chat owner continue
        # from the archived evidence.
        if recovery_mode in {"interrupted_branch", "named_topic_return"}:
            parsed = dict(parsed or {})
            parsed["intent"] = Intent.PERSONAL_CHAT
            parsed["conversation_domain"] = "general"
            mode = "CHAT"

        # ----------------------------------------------------
        # ONE execution owner.
        # ----------------------------------------------------
        result = self._dispatch(
            resolved_input,
            mode,
            parsed,
            user_question=user_input,
            chat_history=chat_history,
            context_transition=transition.value,
        )

        # Project-list clarification is conversation-owned state.
        if self.dialogue_memory:
            state = getattr(self.dialogue_memory, "state", None)
            if state is not None:
                if (
                    result.get("status") == "needs_clarification"
                    and parsed.get("intent") == Intent.PROJECT_INDEX
                    and any(
                        term in str(user_input)
                        for term in (
                            "المشاريع",
                            "مشاريع",
                            "اسماء",
                            "أسماء",
                            "اسماؤ",
                            "أسماؤ",
                        )
                    )
                ):
                    state.pending_clarification = {
                        "kind": "project_order",
                        "request": user_input,
                    }

        result = dict(result)
        result["semantic_request"] = semantic.as_dict()

        # Saving an explanation is only offered for an actual technical
        # explanation response. Never leak a knowledge-save prompt into casual
        # chat, dialogue recall, or other non-executable conversation turns.
        if (
            semantic.context_kind in {"social", "dialogue"}
            or parsed.get("intent") == Intent.PERSONAL_CHAT
        ):
            result.pop("save_prompt", None)
            result.pop("pending_save", None)
            pending_confirmation = result.get("pending_confirmation")
            if (
                isinstance(pending_confirmation, dict)
                and pending_confirmation.get("kind") == "save_kb"
            ):
                result.pop("pending_confirmation", None)

        # ----------------------------------------------------
        # Presentation layer only.
        # ----------------------------------------------------
        if result.get("text"):
            result["text"] = format_response(
                result["text"],
                mode,
            )

        if self.dni:
            self.dni.set_conversation_analysis({
                "intent": result.get("intent"),
                "mode": result.get("mode", mode),
                "conversation_domain": semantic.conversation_domain,
                "conversation_act": semantic.conversation_act,
                "response_attributes": dict(semantic.response_attributes or {}),
                "confidence": (
                    parsed.get("confidence", 0.0)
                    if parsed else 0.0
                ),
            })

        # ConversationManager owns dialogue-state lifecycle.
        # Agent remains only the runtime facade.
        if self.dialogue_memory and hasattr(self.dialogue_memory, "update"):
            # Topic/user-turn state must survive provider failures. DialogueMemory
            # archives only successful answers; an error response must not become
            # a fabricated continuation checkpoint.
            self.dialogue_memory.update(
                user_input,
                result,
                mode=mode,
                parsed=parsed,
                context_transition=transition,
            )

        return result

    def _finalize_local_dialogue_result(
        self,
        result: dict,
        mode: str,
        parsed: dict,
        semantic,
    ) -> dict:
        """Apply the shared presentation and analysis contract to local dialogue replies."""
        result = dict(result)
        response_attributes = dict(
            result.get("response_attributes")
            or getattr(semantic, "response_attributes", {})
            or {}
        )
        if response_attributes:
            result["response_attributes"] = response_attributes
            response_mode = response_attributes.get("dialogue_response_mode")
            if response_mode and not result.get("dialogue_response_mode"):
                result["dialogue_response_mode"] = response_mode
        if (
            semantic.context_kind in {"social", "dialogue"}
            or parsed.get("intent") == Intent.PERSONAL_CHAT
        ):
            result.pop("save_prompt", None)
            result.pop("pending_save", None)
            pending_confirmation = result.get("pending_confirmation")
            if (
                isinstance(pending_confirmation, dict)
                and pending_confirmation.get("kind") == "save_kb"
            ):
                result.pop("pending_confirmation", None)

        if result.get("text"):
            result["text"] = format_response(result["text"], mode)

        if self.dni:
            self.dni.set_conversation_analysis({
                "intent": result.get("intent"),
                "mode": result.get("mode", mode),
                "conversation_domain": semantic.conversation_domain,
                "conversation_act": semantic.conversation_act,
                "response_attributes": dict(semantic.response_attributes or {}),
                "confidence": (
                    parsed.get("confidence", 0.0)
                    if parsed else 0.0
                ),
            })
        return result

    def _dispatch(
        self,
        text: str,
        mode: str,
        parsed: dict,
        *,
        user_question: str | None = None,
        chat_history: list | None = None,
        context_transition: str | None = None,
    ) -> dict:
        """
        Select exactly ONE execution owner.

        Critical rule:
        Mode is descriptive. Intent is authoritative.

        Therefore:
            FOLLOW_UP + executable Intent
                -> Orchestrator

            QUESTION/DISCUSSION/CHAT + executable Intent
                -> Orchestrator

            non-executable Intent
                -> conversational LLM
        """

        intent = parsed.get("intent") if parsed else None
        explicit_target = str((parsed or {}).get("target") or "").strip()

        # An unnamed interrupted-dialogue recovery is a conversational
        # continuation request. Keep its canonical restored intent/target for
        # memory bookkeeping, but send the selected archived branch to the
        # dialogue prompt instead of treating the recovery wording as a fresh
        # executable explanation request.
        recovery_mode = str(
            ((parsed or {}).get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold()
        if recovery_mode in {"interrupted_branch", "ordinal_topic_return"}:
            return self._handle_chat(
                text,
                mode,
                parsed=parsed,
                user_question=user_question or text,
                history=chat_history,
            )

        if (
            intent in _NON_EXECUTABLE_INTENTS
            and context_transition in CONTEXTUAL_TRANSITIONS
            and explicit_target
            and (parsed or {}).get("conversation_domain") == "project"
            and not is_style_act((parsed or {}).get("conversation_act"))
        ):
            parsed = dict(parsed or {})
            parsed["intent"] = Intent.CYBER_EXPLAIN
            intent = Intent.CYBER_EXPLAIN

        # Agent self-description is grounded conversation, not a system action.
        # This check deliberately precedes SYSTEM mode dispatch.
        if intent in _AGENT_SELF_INTENTS:
            return self._handle_chat(
                text,
                mode,
                parsed=parsed,
                user_question=user_question or text,
                history=chat_history,
            )

        # A bare continuation can inherit CYBER_EXPLAIN solely because the
        # active dialogue branch is the project itself. That inheritance is
        # context resolution, not an instruction to execute project work.
        # Keep this project-owned continuation with the evidence-backed chat
        # responder; a turn that explicitly asks to run/test/deploy remains
        # owned by the operational intent path below.
        normalized_turn = self._normalize_transition_text(user_question or text)
        # Only an affirmative operational command should keep this inherited
        # project branch on the execution path. Negated commands (for example,
        # "لا تشغل الاختبارات") and descriptive mentions ("نتيجة الاختبار")
        # are not execution requests.
        negated_execution = bool(re.search(
            r"(?:^|\s)(?:لا|لم|لن|ما|don't|do not|not)"
            r"(?:\s+\w+){0,2}\s+"
            r"(?:نفذ|تنفذ|شغل|تشغل|تشغيل|اختبر|تختبر|انشر|تنشر|execute|run|deploy)"
            r"(?:\s|$)",
            normalized_turn,
        ))
        explicit_execution = bool(
            re.search(
                r"(?:^|\s)(?:نفذ|تنفذ|شغل|تشغل|اختبر|تختبر|انشر|تنشر|ابدأ التنفيذ|ابدا التنفيذ)"
                r"(?:\s|$)",
                normalized_turn,
            )
            or re.search(
                r"(?:^|\s)تشغيل\s+(?:ال)?(?:اختبارات|اختبار|الأوامر|الاوامر|البرنامج|المشروع)"
                r"(?:\s|$)",
                normalized_turn,
            )
            or re.search(
                r"\b(?:execute|deploy)\b|\brun\s+(?:the\s+)?(?:tests?|command|script|app|application)\b",
                normalized_turn,
            )
        ) and not negated_execution
        contextual_project_continuation = (
            intent == Intent.CYBER_EXPLAIN
            and context_transition in CONTEXTUAL_TRANSITIONS
            and str((parsed or {}).get("conversation_act") or "").upper()
            in {"CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY"}
            and str((parsed or {}).get("conversation_domain") or "").casefold()
            in {"project", "technical"}
            and str((parsed or {}).get("entity_type") or "").upper() == "PROJECT"
        )
        if (
            contextual_project_continuation
            and not explicit_execution
        ):
            # Context resolution may label the inherited PROJECT branch as
            # technical. Canonicalize it back to project ownership before prompt
            # construction so the project roadmap/state is actually injected.
            project_continuation = dict(parsed or {})
            project_continuation["target"] = explicit_target or "CyberLab Agent"
            project_continuation["entity_type"] = "PROJECT"
            project_continuation["conversation_domain"] = "project"
            return self._handle_chat(
                text,
                mode,
                parsed=project_continuation,
                user_question=user_question or text,
                history=chat_history,
            )

        # Component/project questions are knowledge requests, not executable
        # operations. Route them through the evidence-backed chat path before
        # the generic executable-intent fallback below. Explicit file analysis
        # and test/run intents remain owned by Orchestrator.
        knowledge_type = QuestionClassifier.classify(user_question or text)
        knowledge_scope = resolve_project_scope(
            user_question or text,
            intent=intent,
        )
        knowledge_intents = {
            Intent.CYBER_EXPLAIN,
            Intent.ARCHITECTURE,
        }
        explicit_target = str((parsed or {}).get("target") or "").strip()
        if (
            intent in knowledge_intents
            and knowledge_scope == ProjectScope.CURRENT_PROJECT
            and knowledge_type in {"component", "relationship", "execution"}
            and not explicit_target
        ):
            return self._handle_chat(
                text,
                mode,
                parsed=parsed,
                user_question=user_question or text,
                history=chat_history,
            )

        if (
            intent in (Intent.UNSUPPORTED, "unsupported")
            and parsed
            and parsed.get("semantic_pattern") == "DEVICE_MEMORY_UNSUPPORTED"
        ):
            return {
                "status": "unsupported",
                "intent": Intent.UNSUPPORTED,
                "text": (
                    "قراءة ذاكرة RAM للهاتف/الجهاز غير مدعومة من هذه البيئة. "
                    "فحص الصحة المتاح يقيس ذاكرة عملية الوكيل فقط، لا إجمالي "
                    "ذاكرة الجهاز أو المتاح منها."
                ),
                "mode": mode,
                "executed": False,
            }

        # Explicit operational modes.
        # SYSTEM commands are always routed to the orchestrator (agent actions).
        # Do NOT let TASK mode unconditionally override the intent decision —
        # intent remains authoritative to avoid hijacking conversational inputs.
        if mode == "SYSTEM":
            result = self.orchestrator.handle(
                text,
                parsed=parsed,
                context_resolved=True,
                conversation_history=chat_history,
                context_transition=context_transition,
            )
            result = dict(result)
            result["executed"] = result.get("status") != "needs_clarification"
            return result

        # ----------------------------------------------------
        # Unsupported is a canonical non-executable result.
        # Preserve the parser decision instead of letting the
        # conversational fallback relabel it as the current mode.
        if mode == "TASK" and intent in (Intent.UNSUPPORTED, "unsupported"):
            return {
                "status": "unsupported",
                "intent": intent,
                "text": f"لم أفهم الأمر: {text[:50]}",
                "mode": mode,
                "executed": False,
            }

        # ----------------------------------------------------
        # FOLLOW_UP MUST NOT automatically become CHAT.
        #
        # Example:
        # "كيف يعمل؟"
        #   mode   = FOLLOW_UP
        #   intent = cyber_explain
        #
        # Therefore -> Orchestrator.
        # ----------------------------------------------------
        # A generic request for suggestions without a subject is not yet
        # an executable project proposal. Let the conversational layer clarify
        # the domain instead of treating a broad NLU label as an actionable task.
        if (
            intent in {Intent.PROPOSE_SOLUTION, Intent.PLAN}
            and not explicit_target
            and str((parsed or {}).get("conversation_domain") or "general")
            not in {"technical", "project", "system"}
        ):
            return self._handle_chat(
                text,
                mode,
                parsed=parsed,
                user_question=user_question or text,
                history=chat_history,
            )

        if intent not in _NON_EXECUTABLE_INTENTS:
            result = self.orchestrator.handle(
                text,
                parsed=parsed,
                context_resolved=True,
                conversation_history=chat_history,
                context_transition=context_transition,
            )
            result = dict(result)
            result["executed"] = result.get("status") != "needs_clarification"
            return result

        # Only genuinely unresolved conversational input reaches LLM.
        return self._handle_chat(
            text,
            mode,
            parsed=parsed,
            user_question=user_question or text,
            history=chat_history,
        )

    def _safe_parse(self, text: str, *, context_entity: dict | None = None) -> dict:
        try:
            if context_entity:
                result = parse(text, context_entity=context_entity)
            else:
                result = parse(text)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _semantic_signal_from_parsed(parsed: dict | None) -> dict:
        """Expose the canonical parse as a read-only routing signal.

        ConversationManager may inspect the signal to choose a response owner,
        but it must not run a second NLU pass over the same user text.
        IntentParser already owns the mode-independent semantic classification.
        """
        parsed = parsed if isinstance(parsed, dict) else {}
        return {
            "conversation_domain": parsed.get("conversation_domain", "general"),
            "conversation_act": parsed.get("conversation_act", "NONE"),
            "confidence": float(
                parsed.get("conversation_confidence", parsed.get("confidence", 0.0))
                or 0.0
            ),
            "response_attributes": dict(parsed.get("response_attributes") or {}),
            "conversational": parsed.get("intent") in {
                Intent.PERSONAL_CHAT,
                "personal_chat",
            },
        }

    @staticmethod
    @staticmethod
    def _is_compound_multi_part_request(text: str) -> bool:
        """Detect an enumerated multi-part prompt explicitly framed as an assistant test."""
        import re

        value = str(text or "")
        numbered = re.findall(
            r"(?<!\S)(?:[0-9٠-٩]{1,2})\s*[.)、:-]\s+",
            value,
        )
        normalized = ConversationManager._normalize_transition_text(value)
        test_frame = any(marker in normalized for marker in (
            "اختبر قدرتك", "اختبر الوكيل", "اختبار مركب",
            "test your ability", "compound test",
        ))
        return len(numbered) >= 3 and test_frame

    @staticmethod
    def _normalize_transition_text(text: str) -> str:
        return " ".join(
            str(text or "").casefold()
            .replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
            .replace("ئ", "ي").replace("ؤ", "و")
            .replace("ـ", "")
            .replace("فبل", "قبل")
            .split()
        )

    @classmethod
    def _is_contextual_ordinal_follow_up(cls, text: str) -> bool:
        """Recognize a short ordinal question only for an active dialogue branch."""
        normalized = cls._normalize_transition_text(text).strip(" .,،؛:!?؟")
        if not normalized:
            return False
        nouns = r"(?:اقتراح|حل|فكرة|نقطة|موضوع|مثال|سبب|خطوة|ملاحظة|خيار|نتيجة)"
        ordinals = (
            r"(?:اول(?:ى)?|اولي|ثان(?:ي|ية|يه)?|ثالث(?:ة|ه)?|رابع(?:ة|ه)?|"
            r"خامس(?:ة|ه)?|سادس(?:ة|ه)?|سابع(?:ة|ه)?|ثامن(?:ة|ه)?|"
            r"تاسع(?:ة|ه)?|عاشر(?:ة|ه)?|[0-9٠-٩]+)"
        )
        patterns = (
            rf"(?:ما|ماذا|اي|اية)\s+(?:(?:هو|هي|كان|كانت)\s+)?(?:ال)?{nouns}\s+(?:ال)?{ordinals}",
            rf"(?:ما|ماذا|اي|اية)\s+(?:(?:هو|هي|كان|كانت)\s+)?(?:ال)?{ordinals}\s+(?:ال)?{nouns}",
        )
        return any(re.fullmatch(pattern, normalized) for pattern in patterns)

    @classmethod
    def _is_explicit_targeted_proposal(cls, text: str) -> bool:
        """Keep a concrete proposal request operational despite an active dialogue branch."""
        normalized = cls._normalize_transition_text(text).strip()
        if not normalized.startswith(("اقترح ", "اقترحي ", "اقترحوا ", "قدم اقتراح", "اعطني اقتراح")):
            return False
        proposal_cues = (
            "حل", "طريقه", "خطه", "اسلوب", "معالجه", "اصلاح",
            "بديل", "تصميم", "استراتيجيه", "آليه",
        )
        return any(cue in normalized for cue in proposal_cues) and len(normalized.split()) >= 4

    @classmethod
    def _is_explicit_topic_switch(cls, text: str) -> bool:
        # Only direct switch/change wording qualifies; the existence of an
        # active topic or a generic "independent" marker is not enough.
        normalized = cls._normalize_transition_text(text)
        if any(marker in normalized for marker in (
            "الموضوع السابق", "الموضوع الاول", "الموضوع الثاني",
            "السابق", "الاول", "الثاني", "previous", "first", "second",
        )):
            return False
        return any(marker in normalized for marker in (
            "لنغير الموضوع", "نغير الموضوع", "غير الموضوع",
            "ننتقل الى موضوع", "لننتقل الى موضوع",
            "ننتقل الى", "ننتقل ل", "لننتقل الى", "لننتقل ل",
            "لنغير المجال", "نغير المجال",
            "let's change the subject", "change the topic",
        ))

    @classmethod
    def _is_explicit_independent_topic(cls, text: str, parsed: dict) -> bool:
        # An independent-topic marker is authoritative even when target parsing
        # fails; requiring a target can leak the previous branch into the new
        # prompt and cause the privacy gate to reject unrelated content.
        normalized = cls._normalize_transition_text(text)
        return any(marker in normalized for marker in (
            "مستقل", "موضوع جديد", "موضوعا جديدا", "موضوعًا جديدًا",
            "موضوع اخر", "مجال اخر", "موضوع مختلف", "نقاش مختلف", "شيء اخر",
            "independent topic", "new topic", "another field", "different topic",
        ))

    def _resolve_generic_topic_reference(self, text: str) -> str | None:
        """Resolve ordinal topic references from chronological dialogue branches."""
        normalized = self._normalize_transition_text(text)
        if not any(marker in normalized for marker in (
            "موضوع", "topic", "ارجع", "عد الى", "عد إلى", "حوار", "محادث",
            "نقاش", "حديث", "قبل هذا الموضوع",
        )):
            return None

        state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
        session_id = str(getattr(state, "session_id", "") or "")
        archive = getattr(state, "exchange_archive", []) if state is not None else []
        valid = []
        for item in archive or []:
            if not isinstance(item, dict):
                continue
            if session_id and str(item.get("session_id") or "") != session_id:
                continue
            if item.get("recall_only") or item.get("state_boundary_only"):
                continue
            kind = str(item.get("context_kind") or "").casefold()
            domain = str(item.get("conversation_domain") or "").casefold()
            if (
                kind in {"work", "system"}
                or domain in {"work", "system", "execution"}
                or (kind == "execution" and domain != "technical")
            ):
                continue
            user = self._normalize_transition_text(item.get("user") or "")
            if not user:
                continue
            if any(marker in user for marker in (
                "استرجع النقاش", "استرجاع الحوار", "استرجع الحوار",
                "ماذا كنا نقول", "ماذا كنا نتحدث", "لخص الحوار",
                "ملخص الحوار", "حفظ الجلسة", "استرجاع الجلسة",
            )):
                continue
            valid.append(item)

        # Split only on explicit independent-branch boundaries. A restore is
        # a pointer to an earlier branch, not a new topic to insert in the list.
        branches = []
        current = []
        for item in valid:
            transition = str(item.get("context_transition") or "").casefold()
            user = self._normalize_transition_text(item.get("user") or "")
            inferred_switch = any(marker in user for marker in (
                "لنغير الموضوع", "نغير الموضوع", "غير الموضوع",
                "لنغير المجال", "نغير المجال", "موضوع جديد", "موضوعا جديدا",
                "موضوع مختلف", "ننتقل الى موضوع", "change the topic",
                "change the subject",
            ))
            if transition in {"new_independent", "explicit_switch"} or inferred_switch:
                if current:
                    branches.append(current)
                current = [item]
            elif transition == "restore":
                # The restore request itself is not a distinct historical topic.
                continue
            else:
                current.append(item)
        if current:
            branches.append(current)

        topics = []
        for branch in branches:
            first = branch[0]
            label = str(first.get("target") or "").strip()
            if not label:
                label = str(first.get("user") or "").strip()
            if label and label.casefold() not in {topic.casefold() for topic in topics}:
                topics.append(label)

        # Older checkpoints may not have an exchange archive. Keep a safe
        # compatibility fallback, but include only same-session dialogue turns.
        if not topics and state is not None:
            for turn in getattr(state, "history", []) or []:
                if not isinstance(turn, dict) or turn.get("role") != "user":
                    continue
                if session_id and str(turn.get("session_id") or "") != session_id:
                    continue
                target = str(turn.get("target") or "").strip()
                if target and target.casefold() not in {topic.casefold() for topic in topics}:
                    topics.append(target)

        if not topics:
            return None
        if any(marker in normalized for marker in ("الأول", "الاول", "first")):
            return topics[0]
        if any(marker in normalized for marker in ("الثاني", "الثانى", "second")) and len(topics) > 1:
            return topics[1]
        if any(marker in normalized for marker in (
            "السابق", "السابقه", "السابقَ", "previous",
        )):
            return topics[-2] if len(topics) > 1 else topics[0]
        if any(marker in normalized for marker in (
            "الرئيسي", "الرئيسيه", "الاصلي", "الأصلي",
        )):
            return topics[0]
        if any(marker in normalized for marker in (
            "موضوعنا", "حوارنا", "نقاشنا", "ارجع", "نرجع", "عد الى", "عد إلى",
        )):
            return topics[0] if len(topics) == 1 else topics[-2]
        return None

    @staticmethod
    def _dialogue_recall_requested(text: str, parsed: dict | None = None) -> bool:
        """Recognize requests to retrieve past dialogue, not discussion of recall itself."""
        normalized = ConversationManager._normalize_transition_text(text)
        if any(marker in normalized for marker in (
            "سياق العمل", "اخر جلسه", "المهام", "ملف العمل",
        )):
            return False

        # Meta-discussion about implementing or repairing the recall feature
        # must never be treated as a request to recall a previous conversation.
        discusses_feature = any(marker in normalized for marker in (
            "نطور", "تطوير", "يطور", "تطويره", "تحسين", "نحسن",
            "تصحيح", "نصحح", "اصلاح", "نصلح", "بناء", "نبني",
            "تصميم", "نصمم", "فحص", "نفحص", "تحليل", "نحلل",
            "اختبار", "نختبر", "مسار", "طبقات",
        ))
        feature_subject = any(marker in normalized for marker in (
            "سياق الحوار", "سياق المحادث", "استرجاع الحوار",
            "استرجاع المحادث", "طبقات الذاكره", "طبقات الذاكرة",
            "مسار الحوار", "مسارات الحوار",
        ))
        if discusses_feature and feature_subject:
            return False

        conversation_act = str(
            (parsed or {}).get("conversation_act") or ""
        ).upper()
        if conversation_act == "CONVERSATION_HISTORY_QUERY":
            return True

        # Strong retrieval/retrospection cues are sufficient on their own.
        # "سياق الحوار" by itself is not: users may be discussing how to improve
        # dialogue-context handling in the agent, not asking to retrieve a chat.
        strong_recall_markers = (
            "استرجع الحوار", "استرجاع الحوار", "استرجع المحادث", "استرجاع المحادث",
            "ماذا كنا نقول", "ماذا كنا نتحدث", "قبل هذا الموضوع",
            "الموضوع السابق", "الحوار السابق", "النقاش السابق", "الحديث السابق",
            "موضوعنا الاصلي", "ارجع الى الموضوع", "ارجع للحوار", "ارجع الى الحوار",
            "ارجع للنقاش", "ارجع الى النقاش", "اين توقفنا", "ما اخر موضوع",
            "ما اخر نقاش", "ما اخر حوار", "لخص الحوار", "ملخص الحوار",
        )
        if any(marker in normalized for marker in strong_recall_markers):
            return True

        # A generic mention of dialogue context becomes retrieval only when it
        # is paired with an explicit memory operation or a retrospective question.
        mentions_dialogue_context = any(marker in normalized for marker in (
            "سياق الحوار", "سياق المحادث", "سياق النقاش",
        ))
        asks_to_retrieve = any(marker in normalized for marker in (
            "استرجع", "استرجاع", "استعادة", "تذكر", "ماذا كنا", "ما كنا",
            "اين كنا", "لخص", "ملخص", "راجع ما",
        ))
        return mentions_dialogue_context and asks_to_retrieve

    def _ordinal_dialogue_exchange(self, text: str) -> dict | None:
        """Return the requested prior dialogue exchange, not a transcript."""
        normalized = self._normalize_transition_text(text)
        if not any(marker in normalized for marker in (
            "الموضوع الذي كنا نتحدث", "الموضوع الذي تحدثنا",
            "الموضوع السابق", "قبل رد", "قبل جواب",
        )):
            return None
        state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
        session_id = str(getattr(state, "session_id", "") or "")
        exchanges = [
            item for item in (getattr(state, "exchange_archive", []) or [])
            if isinstance(item, dict)
            and (not session_id or str(item.get("session_id") or "") == session_id)
            and str(item.get("context_kind") or "").casefold() not in {"work", "system", "execution"}
            and not item.get("recall_only")
            and not item.get("state_boundary_only")
            and str(item.get("assistant") or "").strip()
        ]
        if not exchanges:
            return None
        if "قبل ردين" in normalized or "قبل جوابين" in normalized:
            return exchanges[-2] if len(exchanges) >= 2 else exchanges[-1]
        if "قبل رد" in normalized or "قبل جواب" in normalized:
            return exchanges[-1]
        # For a generic reference after a clarification turn, choose the most
        # recent exchange carrying a named topic, not the clarification itself.
        return next(
            (item for item in reversed(exchanges) if str(item.get("target") or "").strip()),
            exchanges[-1],
        )

    def _ambiguous_resume_without_domain(self, text: str, parsed: dict) -> bool:
        normalized = str(text or "").casefold().strip()
        selector = (parsed or {}).get("session_selector") or {}
        if isinstance(selector, dict) and selector.get("kind") not in {None, "none"}:
            return False
        # A classified conversational continuation/history request is not a
        # work-session resume, even when the active dialogue has no named entity.
        conversation_act = str((parsed or {}).get("conversation_act") or "").upper()
        if conversation_act in {
            "CONVERSATION_CONTINUATION",
            "CONVERSATION_HISTORY_QUERY",
            "TOPIC_RETURN",
        }:
            return False
        resume_intents = {Intent.RESUME, Intent.SESSION_RESTORE, "resume", "session_restore"}
        intent = getattr(parsed.get("intent"), "value", parsed.get("intent"))
        if intent not in resume_intents and not any(marker in normalized for marker in (
            "اكمل", "أكمل", "استكمل", "نكمل",
        )):
            return False
        if any(marker in normalized for marker in (
            "العمل", "الملف", "المهمة", "جلسة", "مشروع", "work", "file", "task",
        )):
            return False
        get_active_context = (
            getattr(self.dialogue_memory, "active_context_entity", None)
            if self.dialogue_memory else None
        )
        active = get_active_context() if callable(get_active_context) else None
        if active:
            return False

        # A named entity is helpful but not required for a valid dialogue
        # branch. Short/colloquial topic openers often have no canonical target;
        # the same-session exchange archive is the fallback source of continuity.
        state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
        session_id = str(getattr(state, "session_id", "") or "")
        exchanges = getattr(state, "exchange_archive", []) if state is not None else []
        for item in reversed(exchanges or []):
            if not isinstance(item, dict) or item.get("recall_only") or item.get("state_boundary_only"):
                continue
            item_session = str(item.get("session_id") or "")
            if session_id and item_session != session_id:
                continue
            kind = str(item.get("context_kind") or "dialogue").casefold()
            domain = str(item.get("conversation_domain") or "general").casefold()
            if kind in {"work", "system"} or domain in {"work", "system", "execution"}:
                continue
            user_text = str(item.get("user") or "").strip()
            if not user_text:
                continue
            normalized_user = self._normalize_transition_text(user_text)
            if normalized_user in {
                "نعم", "اجل", "لا", "حسنا", "تمام", "مرحبا", "اهلا",
                "السلام عليكم", "وعليكم السلام", "hi", "hello", "yes", "no",
            }:
                continue
            return False
        return True

    def _context_kind(self, text: str, parsed: dict, transition) -> str:
        normalized = str(text or "").casefold()
        if str((parsed or {}).get("conversation_act") or "").upper() in {
            "CONVERSATION_CONTINUATION", "CONVERSATION_HISTORY_QUERY", "TOPIC_RETURN",
        }:
            return "dialogue"
        if self._ambiguous_resume_without_domain(text, parsed):
            return "unknown"
        if self._dialogue_recall_requested(text) or transition.value in CONTEXTUAL_TRANSITIONS:
            return "dialogue"
        if parsed.get("intent") in _AGENT_SELF_INTENTS:
            return "dialogue"
        if parsed.get("intent") == Intent.PERSONAL_CHAT or is_social_act(
            parsed.get("conversation_act")
        ):
            return "social"
        if any(marker in normalized for marker in (
            "اهلا", "أهلا", "مرحبا", "كيفك", "كيف الحال", "ماهو الحال",
        )):
            return "social"
        intent_value = str(
            getattr(parsed.get("intent"), "value", parsed.get("intent")) or ""
        ).casefold()
        explicit_work_intents = {
            "work_context", "work_status", "remaining_tasks", "remaining_work",
            "progress_report", "next_task", "project_report", "context_report",
            "last_project", "current_version", "show_changes",
        }
        if intent_value in explicit_work_intents:
            return "work"
        # An explicit request to continue the work in a named file is a work
        # continuation, not merely a question about project scope. Keep this
        # narrower than generic mentions of a file or repository.
        work_continuation_markers = (
            "استكمل العمل", "اكمل العمل", "أكمل العمل",
            "متابعة العمل", "تابع العمل", "واصل العمل",
        )
        if any(marker in normalized for marker in work_continuation_markers):
            return "work"
        # Generic, targetless proposals are conversational requests even when
        # the intent parser labels them PROPOSE_SOLUTION/PLAN. Classifying them
        # from project scope can assign execution ownership and make
        # DialogueMemory.update discard otherwise successful dialogue replies.
        if (
            intent_value in {"propose_solution", "plan"}
            and not str(parsed.get("target") or "").strip()
            and str(parsed.get("conversation_domain") or "general").casefold()
            not in {"technical", "project", "system", "work", "execution"}
        ):
            return "dialogue"
        scope = resolve_project_scope(text, intent=parsed.get("intent"))
        if scope == ProjectScope.CURRENT_PROJECT:
            return "project"
        return "unknown"

    @staticmethod
    def _local_social_answer(
        text: str,
        parsed: dict,
        history: list | None = None,
    ) -> dict | None:
        normalized = str(text or "").casefold()
        bare_confirmation = normalized.strip(" .!؟?")
        if (
            bare_confirmation in {"نعم", "أجل", "اجل", "بلى", "لا", "كلا", "yes", "no"}
            and (parsed or {}).get("source") == "bare_confirmation"
        ):
            reply = (
                "حسنًا."
                if bare_confirmation in {"لا", "كلا", "no"}
                else "حسنًا، أخبرني بما تريد متابعته."
            )
            return {
                "status": "success",
                "intent": Intent.PERSONAL_CHAT,
                "text": reply,
                "mode": "CHAT",
                "source": "local_social",
                "executed": False,
            }
        if any(marker in normalized for marker in (
            "اكمل", "أكمل", "استكمل", "نكمل", "ارجع", "استرجع",
        )):
            return None
        suggestion_markers = (
            "اقترح انت بعض المواضيع المثيرة", "اقترح أنت بعض المواضيع المثيرة",
            "اقترح انت بعض المواضيع", "اقترح أنت بعض المواضيع",
            "اقترح لي بعض المواضيع", "اقترح بعض المواضيع", "اقترح مواضيع",
            "مواضيع مثيرة للنقاش", "مواضيع للنقاش", "موضوع للنقاش",
            "انت اعطيني اقتراحات", "أنت أعطني اقتراحات", "اعطيني اقتراحات",
            "اعطني اقتراحات", "اقترح موضوع", "اقترح شي موضوع", "اقترح موضوعا",
            "انت اقترح شي موضوع", "نت قتارح شي موضوع", "عن اي موضوع قتارح نتا",
            "عن اي موضوع تقترح انت", "اقترحات اخرى", "اقتراحات اخرى", "اقتراحات أخرى",
            "اقتراحات اخرى في مجال اخر", "اقتراحات أخرى في مجال آخر",
            "اريد اقتراحات اخرى في مجال اخر", "أريد اقتراحات أخرى في مجال آخر",
            "موضوع الذي نتحدث فيه",
        )
        if any(marker in normalized for marker in suggestion_markers):
            return {
                "status": "success",
                "intent": Intent.PERSONAL_CHAT,
                "text": (
                    "إليك بعض الموضوعات المثيرة للنقاش:\n"
                    "1. هل تتحقق الراحة من بلوغ الأهداف أم من الاستمتاع بالرحلة نحوها؟\n"
                    "2. هل تزيد التكنولوجيا إبداع الإنسان أم تجعله أكثر اعتمادًا عليها؟\n"
                    "3. هل يستطيع الفن التعبير عن أفكار تعجز الكلمات عن نقلها؟ "
                    "اختر موضوعًا منها لنناقشه. ما رأيك؟"
                ),
                "mode": "CHAT",
                "source": "local_social",
                "executed": False,
            }
        social_markers = (
            "كيفك", "كيف الحال", "ماهو الحال", "حوار ودي", "حوار عادي",
            "محادثة ودية", "محادثه وديه", "دردشة ودية", "دردشه وديه",
            "نريد أن نتحدث فقط", "نريد ان نتحدث فقط", "دردشة فقط",
            "بغيت نهضر معاك", "بغيت نهضر", "موضوع خفيف", "كيفاش داز نهارك",
            "كيف داز نهارك", "كيف كان نهارك", "كيف قضيت يومك", "خلينا نهضرو",
            "نهدرو شوية", "نهضر معاك شوية", "لنتحدث قليلا", "لنتحدث قليلًا",
            "نتحدث قليلا", "نتحدث قليلًا", "دعنا نتحدث قليلا", "دعنا نتحدث قليلًا",
        )
        if not any(marker in normalized for marker in social_markers):
            # Use semantic act classification for social variants not covered by
            # the legacy phrase rules. Non-social acts still fall through.
            return answer_local_social(text, parsed)

        def contextual_social_reply() -> dict | None:
            candidate = dict(parsed or {})
            act = str(candidate.get("conversation_act") or "").upper()
            supported_acts = {
                "SOCIAL_OPENING", "CASUAL_CONVERSATION", "CASUAL_DISCUSSION",
                "PERSONAL_INTERACTION", "SOCIAL_FOLLOW_UP",
                "CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY",
                "TOPIC_RETURN",
            }
            # This branch is entered only after a social-opening phrase was
            # recognized. If the parser left the act unresolved, use that
            # narrow conversational interpretation instead of the old one-line
            # template; preserve any already-resolved continuation act.
            if act not in supported_acts:
                candidate["conversation_act"] = "SOCIAL_OPENING"
                act = "SOCIAL_OPENING"
            semantic_request = {
                "conversation_act": act,
                "conversation_domain": candidate.get("conversation_domain") or "general",
                "target": candidate.get("target") or "",
                "response_attributes": candidate.get("response_attributes") or {},
            }
            composed = answer_local_response(
                text,
                candidate,
                semantic_request,
                history=history,
            )
            if composed is None:
                return None
            composed = dict(composed)
            composed["intent"] = candidate.get("intent") or Intent.PERSONAL_CHAT
            # Keep the established public source label for callers and
            # DialogueMemory lifecycle rules; the local strategy is recorded
            # separately in local_strategy.
            composed["source"] = "local_social"
            composed["mode"] = "CHAT"
            composed["executed"] = False
            return composed

        if any(marker in normalized for marker in ("كيفك", "كيف الحال", "ماهو الحال")):
            reply = "أنا بخير، شكرًا لسؤالك. كيف حالك أنت؟"
        elif any(marker in normalized for marker in ("كيفاش داز نهارك", "كيف داز نهارك")):
            reply = "لا أعيش يومًا بالمعنى البشري، لكنني مستعد لمحادثتك. كيف كان يومك؟"
        elif "كيف كان نهارك" in normalized or "كيف قضيت يومك" in normalized:
            reply = "لا أعيش يومًا بالمعنى البشري، لكنني جاهز للحديث معك. كيف كان يومك أنت؟"
        elif any(marker in normalized for marker in (
            "محادثة ودية", "محادثه وديه", "دردشة ودية", "دردشه وديه",
            "نريد أن نتحدث فقط", "نريد ان نتحدث فقط", "دردشة فقط",
        )):
            # This explicitly switches away from work; do not revive an old
            # topic through contextual composition after the user asked to leave it.
            reply = "حسنًا، لنتحدث بشكل ودي بعيدًا عن العمل والمهام. ما الذي يشغل بالك؟"
        else:
            composed = contextual_social_reply()
            if composed is not None:
                return composed
            reply = "يمكننا مناقشة موضوع خفيف. ما الذي تود أن تحدثني عنه؟"
        return {
            "status": "success",
            "intent": Intent.PERSONAL_CHAT,
            "text": reply,
            "mode": "CHAT",
            "source": "local_social",
            "executed": False,
        }

    @staticmethod
    def _is_social_filler_exchange(item: dict) -> bool:
        """Keep summaries focused on topics rather than greetings and chat controls."""
        if not isinstance(item, dict):
            return False
        user = normalize_text(str(item.get("user") or ""))
        assistant = normalize_text(str(item.get("assistant") or ""))
        filler_users = {
            normalize_text(value)
            for value in (
                "مرحبا", "مرخبا", "أهلًا", "أهلا", "السلام عليكم",
                "لنتحدث قليلا", "دعنا نتحدث قليلا", "حوار ودي جديد",
                "كيف الحال", "كيفك", "كيف حالك", "كيف كان نهارك",
                "نعم", "أجل", "بلى", "لا", "حسنا", "تمام", "ماذا",
                "أكمل", "اكمل", "نكمل", "تابع", "واصل", "أكمل الحديث",
            )
        }
        social_reply_prefixes = tuple(
            normalize_text(value)
            for value in (
                "أنا بخير، شكرًا لسؤالك",
                "لا أعيش يومًا بالمعنى البشري",
                "مرحبًا. أخبرني بما يشغل اهتمامك الآن",
                "أهلًا بك. هل نتابع حديثًا سابقًا",
                "وعليكم السلام. هل جئت بموضوع تريد مناقشته",
                "حسنًا، أخبرني بما تريد متابعته",
                "يمكننا اختيار موضوع خفيف ثم تطوير النقاش",
            )
        )
        if user in filler_users:
            return True
        return bool(user and any(assistant.startswith(prefix) for prefix in social_reply_prefixes))

    def _conversation_history_answer(self, text: str, parsed: dict | None = None) -> dict | None:
        """Answer recent-dialogue questions from bounded dialogue memory only."""
        normalized = str(text or "").casefold()
        history_act = str((parsed or {}).get("conversation_act") or "").upper()
        normalized_query = normalize_text(text)
        state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
        live_previous_session_recall = (
            normalized_query.strip(" .!؟?") in {
                "استرجع الجلسة السابقة",
                "استرجع الجلسه السابقه",
            }
            and state is not None
            and bool(
                getattr(state, "exchange_archive", [])
                or getattr(state, "history", [])
                or getattr(state, "last_topic", None)
            )
        )
        if live_previous_session_recall:
            # The bare phrase is ambiguous by itself, but when a live dialogue
            # archive exists it means recall that branch. Explicit saved-session
            # requests are excluded by the caller's saved_session_request guard.
            history_act = "CONVERSATION_HISTORY_QUERY"
        if re.search(
            r"(?:قلت|اقصد|المقصود)\s+(?:موضوع\s+)?(?:الكتب|كتب|الفن|الرسم|النحت)",
            self._normalize_transition_text(text),
        ):
            return None
        direct_suggestion = any(marker in normalized for marker in (
            "اقترح انت", "اقترح أنت", "اقترح لي", "اقترح بعض", "اقترح مواضيع",
            "اريد اقتراحات", "أريد اقتراحات", "اعطيني اقتراحات", "اعطني اقتراحات",
            "اقتراحات اخرى", "اقتراحات أخرى", "اقترحات اخرى",
        ))
        historical_recall = any(marker in normalized for marker in (
            "السابق", "سابقا", "سابقًا", "قبل", "تتذكر", "التي قدمتها",
            "التي اقترحتها", "ماذا اقترحت", "ما اقترحت",
        ))
        if direct_suggestion and not historical_recall:
            return None
        recovery_mode = str(
            ((parsed or {}).get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold()
        if self._ordinal_dialogue_exchange(text):
            return None
        # An unnamed return is a routing instruction, not a request to print
        # the archive. Let the transition resolver select the interrupted
        # branch and pass that branch to the response path.
        if (
            recovery_mode in {"interrupted_branch", "ordinal_topic_return"}
            and not live_previous_session_recall
        ):
            return None
        if history_act == "TOPIC_RETURN" and str((parsed or {}).get("target") or "").strip():
            return None
        if (
            history_act not in {"CONVERSATION_HISTORY_QUERY", "TOPIC_RETURN"}
            and not live_previous_session_recall
            and any(marker in normalized for marker in (
                "ارجع", "عد إلى", "عد الى", "الاول", "الأول", "الثاني", "السابق",
                "previous", "first", "second",
            ))
        ):
            return None
        markers = (
            "موضوعين", "الموضوعين", "موضوعات", "المواضيع", "آخر موضوع",
            "اخر موضوع", "ماذا شرح", "ماذا شرحت", "شرحنا", "تكلمنا",
            "ناقشنا", "سجل المحادث", "تاريخ المحادث",
        )
        if (
            history_act not in {"CONVERSATION_HISTORY_QUERY", "TOPIC_RETURN"}
            and not live_previous_session_recall
            and not any(marker in normalized for marker in markers)
        ):
            return None
        current_session_id = str(getattr(state, "session_id", "") or "")
        history = [
            turn for turn in (getattr(state, "history", []) if state is not None else [])
            if isinstance(turn, dict)
            and (
                not current_session_id
                or str(turn.get("session_id") or "") == current_session_id
            )
        ]
        exchanges = getattr(state, "exchange_archive", []) if state is not None else []
        exchanges = [
            item for item in (exchanges or [])
            if isinstance(item, dict)
            and (
                not current_session_id
                or (
                    not str(item.get("session_id") or "").strip()
                    and item.get("context_kind") not in {"work", "system", "execution"}
                )
                or str(item.get("session_id") or "") == current_session_id
            )
        ]
        response_attributes = dict((parsed or {}).get("response_attributes") or {})
        response_mode = str(
            response_attributes.get("dialogue_response_mode", "")
        ).casefold()
        if not response_mode and live_previous_session_recall:
            response_mode = "summary"
        elif not response_mode and any(
            marker in normalized_query
            for marker in (
                "ماذا كنا نقول", "ماذا قلنا", "ما كنا نقول",
                "الردود السابقة", "الردود السابقه", "قبل قليل",
            )
        ):
            # History recall must preserve the recorded user/assistant pairs.
            # A summary is selected only when the user asks for one explicitly.
            response_mode = "transcript"
        elif not response_mode and any(
            marker in normalized_query
            for marker in (
                "كنا نناقش", "كنا نتحدث", "ملخص الحوار السابق",
                "اكتب ملخص الحوار السابق",
            )
        ):
            response_mode = "summary"
        if response_mode in {"summary", "last_question", "answer", "transcript"}:
            result = self._answer_dialogue_history(text, response_mode, exchanges)
            response_attributes["dialogue_response_mode"] = response_mode
            result["response_attributes"] = response_attributes
            result["dialogue_response_mode"] = response_mode
            return result
        topics = []
        for turn in history or []:
            if not isinstance(turn, dict) or turn.get("role") != "user":
                continue
            target = str(turn.get("target") or "").strip()
            intent = str(turn.get("intent") or "").casefold()
            if not target or intent not in {"cyber_explain", "explain", "question"}:
                continue
            if target not in topics:
                topics.append(target)
        if not topics:
            dialogue_candidates = [
                item for item in exchanges
                if isinstance(item, dict)
                and item.get("context_kind") not in {"work", "system"}
                and item.get("conversation_domain") not in {"work", "system"}
                and (
                    not current_session_id
                    or str(item.get("session_id") or "") == current_session_id
                    or not str(item.get("session_id") or "").strip()
                )
            ]
            dialogue_exchanges = (
                dialogue_candidates[-6:]
                if history_act == "CONVERSATION_HISTORY_QUERY"
                else self._latest_dialogue_branch(dialogue_candidates)[-6:]
            )
            if dialogue_exchanges:
                return {
                    "status": "success", "intent": Intent.MEMORY_DUMP,
                    "source": "dialogue_memory",
                    "text": "في الحوار السابق دار التبادل التالي:\n"
                    + "\n".join(self._format_dialogue_exchanges(dialogue_exchanges)),
                    "dialogue_turns": dialogue_exchanges,
                    "executed": False,
                }
            if history_act == "TOPIC_RETURN":
                return {
                    "status": "needs_clarification",
                    "intent": Intent.MEMORY_DUMP,
                    "source": "dialogue_memory",
                    "text": (
                        "لا يوجد موضوع سابق مسجل أستطيع الرجوع إليه في هذه الجلسة. "
                        "اذكر الموضوع الذي تريد استعادته."
                    ),
                    "executed": False,
                }
            return {
                "status": "success", "intent": Intent.MEMORY_DUMP,
                "source": "dialogue_memory",
                "text": "لا توجد موضوعات تعليمية مسجلة في الحوار الحالي.",
                "executed": False,
            }
        text = "الموضوعات التي نوقشت بالترتيب: " + "، ".join(topics)
        if history_act == "CONVERSATION_HISTORY_QUERY" and exchanges:
            # Select complete archived exchanges, not individual turns. Keep
            # relevant dialogue while excluding only explicit work context.
            selected = [
                item for item in exchanges
                if item.get("context_kind") != "work"
                and item.get("conversation_domain") != "work"
                and (
                    not item.get("target")
                    or item.get("target") in topics
                    or any(str(topic).casefold() in str(item.get("user", "")).casefold() for topic in topics)
                )
            ][-6:]
            text += "\n\nالتبادل الأخير:\n" + "\n".join(
                self._format_dialogue_exchanges(selected)
            )
        return {
            "status": "success", "intent": Intent.MEMORY_DUMP,
            "source": "dialogue_memory",
            "text": text,
            "topics": topics,
            "executed": False,
        }

    @staticmethod
    def _latest_dialogue_branch(exchanges: list[dict]) -> list[dict]:
        """Select one active dialogue branch without crossing a later topic boundary."""
        valid = [item for item in (exchanges or []) if isinstance(item, dict)]

        def normalized_user(item: dict) -> str:
            return " ".join(
                str(item.get("user") or "").casefold()
                .replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
                .split()
            )

        def excluded(item: dict) -> bool:
            kind = str(item.get("context_kind") or "").casefold()
            domain = str(item.get("conversation_domain") or "").casefold()
            if (
                kind in {"work", "system"}
                or domain in {"work", "system", "execution"}
                or (kind == "execution" and domain != "technical")
                or item.get("recall_only")
                or item.get("state_boundary_only")
            ):
                return True
            user = normalized_user(item)
            return user == "حفظ" or user.startswith("حفظ ")

        substantive = [item for item in valid if not excluded(item)]
        if not substantive:
            return []

        def boundary(item: dict) -> str:
            transition = str(item.get("context_transition") or "").casefold()
            if transition in {"new_independent", "explicit_switch", "restore"}:
                return transition
            user = normalized_user(item)
            if any(marker in user for marker in (
                "لنغير الموضوع", "نغير الموضوع", "غير الموضوع",
                "لنغير المجال", "نغير المجال", "ننتقل الى موضوع",
                "لننتقل الى موضوع", "change the topic", "change the subject",
            )):
                return "explicit_switch"
            if any(marker in user for marker in (
                "نرجع الى موضوع", "نعود الى موضوع", "العودة الى موضوع",
                "ارجع الى موضوع", "نرجع لموضوع", "نعود لموضوع",
                "back to", "return to",
            )):
                return "restore"
            return ""

        boundaries = [
            (index, boundary(item))
            for index, item in enumerate(substantive)
            if boundary(item)
        ]
        if not boundaries:
            return substantive[-1:]

        latest_index, latest_kind = boundaries[-1]
        if latest_kind == "restore":
            # A return points back to a prior branch. Do not append the
            # intervening branch to the restored topic's history.
            restored_target = str(substantive[latest_index].get("target") or "").strip()
            if restored_target:
                normalized_target = restored_target.casefold()
                matching_indices = [
                    index for index, item in enumerate(substantive[:latest_index])
                    if str(item.get("target") or "").strip().casefold()
                    == normalized_target
                ]
                if matching_indices:
                    # Locate the most recent start of this exact topic before
                    # the return, then stop at the next independent branch.
                    matching_starts = [
                        index for index in matching_indices
                        if boundary(substantive[index]) in {"new_independent", "explicit_switch"}
                    ]
                    segment_start = matching_starts[-1] if matching_starts else matching_indices[0]
                    segment_end = next(
                        (
                            index for index, kind in boundaries
                            if index > segment_start and index < latest_index
                            and kind in {"new_independent", "explicit_switch"}
                        ),
                        latest_index,
                    )
                    selected = [
                        item for item in substantive[segment_start:segment_end]
                        if (
                            str(item.get("target") or "").strip().casefold()
                            == normalized_target
                            or (
                                not str(item.get("target") or "").strip()
                                and boundary(item) not in {"new_independent", "explicit_switch"}
                            )
                        )
                    ]
                    return selected or [substantive[matching_indices[-1]]]
            # Targetless social returns use ordinal/relational wording rather
            # than a canonical entity target. Resolve that wording against the
            # chronological branch starts, including an initial branch whose
            # legacy transition was ambiguous.
            restore_request = normalized_user(substantive[latest_index])
            branch_starts = [0]
            branch_starts.extend(
                index for index, kind in boundaries
                if index > 0 and kind in {"new_independent", "explicit_switch"}
            )
            branch_starts = sorted(set(
                index for index in branch_starts if index < latest_index
            ))
            if branch_starts:
                if any(marker in restore_request for marker in (
                    "الاول", "الأول", "الرئيسي", "الرئيسيه", "الاصلي", "الأصلي", "first",
                )):
                    segment_start = branch_starts[0]
                elif any(marker in restore_request for marker in (
                    "الثاني", "الثانى", "second",
                )) and len(branch_starts) > 1:
                    segment_start = branch_starts[1]
                elif any(marker in restore_request for marker in (
                    "السابق", "السابقه", "previous",
                )) and len(branch_starts) > 1:
                    segment_start = branch_starts[-2]
                else:
                    segment_start = branch_starts[-2] if len(branch_starts) > 1 else branch_starts[-1]
                segment_end = next(
                    (
                        index for index, kind in boundaries
                        if index > segment_start and index < latest_index
                        and kind in {"new_independent", "explicit_switch"}
                    ),
                    latest_index,
                )
                return substantive[segment_start:segment_end]
            return substantive[latest_index:]

        # The newest independent/switch boundary starts the active branch.
        # Crucially, a later RESTORE is handled above rather than concatenating
        # the restored branch with the branch that was left.
        return substantive[latest_index:]
    def _answer_dialogue_history(
        self,
        text: str,
        response_mode: str,
        exchanges: list[dict],
    ) -> dict:
        """Answer a dialogue-history request without routing it as project work."""
        state = getattr(self.dialogue_memory, "state", None) if self.dialogue_memory else None
        current_session_id = str(getattr(state, "session_id", "") or "")
        normalized_history_query = str(text or "").casefold()
        allow_untagged_legacy = response_mode == "answer" or (
            response_mode == "summary"
            and not any(marker in normalized_history_query for marker in (
                "ماذا كنا نقول", "ماذا قلنا", "ما كنا نقول", "ما كنا نتحدث",
            ))
        )
        relevant = [
            item for item in exchanges
            if str(item.get("context_kind") or "").casefold()
            not in {"work", "system"}
            and (
                str(item.get("context_kind") or "").casefold() != "execution"
                or str(item.get("conversation_domain") or "").casefold() == "technical"
            )
            and str(item.get("conversation_domain") or "").casefold()
            not in {"work", "system", "execution"}
            and (
                not current_session_id
                or str(item.get("session_id") or "") == current_session_id
                or (allow_untagged_legacy and (
                    not str(item.get("session_id") or "").strip()
                    and str(item.get("context_kind") or "").casefold()
                    not in {"work", "system", "execution"}
                ))
            )
        ][-32:]

        base = {
            "status": "success",
            "intent": Intent.MEMORY_DUMP,
            "source": "dialogue_memory",
            "executed": False,
            "dialogue_response_mode": response_mode,
        }
        if response_mode == "last_question":
            question_starts = (
                "هل ", "ما ", "ماذا ", "كيف ", "لماذا ", "من ", "أين ",
                "اين ", "متى ", "كم ", "أي ", "اي ", "ماهو ", "ما هي ",
            )
            last_question = next(
                (
                    str(item.get("user") or "").strip()
                    for item in reversed(relevant)
                    if str(item.get("user") or "").strip()
                    and (
                        "؟" in str(item.get("user") or "")
                        or "?" in str(item.get("user") or "")
                        or str(item.get("user") or "").strip().casefold().startswith(question_starts)
                    )
                ),
                "",
            )
            if not last_question:
                return {
                    **base,
                    "status": "needs_clarification",
                    "text": "لا أجد سؤالًا صريحًا في سجل الحوار القريب؛ لن أستبدله برسالة عادية.",
                }
            return {
                **base,
                "text": f"آخر سؤال طرحته عليّ كان: «{last_question}».",
                "last_user_message": last_question,
            }

        if not relevant:
            return {
                **base,
                "status": "needs_clarification",
                "text": "لا يوجد سجل حوار كافٍ للإجابة عن هذا الطلب.",
            }

        if response_mode == "transcript":
            return {
                **base,
                "text": "نص الحوار المسجل:\n"
                + "\n".join(self._format_dialogue_exchanges(relevant)),
                "dialogue_turns": relevant,
            }

        archive = []
        for item in relevant:
            archive.append(
                "المستخدم: " + str(item.get("user") or "").strip()
                + "\nالوكيل: " + str(item.get("assistant") or "").strip()
            )
        # History recall is a provenance-sensitive operation: do not ask an
        # unconstrained language model to reconstruct events from a transcript.
        # Render only the exact bounded exchanges present in DialogueMemory.
        if response_mode == "answer":
            query = str(text or "").casefold()
            matched = [
                item for item in relevant
                if any(
                    token and len(token) > 2
                    and token in " ".join((
                        str(item.get("target") or ""),
                        str(item.get("user") or ""),
                        str(item.get("assistant") or ""),
                    )).casefold()
                    for token in query.split()
                )
            ]
            selected = matched[-3:]
            if not selected:
                return {
                    **base,
                    "status": "needs_clarification",
                    "text": "لا أجد في سجل الحوار المحفوظ تفاصيل موثوقة عن هذا الموضوع؛ لن أخمّن.",
                }
            return {
                **base,
                "text": "بحسب سجل الحوار المحفوظ:\n"
                + "\n".join(self._format_dialogue_exchanges(selected)),
                "dialogue_turns": selected,
            }

        if response_mode == "summary":
            # Requests explicitly asking what was said in previous replies need
            # the recent recorded exchanges, not only the active branch. The
            # branch-only view remains appropriate for a plain current-state
            # summary, where mixing independent topics would be misleading.
            normalized_query = normalize_text(text)
            whole_dialogue_summary = any(marker in normalized_query for marker in (
                "منذ البداية", "منذ بدايه", "من بداية الحوار", "من بداية النقاش",
                "من اول الحوار", "من أول الحوار", "منذ أول الحوار",
                "الموضوعين", "موضوعين", "بالترتيب", "من البداية حتى الآن",
                "هذا الحوار", "لهذا الحوار", "الحوار الحالي بالكامل",
            ))
            recall_recent_exchanges = whole_dialogue_summary or any(marker in normalized_query for marker in (
                "الردود السابقة", "الردود السابقه", "قبل قليل",
                "ماذا كنا نقول", "ماذا قلنا", "ما كنا نقول",
                "بما كنا", "كنا نناقش", "كنا نتحدث",
                "الاختبار المركب", "اختبارنا", "لخص الاختبار",
                "ملخص الاختبار", "الذي اجريناه", "الذي أجريناه",
            ))
            if normalized_query.strip() in {"اكتب ملخص", "اكتب ملخصا", "لخص", "ملخص"}:
                recall_recent_exchanges = True
            branch = (
                relevant[-12:]
                if whole_dialogue_summary
                else (
                    relevant[-12:]
                    if recall_recent_exchanges
                    else self._latest_dialogue_branch(relevant)[-5:]
                )
            )
            if recall_recent_exchanges:
                meaningful_branch = [
                    item for item in branch
                    if not self._is_social_filler_exchange(item)
                ]
                if meaningful_branch:
                    branch = meaningful_branch[-6:]
                elif branch:
                    return {
                        **base,
                        "text": (
                            "سجل الحوار المتاح هنا يتكون من تحيات وتبادل قصير عن الحال؛ "
                            "لم نحدد موضوعًا فعليًا للنقاش بعد."
                        ),
                        "dialogue_turns": [],
                    }
                lines = []
                for item in branch:
                    user = " ".join(str(item.get("user") or "").split())
                    assistant = " ".join(str(item.get("assistant") or "").split())
                    if not user and not assistant:
                        continue
                    # Compact each exchange into its subject and recorded
                    # takeaway; do not render a role-labelled transcript.
                    line = f"- ناقشنا: {user[:130]}"
                    if assistant:
                        takeaway = assistant.split("。", 1)[0].split(". ", 1)[0].strip()
                        if len(takeaway) > 160:
                            takeaway = takeaway[:157].rstrip() + "..."
                        line += f"؛ الخلاصة المسجلة: {takeaway}"
                    lines.append(line)
                return {
                    **base,
                    "text": "ملخص موثّق للحوار المسجّل:\n" + "\n".join(lines),
                    "dialogue_turns": branch[-6:],
                }

            last = branch[-1] if branch else {}
            active_topic = str(
                getattr(state, "last_topic", None)
                or last.get("target")
                or ""
            ).strip()
            summary_lines = []
            if active_topic:
                summary_lines.append(f"- الموضوع النشط: {active_topic}")
            else:
                summary_lines.append("- الموضوع النشط: حوار عام؛ لم يُسجّل له عنوان مستقل.")
            user = " ".join(str(last.get("user") or "").split())
            assistant = " ".join(str(last.get("assistant") or "").split())
            if user:
                excerpt = user[:180] + ("…" if len(user) > 180 else "")
                summary_lines.append(f"- آخر رسالة واردة: {excerpt}")
            if assistant:
                excerpt = assistant[:220] + ("…" if len(assistant) > 220 else "")
                summary_lines.append(f"- نقطة التوقف: {excerpt}")
            return {
                **base,
                "text": "ملخص الحوار الحالي:\n" + "\n".join(summary_lines),
                "dialogue_turns": branch,
            }

        task = (
            "أجب عن طلب المستخدم الحالي بالاعتماد حصريًا على سجل الحوار المرفق.\n"
            "لا تضف أحداثًا غير موجودة.\n\n"
            f"طلب المستخدم الحالي: {text}\n\n"
            "سجل الحوار السابق:\n" + "\n\n".join(archive)
        )
        try:
            generated = gateway_ask(
                task,
                system=(
                    "أنت تسترجع حوارًا سابقًا. التزم بالسجل فقط. "
                    "لا تضف أحداثًا غير موجودة. أجب مباشرة وبالعربية."
                ),
                max_tokens=900,
                temperature=0.2,
                routing_text=text,
            )
            answer = str((generated or {}).get("text") or "").strip()
            if (generated or {}).get("status") == "success" and answer:
                return {**base, "text": answer}
        except Exception:
            pass

        # Offline/provider-failure fallback: compact and explicitly bounded,
        # not a full transcript and not a fabricated semantic interpretation.
        if response_mode == "summary":
            lines = []
            seen = set()
            for item in relevant[-5:]:
                user_turn = " ".join(str(item.get("user") or "").split())
                if not user_turn or user_turn.casefold() in seen:
                    continue
                seen.add(user_turn.casefold())
                assistant_turn = " ".join(str(item.get("assistant") or "").split())
                line = f"- طلب المستخدم: {user_turn[:110]}"
                if assistant_turn:
                    first_sentence = assistant_turn.split("。", 1)[0].split(". ", 1)[0]
                    line += f"؛ رد الوكيل باختصار: {first_sentence[:110]}"
                lines.append(line)
            return {
                **base,
                "text": "ملخص موجز من سجل الحوار المتاح:\n" + "\n".join(lines),
                "summary_fallback": True,
            }
        return {
            **base,
            "status": "needs_clarification",
            "text": "تعذر تحديد الإجابة من سجل الحوار المتاح دون تخمين.",
        }

    @staticmethod
    def _format_dialogue_exchanges(exchanges: list[dict]) -> list[str]:
        """Render bounded recall with explicit user/assistant roles."""
        lines = []
        for item in exchanges:
            user = str(item.get("user") or "").strip()
            assistant = str(item.get("assistant") or "").strip()
            if user:
                lines.append(f"- المستخدم: {user}")
            if assistant:
                lines.append(f"  الوكيل: {assistant[:1200]}")
        return lines

    def _classify_context_transition(
        self,
        mode: str,
        parsed: dict,
        *,
        text: str = "",
    ) -> ContextTransition:
        """Classify the current semantic subject against dialogue-owned state."""
        parsed = parsed or {}
        entity_type = str(parsed.get("entity_type", "")).upper()
        target = str(parsed.get("target") or "").strip()
        intent = getattr(parsed.get("intent"), "value", parsed.get("intent"))
        pattern = parsed.get("semantic_pattern")
        active_context = None
        if self.dialogue_memory:
            get_active_context = getattr(
                self.dialogue_memory,
                "active_context_entity",
                None,
            )
            if callable(get_active_context):
                active_context = get_active_context()
        active_topic = (
            active_context.get("entity")
            if isinstance(active_context, dict)
            else None
        )

        conversation_act = parsed.get("conversation_act")
        if parsed.get("semantic_pattern") == "COMPOUND_DIALOGUE_REQUEST":
            return ContextTransition.NEW_INDEPENDENT
        # Reference-only wording belongs to the dialogue-memory owner. Do not
        # let the generic explanation parser turn "وضّح الفكرة" or "اشرح هذا
        # الأمر" into a new executable topic; without an active topic, keep it
        # unresolved so no stale/global index can supply one implicitly.
        generic_reference_target = self._normalize_transition_text(target) in {
            "هذا", "هذه", "ذلك", "تلك", "هذا الامر", "ذلك الامر",
            "الامر", "الفكرة", "الموضوع", "الشرح", "النقطة",
        }
        if (
            (not target and entity_type == "REFERENCE")
            or generic_reference_target
        ) and conversation_act not in {
            "TOPIC_RETURN", "CONVERSATION_HISTORY_QUERY", "SOCIAL_ACKNOWLEDGEMENT",
            "CORRECTION",
        }:
            return (
                ContextTransition.REFERENCE
                if active_topic
                else ContextTransition.AMBIGUOUS
            )
        if active_topic and (
            entity_type == "ELABORATION"
            or conversation_act in {
                "TOPIC_CONTINUATION_QUERY", "SIMPLIFICATION_REQUEST",
            }
        ):
            return ContextTransition.CONTINUE
        normalized_request = str(text or "").casefold()
        explicit_explain_markers = (
            "اشرح", "شرح", "وضح", "عرّف", "عرف", "ما هو", "ماهي",
            "حدثني عن", "دعنا نتحدث عن", "let's discuss", "explain",
        )
        explicit_resume_markers = (
            "اكمل", "أكمل", "استكمل", "تابع", "واصل", "من نقطة التوقف",
            "ارجع", "نرجع", "عد إلى", "عد الى", "continue", "resume",
        )
        starts_explicit_explanation = (
            target
            and any(marker in normalized_request for marker in explicit_explain_markers)
            and not any(marker in normalized_request for marker in explicit_resume_markers)
        )
        if (
            starts_explicit_explanation
            and active_topic
            and self._same_topic(target, active_topic)
            and conversation_act != "TOPIC_RETURN"
        ):
            # "Explain X in detail" starts a fresh answer even if a persisted
            # session happened to leave X as the active topic. Only explicit
            # continuation/return language may resume the old stopping point.
            return ContextTransition.EXPLICIT_SWITCH
        if parsed.get("semantic_pattern") == "GENERIC_TOPIC_REFERENCE":
            return (
                ContextTransition.RESTORE
                if conversation_act == "TOPIC_RETURN"
                else ContextTransition.REFERENCE
            )
        if intent in _AGENT_SELF_INTENTS:
            return ContextTransition.NEW_INDEPENDENT
        if conversation_act == "TOPIC_RETURN":
            # A named return must resolve that exact topic. Never fall back to
            # whichever branch happens to be last in context_history.
            if target and self.dialogue_memory:
                get_topic = getattr(self.dialogue_memory, "context_for_topic", None)
                named_context = get_topic(target) if callable(get_topic) else None
                if named_context:
                    return ContextTransition.RESTORE
                if active_topic and self._same_topic(target, active_topic):
                    return ContextTransition.CONTINUE
                return ContextTransition.AMBIGUOUS
            get_previous = getattr(
                self.dialogue_memory,
                "previous_context_entity",
                None,
            ) if self.dialogue_memory else None
            return (
                ContextTransition.RESTORE
                if callable(get_previous) and get_previous()
                else ContextTransition.AMBIGUOUS
            )
        if conversation_act in {"CORRECTION", "COMPOUND_REFERENCE"}:
            return (
                ContextTransition.CONTINUE
                if active_topic else ContextTransition.AMBIGUOUS
            )
        if conversation_act == "CONVERSATION_CONTINUATION":
            # A named, different subject is an explicit branch switch even if
            # a semantic marker such as "نقطة" made the utterance look like a
            # continuation. Prefer a matching archived branch when available.
            if target and active_topic and not self._same_topic(target, active_topic):
                get_topic = getattr(self.dialogue_memory, "context_for_topic", None) if self.dialogue_memory else None
                named_context = get_topic(target) if callable(get_topic) else None
                return (
                    ContextTransition.RESTORE
                    if named_context else ContextTransition.EXPLICIT_SWITCH
                )
            if target and not active_topic:
                return ContextTransition.NEW_INDEPENDENT
            return (
                ContextTransition.CONTINUE
                if active_topic else ContextTransition.AMBIGUOUS
            )
        if is_style_act(conversation_act) and not target:
            return (
                ContextTransition.CONTINUE
                if active_topic else ContextTransition.AMBIGUOUS
            )
        # A generic CASUAL_CONVERSATION fallback is weaker than a structural
        # reference/elaboration marker or an explicit FOLLOW_UP mode.
        if (
            is_social_act(conversation_act)
            and str(conversation_act).upper() != "CASUAL_CONVERSATION"
            and not target
        ):
            return ContextTransition.AMBIGUOUS

        if entity_type == "REFERENCE":
            return (
                ContextTransition.REFERENCE
                if active_topic else ContextTransition.AMBIGUOUS
            )

        if target:
            if active_topic and self._same_topic(target, active_topic):
                return ContextTransition.CONTINUE
            previous_context = None
            if self.dialogue_memory:
                get_context = getattr(
                    self.dialogue_memory,
                    "context_for_topic",
                    None,
                )
                if callable(get_context):
                    previous_context = get_context(target)
                pending_topic = getattr(
                    self.dialogue_memory,
                    "pending_topic",
                    None,
                )
            else:
                pending_topic = None
            valid_target = entity_type not in {
                "", "UNKNOWN", "REFERENCE", "ELABORATION",
            }
            if valid_target and (
                previous_context
                or self._same_topic(target, pending_topic)
            ):
                return ContextTransition.RESTORE
            return (
                ContextTransition.EXPLICIT_SWITCH
                if active_topic else ContextTransition.NEW_INDEPENDENT
            )

        if entity_type == "ELABORATION":
            return (
                ContextTransition.CONTINUE
                if active_topic else ContextTransition.AMBIGUOUS
            )

        if pattern in {"CONTINUE_WORK", "GIVE_EXAMPLE"}:
            return (
                ContextTransition.CONTINUE
                if active_topic else ContextTransition.AMBIGUOUS
            )

        if mode == "FOLLOW_UP":
            if not active_topic:
                return ContextTransition.AMBIGUOUS
            previous_intent = getattr(
                getattr(self.dialogue_memory, "state", None),
                "last_intent",
                None,
            )
            previous_intent = getattr(previous_intent, "value", previous_intent)
            return (
                ContextTransition.CONTINUE
                if intent and intent == previous_intent
                else ContextTransition.REFERENCE
            )

        if mode == "CHAT" and intent in _NON_EXECUTABLE_INTENTS:
            return ContextTransition.AMBIGUOUS

        incomplete = is_incomplete({
            "intent": intent or "",
            "target": "",
            "entity": {"value": ""},
        })
        if incomplete or not intent:
            return ContextTransition.AMBIGUOUS

        return ContextTransition.NEW_INDEPENDENT

    @staticmethod
    def _same_topic(left, right) -> bool:
        def normalize_topic(value):
            return " ".join(
                str(value).casefold().strip(" \t\r\n.,،؛:!?؟()[]{}\"'").split()
            )
        return normalize_topic(left) == normalize_topic(right)

    def _history_for_transition(
        self,
        transition: ContextTransition,
        parsed: dict,
    ) -> list:
        """Build bounded prompt history from durable dialogue exchanges.

        The visible turn list is intentionally short. Prefer the exchange archive
        when selecting a branch so recent relevant turns survive transcript rollover.
        Work/system exchanges are never admitted to a dialogue prompt.
        """
        if not self.dialogue_memory:
            return []

        state = getattr(self.dialogue_memory, "state", None)
        history = getattr(state, "history", []) if state is not None else []
        exchanges = getattr(state, "exchange_archive", []) if state is not None else []

        current_session_id = str(getattr(state, "session_id", "") or "")

        def allowed(item):
            if (
                not isinstance(item, dict)
                or item.get("recall_only")
                or item.get("state_boundary_only")
            ):
                return False
            kind = str(item.get("context_kind") or "").casefold()
            domain = str(item.get("conversation_domain") or "").casefold()
            item_session_id = str(item.get("session_id") or "")
            # Fail closed when a session ID is available: untagged legacy turns
            # cannot be proven to belong to this session.
            same_session = (
                not current_session_id
                or item_session_id == current_session_id
            )
            # Keep educational technical exchanges that were routed through
            # execution, but never admit actual execution/system state into a
            # dialogue prompt. The domain is authoritative for this distinction.
            safe_kind = kind not in {"work", "system"} and (
                kind != "execution" or domain == "technical"
            )
            safe_domain = domain not in {"work", "system", "execution"}
            return safe_kind and safe_domain and same_session

        # A state boundary ends the implicit continuation branch. Keep older
        # exchanges available only for an explicit restore/recovery request;
        # otherwise they must not leak into a new independent dialogue path.
        if transition not in {
            ContextTransition.RESTORE,
            ContextTransition.EXPLICIT_SWITCH,
        }:
            latest_boundary = max(
                (
                    index for index, item in enumerate(exchanges or [])
                    if isinstance(item, dict) and item.get("state_boundary_only")
                ),
                default=-1,
            )
            if latest_boundary >= 0:
                exchanges = list(exchanges or [])[latest_boundary + 1:]

        recovery_mode = str(
            ((parsed or {}).get("response_attributes") or {}).get("dialogue_recovery", "")
        ).casefold()
        if recovery_mode == "interrupted_branch":
            def is_recovery_request(item):
                user_text = str(item.get("user") or "").casefold()
                return (
                    "استرجع النقاش الذي انقطع" in user_text
                    or "استرجع الحوار الذي انقطع" in user_text
                    or "recover the interrupted discussion" in user_text
                )

            valid = [
                item for item in (exchanges or [])
                if allowed(item) and not is_recovery_request(item)
            ]

            def effective_transition(item):
                transition_value = str(
                    item.get("context_transition") or ""
                ).casefold()
                if transition_value in {"new_independent", "explicit_switch", "restore"}:
                    return transition_value
                user_text = str(item.get("user") or "")
                if self._is_explicit_topic_switch(user_text):
                    return "explicit_switch"
                if self._is_explicit_independent_topic(user_text, {}):
                    return "new_independent"
                normalized = user_text.casefold().replace("أ", "ا").replace("إ", "ا")
                if any(marker in normalized for marker in (
                    "نعود إلى", "نعود الى", "نرجع إلى", "نرجع الى",
                    "عدنا إلى", "عدنا الى", "العودة إلى", "العودة الى",
                    "لنعد إلى", "لنعد الى", "ارجع إلى", "ارجع الى",
                    "الرجوع إلى", "الرجوع الى", "عودة إلى", "عودة الى",
                    "back to ", "return to ",
                )):
                    return "restore"
                return transition_value

            boundaries = [
                (index, effective_transition(item))
                for index, item in enumerate(valid)
                if effective_transition(item) in {
                    "new_independent", "explicit_switch", "restore"
                }
            ]
            if boundaries:
                latest_boundary, latest_kind = boundaries[-1]
                if latest_kind == "restore":
                    # A later explicit return reactivates the earlier branch.
                    # Continue from that restored branch, not the intervening one.
                    selected = valid[latest_boundary:]
                elif len(boundaries) > 1:
                    previous_boundary = boundaries[-2][0]
                    selected = valid[previous_boundary:latest_boundary]
                elif latest_boundary > 0:
                    # A legacy archive may have one explicit boundary after
                    # untagged earlier exchanges; those exchanges are the best
                    # available candidate for the interrupted branch.
                    selected = valid[:latest_boundary]
                else:
                    # With only one known branch there is no older branch to
                    # distinguish. Fall back to that branch rather than return
                    # an empty history and trigger a clarification loop.
                    selected = valid[-4:]
            else:
                # Legacy archives may lack transition metadata. Prefer the last
                # few dialogue exchanges, excluding work and failed recovery turns.
                selected = valid[-4:]
            if selected:
                return self._exchange_history_turns(selected[-4:])[-8:]
            return []

        topic = None
        if transition in {ContextTransition.RESTORE, ContextTransition.EXPLICIT_SWITCH}:
            topic = (parsed or {}).get("target")
        elif transition.value in CONTEXTUAL_TRANSITIONS:
            get_active_context = getattr(
                self.dialogue_memory, "active_context_entity", None
            )
            active = get_active_context() if callable(get_active_context) else None
            topic = active.get("entity") if isinstance(active, dict) else None

        if transition == ContextTransition.AMBIGUOUS and is_social_act(
            (parsed or {}).get("conversation_act")
        ):
            branch = self._latest_dialogue_branch([
                item for item in (exchanges or []) if allowed(item)
            ])
            selected = [item for item in branch if not item.get("target")][-8:]
            if selected:
                return self._exchange_history_turns(selected)[-8:]
            return [
                turn for turn in (history or [])
                if allowed(turn) and not turn.get("target")
            ][-8:]

        if transition == ContextTransition.AMBIGUOUS and str(
            (parsed or {}).get("conversation_act") or ""
        ).upper() == "CONVERSATION_CONTINUATION":
            selected = self._latest_dialogue_branch(
                [item for item in (exchanges or []) if allowed(item)]
            )[-8:]
            if selected:
                return self._exchange_history_turns(selected)[-8:]
            return [turn for turn in (history or []) if allowed(turn)][-8:]

        if not topic:
            # General conversation branches may not have a canonical entity.
            # For an authorized continuation/return, use recent dialogue exchanges
            # rather than dropping context solely because no entity was extracted.
            if transition in CONTEXTUAL_TRANSITIONS:
                selected = self._latest_dialogue_branch(
                    [item for item in (exchanges or []) if allowed(item)]
                )[-8:]
                if selected:
                    return self._exchange_history_turns(selected)[-8:]
                return [turn for turn in (history or []) if allowed(turn)][-8:]
            return []

        selected = [
            item for item in (exchanges or [])
            if allowed(item) and item.get("target")
            and self._same_topic(item.get("target"), topic)
        ][-8:]
        if selected:
            return self._exchange_history_turns(selected)[-8:]

        # A friendly/social branch often has no canonical entity target. Its
        # chronological opener is therefore the branch label used by ordinal
        # recall; recover the bounded segment from that opener to the next
        # independent-topic boundary instead of falling back to an empty history.
        if transition == ContextTransition.RESTORE and topic:
            normalized_topic = self._normalize_transition_text(topic)
            matching_index = next(
                (
                    index for index, item in enumerate(exchanges or [])
                    if allowed(item)
                    and self._normalize_transition_text(item.get("user") or "") == normalized_topic
                ),
                None,
            )
            if matching_index is not None:
                segment = []
                for item in (exchanges or [])[matching_index:]:
                    if not allowed(item):
                        continue
                    relation = str(item.get("context_transition") or "").casefold()
                    if segment and relation in {"new_independent", "explicit_switch", "restore"}:
                        break
                    segment.append(item)
                if segment:
                    return self._exchange_history_turns(segment)[-8:]

        # Compatibility with checkpoints created before exchange archives.
        return [
            turn for turn in (history or [])
            if allowed(turn) and turn.get("target")
            and self._same_topic(turn.get("target"), topic)
        ][-8:]

    @staticmethod
    def _exchange_history_turns(exchanges: list[dict]) -> list[dict]:
        """Convert archived exchanges to the standard prompt-history shape."""
        turns = []
        for exchange in exchanges:
            if not isinstance(exchange, dict):
                continue
            shared = {
                "mode": exchange.get("mode"),
                "intent": exchange.get("intent"),
                "target": exchange.get("target"),
                "conversation_domain": exchange.get("conversation_domain", "general"),
                "conversation_act": exchange.get("conversation_act", "NONE"),
                "context_kind": exchange.get("context_kind", "unknown"),
            }
            user_text = str(exchange.get("user") or "").strip()
            assistant_text = str(exchange.get("assistant") or "").strip()
            if user_text:
                turns.append({"role": "user", "content": user_text, **shared})
            if assistant_text:
                turns.append({"role": "assistant", "content": assistant_text, **shared})
        return turns

    # Compatibility entry points
    # --------------------------------------------------------

    def _handle_task(self, text: str) -> dict:
        return self.process(text)

    def _handle_system(self, text: str) -> dict:
        return self.process(text)

    def _handle_follow_up(self, text: str) -> dict:
        return self.process(text)

    def _handle_chat(
        self,
        text: str,
        mode: str,
        *,
        parsed: dict | None = None,
        user_question: str | None = None,
        history: list | None = None,
    ) -> dict:
        result = {}
        try:
            intent = (parsed or {}).get("intent")
            response_attributes = (parsed or {}).get("response_attributes") or {}
            compound_request = bool(response_attributes.get("compound_request"))
            normalized_question = self._normalize_transition_text(user_question or text)
            general_scope_markers = (
                "بصفة عامة", "بشكل عام", "بصورة عامة", "عموما",
                "محادثة ودية", "محادثه وديه", "دردشة ودية", "دردشه وديه",
                "خارج بنية المشروع", "خارج نبية المشروع",
                "لا نتحدث عن مشروع", "لا نتحدث عن مشروع cyberlab",
                "ليس عن مشروع", "بلا علاقة بالمشروع",
            )
            explicitly_general_scope = any(
                marker in normalized_question for marker in general_scope_markers
            )
            # One compound message belongs to the ordinary conversational responder.
            # Do not inject agent-self or project knowledge because individual items
            # mention the agent, Python, or project-adjacent vocabulary.
            self_knowledge = (
                build_agent_self_knowledge(intent)
                if intent in _AGENT_SELF_INTENTS
                and not compound_request
                and not explicitly_general_scope
                else None
            )
            scope_question = " ".join(
                part for part in (
                    str(user_question or text),
                    str((parsed or {}).get("target") or ""),
                ) if part
            )
            project_scope = (
                "general"
                if compound_request or explicitly_general_scope
                else resolve_project_scope(scope_question, intent=intent)
            )
            authorized_project_context = False
            context_domain = str(
                (parsed or {}).get("conversation_domain") or ""
            ).casefold()
            # A project branch is explicit authorization to resolve an
            # otherwise ambiguous follow-up against this project. It cannot
            # override a question explicitly scoped as generic, external, or
            # historical, nor a compound/general conversation.
            if (
                not compound_request
                and not explicitly_general_scope
                and context_domain == "project"
                and project_scope not in {
                    ProjectScope.EXTERNAL_PROJECT,
                    ProjectScope.GENERIC_PROJECT,
                    ProjectScope.HISTORICAL_PROJECT,
                }
            ):
                project_scope = ProjectScope.CURRENT_PROJECT
                authorized_project_context = True

            # Architecture is a knowledge type too; excluding it silently
            # sent layer questions to generic provider prose.
            project_knowledge = None
            knowledge_type = QuestionClassifier.classify(user_question or text)
            if (
                not compound_request
                and not explicitly_general_scope
                and user_question
                and (
                    intent in _AGENT_SELF_INTENTS
                    or knowledge_type in {
                        "component", "relationship", "execution", "file",
                        "architecture",
                    }
                )
                and project_scope == ProjectScope.CURRENT_PROJECT
            ):
                try:
                    if authorized_project_context:
                        project_knowledge = retrieve_for_question(
                            user_question,
                            authorized_current_project=True,
                        )
                    else:
                        project_knowledge = retrieve_for_question(user_question)
                except Exception as exc:
                    # Preserve a truthful, evidence-empty result instead of
                    # silently falling through to an apparently grounded LLM
                    # answer.
                    project_knowledge = {
                        "type": knowledge_type,
                        "components": [],
                        "current_project_knowledge": True,
                        "retrieval_error": type(exc).__name__,
                        "recommendation": (
                            "تعذر استرجاع أدلة المشروع؛ صرّح بعدم كفاية الأدلة "
                            "ولا تستبدلها بوصف عام."
                        ),
                    }
            
            system, prompt = build_chat_prompt(
                text,
                list(history or []),
                agent_self_knowledge=self_knowledge,
                project_knowledge=project_knowledge,
                project_scope=project_scope,
                conversation_semantics={
                    "intent": getattr(
                        (parsed or {}).get("intent"),
                        "value",
                        (parsed or {}).get("intent"),
                    ),
                    "conversation_domain": (parsed or {}).get(
                        "conversation_domain", "general"
                    ),
                    "conversation_act": (parsed or {}).get(
                        "conversation_act", "NONE"
                    ),
                    "response_attributes": (parsed or {}).get(
                        "response_attributes", {}
                    ),
                },
            )
            if (parsed or {}).get("response_attributes", {}).get("compound_request"):
                system = str(system or "") + (
                    "\n\nتعليمات للطلب المركب: أجب عن كل بند مرقّم بالترتيب نفسه، "
                    "ولا تسقط أي بند حتى لو تكرر سياقه. ميّز بوضوح بين الحديث الودي "
                    "والسؤال التقني وتصحيح الافتراض الخاطئ. صحّح الافتراضات الخاطئة "
                    "بشرح موجز، ولا تستبدل الإجابة المطلوبة بشرح عن بنية الوكيل أو "
                    "قدراته إلا إذا كان ذلك بندًا صريحًا في السؤال."
                )

            result = gateway_ask(
                prompt,
                system=system,
                # Reasoning can consume the full budget before GPT-5 emits
                # visible text; grounded self-descriptions need extra headroom.
                max_tokens=4000 if self_knowledge else 1600,
                temperature=0.7,
                routing_text=text,
            )

            if result.get("status") != "success":
                raise RuntimeError(
                    result.get("message")
                )

            reply = result.get("text", "")

            if not reply:
                raise ValueError("empty")

            return {
                "status": "success",
                "intent": (parsed or {}).get("intent", mode.lower()),
                "text": reply,
                "mode": mode,
                "source": "llm",
                "provider_used": result.get("provider_used"),
                "provider_chain": result.get(
                    "provider_chain",
                    [],
                ),
                "model": result.get("model"),
                "executed": False,
            }

        except Exception as e:
            gateway_error = (
                result.get("error")
                if isinstance(result, dict)
                else None
            )

            # If generation is unavailable, use the bounded local composer for
            # ordinary conversation continuations. It quotes only the authorized
            # dialogue history and explicitly labels the result as local; it
            # cannot answer project, operational, or unsupported factual turns.
            local_intent = str(
                getattr((parsed or {}).get("intent"), "value", (parsed or {}).get("intent")) or ""
            ).casefold()
            local_act = str((parsed or {}).get("conversation_act") or "").upper()
            local_domain = str((parsed or {}).get("conversation_domain") or "general").casefold()
            # Social openings/follow-ups can be composed locally after a
            # provider failure. A continuation is eligible only when the local
            # responder classifies the authorized history as social-only and
            # returns the explicit friendly-reopen strategy. A real topic must
            # retain the safe last-point recovery below rather than pretending
            # that quoting its previous answer is a new continuation.
            local_fallback_acts = {
                "SOCIAL_OPENING", "CASUAL_CONVERSATION", "CASUAL_DISCUSSION",
                "PERSONAL_INTERACTION", "SOCIAL_FOLLOW_UP",
                "CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY",
            }
            local_history = list(history or [])
            local_history_is_dialogue = bool(local_history) and all(
                isinstance(turn, dict)
                and str(turn.get("conversation_domain") or "general").casefold()
                    in {"", "general", "social"}
                and str(turn.get("context_kind") or "dialogue").casefold()
                    not in {"work", "system", "execution"}
                for turn in local_history
            )
            if (
                local_intent in {"personal_chat", "discussion", "chat"}
                and local_domain in {"", "general", "social"}
                and local_act in local_fallback_acts
                and local_history_is_dialogue
            ):
                local_semantic = {
                    "conversation_act": local_act,
                    "conversation_domain": local_domain or "general",
                    "target": (parsed or {}).get("target") or "",
                    "response_attributes": (parsed or {}).get("response_attributes") or {},
                }
                local_result = answer_local_response(
                    user_question or text,
                    parsed,
                    local_semantic,
                    history=list(history or []),
                )
                if local_result is not None:
                    local_result = dict(local_result)
                    is_continuation = local_act in {
                        "CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY",
                    }
                    if (
                        is_continuation
                        and local_result.get("local_strategy") != "friendly_dialogue_reopen"
                    ):
                        # Preserve the established truthful recovery for a real
                        # topic when no provider can generate the next content.
                        local_result = None
                    if local_result is not None:
                        local_result["source"] = "local_dialogue_fallback"
                        local_result["mode"] = mode
                        local_result["executed"] = False
                        local_result["recovery"] = "provider_unavailable_local_dialogue"
                        local_result["provider_failure_code"] = (
                            str(gateway_error.get("code") or "")
                            if isinstance(gateway_error, dict)
                            else ""
                        )
                        if local_result.get("local_strategy") != "friendly_dialogue_reopen":
                            local_result["text"] = str(local_result.get("text") or "").rstrip() + (
                                "\n\nملاحظة: تعذر الحصول على رد من المزود؛ هذه متابعة محلية "
                                "مبنية على الحوار المحفوظ، وليست شرحًا جديدًا يعتمد على معرفة خارجية."
                            )
                        return local_result

            continuation = str((parsed or {}).get("conversation_act") or "").upper() in {
                "CONVERSATION_CONTINUATION", "TOPIC_CONTINUATION_QUERY",
            }
            branch = None
            if self.dialogue_memory:
                get_branch = getattr(self.dialogue_memory, "active_dialogue_branch", None)
                branch = get_branch() if callable(get_branch) else None
            if continuation and branch:
                # Provider failure must not erase locally recoverable dialogue
                # context. Return a memory-owned recovery response, not a fake
                # generated continuation and not a generic provider error.
                topic = str(branch.get("entity") or "").strip()
                last_point = str(branch.get("reference_text") or "").strip()
                details = []
                if topic:
                    details.append(f"الموضوع المحفوظ: {topic}.")
                if last_point:
                    details.append(f"آخر نقطة محفوظة في هذا الفرع: {last_point}")
                details.append(
                    "تعذر توليد شرح جديد لأن المزود غير متاح في هذه المحاولة. "
                    "حافظت على الفرع الحالي ولم أختلق محتوى جديدًا. "
                    "يمكنك طلب تلخيص النقاط المحفوظة أو إعادة المحاولة لاحقًا."
                )
                return {
                    "status": "needs_clarification",
                    "intent": (parsed or {}).get("intent", mode.lower()),
                    "text": "\n".join(details),
                    "mode": mode,
                    "source": "dialogue_memory",
                    "gateway_error": gateway_error,
                    "recovery": "provider_unavailable_preserved_dialogue",
                    "executed": False,
                }
            error_code = (
                str(gateway_error.get("code") or "").strip()
                if isinstance(gateway_error, dict)
                else ""
            )
            if error_code == "PRIVACY_EXTERNAL_BLOCKED":
                fallback = (
                    "حُجب إرسال هذا الطلب إلى مزود خارجي وفق فحص الخصوصية. "
                    "لم يُنفَّذ أي إجراء، ولم يُسجَّل رد مختلق."
                )
            elif error_code == "NO_PROVIDER_AVAILABLE":
                fallback = (
                    "لا يوجد حاليًا مزود ذكاء اصطناعي مهيأ ومتاح لإنتاج الرد. "
                    "لم أتمكن من متابعة الحوار في هذه المحاولة."
                )
            elif error_code == "TIMEOUT":
                fallback = (
                    "انتهت مهلة انتظار مزود الذكاء الاصطناعي قبل وصول رد صالح. "
                    "لم أتمكن من متابعة الحوار في هذه المحاولة."
                )
            elif error_code:
                fallback = (
                    "تعذر إنتاج رد صالح من مزود الذكاء الاصطناعي "
                    f"(رمز الخطأ: {error_code}). لم أعتبر رسالة الخطأ إجابة "
                    "ولم أضفها إلى سجل الحوار كأنها رد ناجح."
                )
            else:
                fallback = (
                    "تعذر إنتاج رد صالح في هذه المحاولة. لا تتوفر أدلة كافية "
                    "للجزم بأن السبب هو الاتصال أو إعدادات المزود."
                )

            return {
                "status": "error",
                "intent": (parsed or {}).get("intent", mode.lower()),
                "text": fallback,
                "mode": mode,
                "source": "fallback",
                "provider_used": (
                    result.get("provider_used")
                    if isinstance(result, dict)
                    else None
                ),
                "provider_chain": (
                    result.get("provider_chain", [])
                    if isinstance(result, dict)
                    else []
                ),
                "model": (
                    result.get("model")
                    if isinstance(result, dict)
                    else None
                ),
                "gateway_error": gateway_error,
                "error": error_code or str(e) or type(e).__name__,
                "executed": False,
            }

    def switch_topic(
        self,
        current_topic: str,
        new_input: str,
    ) -> dict:
        if self.dialogue_memory:
            self.dialogue_memory.save_pending(
                current_topic
            )

        return self.process(new_input)

    def restore_topic(self) -> dict:
        if self.dialogue_memory:
            topic = getattr(self.dialogue_memory, "pending_topic", None)
            if topic:
                context = getattr(self.dialogue_memory.state, "pending_context", None)
                if not isinstance(context, dict) or not context.get("entity"):
                    context = self.dialogue_memory.context_for_topic(topic)
                if not context:
                    return {
                        "status": "needs_clarification",
                        "intent": Intent.MEMORY_DUMP,
                        "source": "dialogue_memory",
                        "text": "لا أجد فرعًا محفوظًا موثوقًا لهذا الموضوع؛ لم أغيّر الموضوع النشط.",
                        "executed": False,
                    }
                result = dict(
                    self.process(
                        "استعادة الفرع الحواري المحفوظ",
                        _restore_context=context,
                    )
                )
                self.dialogue_memory.restore_pending()
                result.setdefault("topic", topic)
                return result

        return {
            "status": "success",
            "intent": "topic_restore",
            "text": "لا يوجد موضوع مؤجل.",
        }
