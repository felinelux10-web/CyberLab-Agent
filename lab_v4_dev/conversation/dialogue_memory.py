"""
Dialogue Memory — Series 10-B
طبقة إدارة خفيفة تبني فوق ContextStore الموجود.
لا تنشئ قاعدة بيانات جديدة.
"""


class DialogueMemory:

    def __init__(self, context_store):
        self.context        = context_store
        self.last_topic     = None
        self.pending_topic  = None
        self.last_list      = []


    def update(self, text: str, result: dict):
        if result.get("text"):
            # حفظ الموضوع الرئيسي بدل السؤال كامل
            topic = text

            if "orchestrator.py" in text:
                topic = "orchestrator.py"
            elif "memory/db.py" in text:
                topic = "memory/db.py"
            else:
                for part in text.split():
                    if ".py" in part:
                        topic = part
                        break

            # لا تغير الموضوع الرئيسي عند أسئلة المتابعة
            follow_up = any(x in text for x in (
                "هل هذا",
                "ما دوره",
                "ما وظيفته",
                "ما علاقته",
                "كيف يعمل",
                "أخبرني عن علاقته",
                "وماذا عن",
                "ماذا عن",
            ))

            if not follow_up:
                self.last_topic = topic

            self.last_list.append({
                "role": "user",
                "content": text,
            })

            self.last_list.append({
                "role": "assistant",
                "content": result.get("text", ""),
            })

            self.last_list = self.last_list[-8:]

        items = result.get("items") or result.get("files") or []
        if items:
            self.last_items = items

    def save_pending(self, topic: str):
        self.pending_topic = topic

    def restore_pending(self) -> str | None:
        t = self.pending_topic
        self.pending_topic = None
        return t

    def resolve_references(self, text: str) -> str:
        REFS = {
            "هذا"           : getattr(self.context, "current_file", None) or getattr(self.context, "current_subject", None),
            "هذه"           : getattr(self.context, "current_file", None) or getattr(self.context, "current_subject", None),
            "ذلك"           : getattr(self.context, "current_subject", None),
            "تلك"           : getattr(self.context, "current_subject", None),
            "السابق"        : getattr(self.context, "current_subject", None),
            "السابقة"       : getattr(self.context, "current_subject", None),
            "الملف السابق"  : getattr(self.context, "current_file", None),
            "نفسه"          : getattr(self.context, "current_file", None) or getattr(self.context, "current_subject", None),
            "نفسها"         : getattr(self.context, "current_file", None) or getattr(self.context, "current_subject", None),
        }
        resolved = text

        # متابعة آخر موضوع في الحوار
        # معالجة الأسئلة المرتبطة بالموضوع قبل استبدال الضمائر
        if self.last_topic:

            if "علاقته بهذا" in text or "علاقته بهذه" in text:
                return "ما علاقة " + self.last_topic + " بالمشروع؟"

            if "ما دوره في المشروع" in text:
                return self.last_topic + " ما دوره في المشروع؟"

            if "كيف يعمل" in text:
                return self.last_topic + " كيف يعمل؟"

            if "ما وظيفته" in text:
                return self.last_topic + " ما وظيفته؟"

            if text.startswith("ولماذا"):
                return self.last_topic + " لماذا؟"
            if text.startswith("لماذا"):
                return self.last_topic + " لماذا؟"
            if text.startswith("وماذا عن"):
                return self.last_topic + " " + text[1:]
            if text.startswith("ماذا عن"):
                return self.last_topic + " " + text
            if text.startswith("وما علاقته"):
                return self.last_topic + " " + text
            if text.startswith("ما علاقته"):
                return self.last_topic + " " + text
            if text.startswith("هل تنصحني"):
                return self.last_topic + " " + text
            if text.startswith("وأيهما"):
                return self.last_topic + " " + text[1:]
        for ref, value in REFS.items():
            if ref in resolved and value:
                resolved = resolved.replace(ref, value)

        # معالجة التراكيب قبل الاستبدال العام للمراجع
        if self.last_topic:
            if "علاقته بهذا" in resolved:
                return "ما علاقة " + self.last_topic + " بالمشروع؟"

            if "علاقته بهذه" in resolved:
                return "ما علاقة " + self.last_topic + " بالمشروع؟"

            if "دوره في هذا" in resolved:
                return self.last_topic + " ما دوره في المشروع؟"

        # استبدال المراجع العامة باستخدام آخر موضوع معروف
        if self.last_topic:
            for ref in ("هذا", "هذه", "ذلك", "تلك", "نفسه", "نفسها"):
                if ref in resolved:
                    resolved = resolved.replace(ref, self.last_topic)

            # معالجة المراجع الملحقة مثل: علاقته بهذا / دوره في هذا

            if "علاقته بهذا" in resolved:
                return "ما علاقة " + self.last_topic + " بالمشروع؟"

            if "علاقته بهذه" in resolved:
                return "ما علاقة " + self.last_topic + " بالمشروع؟"

            if "دوره في هذا" in resolved:
                return self.last_topic + " ما دوره في المشروع؟"

            if "بهذا" in resolved:
                resolved = resolved.replace("بهذا", self.last_topic)

            if "بهذه" in resolved:
                resolved = resolved.replace("بهذه", self.last_topic)

            if "لهذا" in resolved:
                resolved = resolved.replace("لهذا", self.last_topic)

            # أسئلة متابعة عامة بدون مرجع صريح
            if resolved == text and any(
                x in text for x in (
                    "ما دوره",
                    "ما وظيفته",
                    "ما علاقته",
                    "هل هو مهم",
                    "كيف يعمل",
                )
            ):
                resolved = "ما " + self.last_topic + " " + text[3:]
        if "الحل الثاني" in resolved and hasattr(self,"last_items") and len(self.last_items) >= 2:
            resolved = resolved.replace("الحل الثاني", self.last_items[1])
        return resolved
