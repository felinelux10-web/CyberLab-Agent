# CyberLab Agent v4.0
# intent/parser.py

ACTION_KEYWORDS = {
    "shell": [
        "شغّل", "نفّذ", "run", "execute", "اشغل"
    ],
    "write_file": [
        "اكتب", "أنشئ", "عدّل", "write", "create", "edit", "انشئ"
    ],
    "read_file": [
        "اقرأ", "اعرض", "read", "show", "print", "اظهر"
    ],
    "create_and_run": [
        "ابنِ وشغّل", "create and run", "انشئ وشغّل"
    ],
}

def detect_action(text: str) -> str | None:
    text_lower = text.lower()
    for action, keywords in ACTION_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return action
    return None

def detect_target(text: str, action: str = None) -> str:
    words = text.split()

    # لـ shell — كل شيء بعد الكلمة الأولى هو الأمر
    if action == "shell":
        for i, word in enumerate(words):
            for kw in ACTION_KEYWORDS["shell"]:
                if kw in word:
                    rest = " ".join(words[i+1:])
                    return rest if rest else ""

    # للباقي — ابحث عن مسار
    for word in words:
        if "/" in word or "." in word:
            return word

    return ""

def parse(user_input: str) -> dict:
    action = detect_action(user_input)
    target = detect_target(user_input, action)

    confidence = 0.0
    if action:
        confidence += 0.6
    if target:
        confidence += 0.4

    if confidence < 0.6:
        return {
            "status"    : "unclear",
            "confidence": confidence,
            "raw"       : user_input,
        }

    return {
        "status"    : "clear",
        "action"    : action,
        "target"    : target,
        "confidence": confidence,
        "raw"       : user_input,
    }
