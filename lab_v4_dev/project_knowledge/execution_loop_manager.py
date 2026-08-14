"""
PIE-007A — Execution Loop Manager

المسؤولية:
- إدارة دورة التنفيذ خطوة بخطوة.
- تحديث حالة التنفيذ.

لا يقوم بـ:
- تعديل الملفات.
- تنفيذ أوامر النظام.
"""


class ExecutionLoopManager:

    def start(self, context):

        return {
            "status": "running",
            "current_step": context.get(
                "remaining",
                []
            )[0] if context.get("remaining") else None,
            "completed": [],
            "failed": [],
            "remaining": context.get(
                "remaining",
                []
            ).copy(),
        }


    def complete(self, state, step):

        state["completed"].append(step)

        return state


    def fail(self, state, step):

        state["failed"].append(step)

        return state
