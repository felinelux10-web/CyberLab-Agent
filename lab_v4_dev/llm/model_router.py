"""
CyberLab Agent
H.R.1

Model Router
Decision Layer only.

لا يتصل بأي مزود.
لا ينفذ أي طلب.
يقرر فقط:
- المهمة
- المزود
- النموذج
"""

from dataclasses import dataclass


@dataclass
class RoutingDecision:
    task_type: str
    provider: str
    model: str | None = None


CYBER_KEYWORDS = [
    "sql",
    "xss",
    "csrf",
    "tcp",
    "udp",
    "linux",
    "اختراق",
    "الأمن",
    "امن",
    "ثغرة",
    "هجوم",
    "cyber",
]

PROJECT_KEYWORDS = [
    ".py",
    "gateway",
    "orchestrator",
    "prompt_builder",
    "project",
    "المشروع",
    "الوكيل",
    "cyberlab",
]


def route(user_text: str) -> RoutingDecision:

    text = user_text.lower()

    if any(k.lower() in text for k in PROJECT_KEYWORDS):
        return RoutingDecision(
            task_type="project",
            provider="openrouter",
        )

    if any(k.lower() in text for k in CYBER_KEYWORDS):
        return RoutingDecision(
            task_type="cyber",
            provider="groq",
        )

    return RoutingDecision(
        task_type="general",
        provider="groq",
    )
