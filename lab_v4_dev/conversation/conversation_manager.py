"""
Conversation Manager — Series 10-A
Router رئيسي: يصنف الرسالة ويوجهها للمسار الصحيح.
"""
from lab_v4_dev.conversation.mode_detector import detect_mode
from lab_v4_dev.conversation.assistant_style import format_response, single_question
from lab_v4_dev.llm.prompt_builder import build_chat_prompt
from lab_v4_dev.llm.gateway import ask as gateway_ask


class ConversationManager:

    def __init__(self, orchestrator, dialogue_memory=None, dni=None):
        self.orchestrator     = orchestrator
        self.dialogue_memory  = dialogue_memory
        self.dni = dni

    def process(self, user_input: str) -> dict:
        mode = detect_mode(user_input)

        if mode == "TASK":
            result = self._handle_task(user_input)
        elif mode == "FOLLOW_UP":
            result = self._handle_follow_up(user_input)
        elif mode == "SYSTEM":
            result = self._handle_system(user_input)
        elif mode in ("CHAT", "QUESTION", "DISCUSSION"):
            result = self._handle_chat(user_input, mode)
        else:
            result = self._handle_task(user_input)

        # تطبيق AssistantStyle على النص النهائي
        if result.get("text"):
            text = format_response(result["text"], mode)
            text = single_question(text)
            result = dict(result)
            result["text"] = text

        if self.dni:
            self.dni.set_conversation_analysis({
                "intent": result.get("intent"),
                "mode": result.get("mode")
            })

        # تحديث DialogueMemory يحدث حصرياً من agent.run() لتفادي الاستدعاء المزدوج (BUG #6, DNI-7)
        return result

    def _handle_task(self, text: str) -> dict:
        return self.orchestrator.handle(text)

    def _handle_follow_up(self, text: str) -> dict:
        resolved = text
        if self.dialogue_memory:
            resolved = self.dialogue_memory.resolve_references(text)

        # إذا كانت متابعة حوارية فأرسلها إلى الـ LLM
        if any(x in resolved for x in (
            "لماذا",
            "ولماذا",
            "هل",
            "وماذا",
            "ماذا عن",
            "وأيهما",
            "ايهما",
            "تنصح",
            "ما دوره",
            "ما وظيفته",
            "كيف يعمل",
            "ما علاقته",
            "ما علاقة",
            "علاقته",
            "ما دوره",
            "ما وظيفته",
            "كيف يعمل"
        )):
            return self._handle_chat(resolved, "DISCUSSION")

        if resolved.startswith(("وماذا عن","ماذا عن","ثم ","ثم")):
            return self._handle_chat(resolved, "DISCUSSION")

        return self.orchestrator.handle(resolved)

    def _handle_system(self, text: str) -> dict:
        return self.orchestrator.handle(text)

    def _handle_chat(self, text: str, mode: str) -> dict:
        try:
            history = getattr(self.dialogue_memory, "last_list", []) if self.dialogue_memory else []
            system, prompt = build_chat_prompt(text, history)
            result = gateway_ask(prompt, system=system, max_tokens=300, temperature=0.7, routing_text=text)

            if result.get("status") != "success":
                raise RuntimeError(result.get("message"))

            reply = result.get("text", "")
            if not reply:
                raise ValueError("empty")
            return {
                "status": "success",
                "intent": mode.lower(),
                "text": reply,
                "mode": mode,
                "source": "llm",
                "provider_used": result.get("provider_used"),
                "provider_chain": result.get("provider_chain", []),
                "model": result.get("model"),
            }
        except Exception as e:
            fallback = {
                "CHAT"      : "تعذر الوصول إلى نموذج الذكاء الاصطناعي حالياً. تحقق من الاتصال أو إعدادات المزود ثم أعد المحاولة.",
                "QUESTION"  : "تعذر الوصول إلى نموذج الذكاء الاصطناعي حالياً. تحقق من الاتصال أو إعدادات المزود ثم أعد المحاولة.",
                "DISCUSSION": "تعذر الوصول إلى نموذج الذكاء الاصطناعي حالياً. تحقق من الاتصال أو إعدادات المزود ثم أعد المحاولة.",
            }

            return {
                "status": "error",
                "intent": mode.lower(),
                "text": fallback.get(mode),
                "mode": mode,
                "source": "fallback",
                "provider_used": result.get("provider_used") if "result" in locals() and isinstance(result, dict) else None,
                "provider_chain": result.get("provider_chain", []) if "result" in locals() and isinstance(result, dict) else [],
                "model": result.get("model") if "result" in locals() and isinstance(result, dict) else None,
                "gateway_error": result.get("error") if "result" in locals() and isinstance(result, dict) else None,
                "error": str(e),
            }

    def switch_topic(self, current_topic: str, new_input: str) -> dict:
        """يحفظ الموضوع الحالي ويبدأ موضوعاً جديداً."""
        if self.dialogue_memory:
            self.dialogue_memory.save_pending(current_topic)
        return self.process(new_input)

    def restore_topic(self) -> dict:
        """يسترجع الموضوع المؤجل."""
        if self.dialogue_memory:
            topic = self.dialogue_memory.restore_pending()
            if topic:
                return {
                    "status": "success",
                    "intent": "topic_restore",
                    "text"  : f"نرجع للموضوع السابق: {topic}",
                    "topic" : topic,
                }
        return {
            "status": "success",
            "intent": "topic_restore",
            "text"  : "لا يوجد موضوع مؤجل.",
        }
