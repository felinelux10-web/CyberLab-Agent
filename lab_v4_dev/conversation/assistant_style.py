"""
Assistant Personality — Series 10-D
قواعد ثابتة لأسلوب الرد.
"""

FILLER_PHRASES = [
    "بالطبع!","بالطبع ","رائع!","رائع ","ممتاز!","ممتاز ",
    "بكل سرور!","بكل سرور ","حسناً،","حسنا،",
    "بالتأكيد!","بالتأكيد ","شكراً لسؤالك",
]

QUESTION_LIMIT = 1


def clean_response(text: str) -> str:
    """يحذف العبارات الزائدة من بداية الرد."""
    for phrase in FILLER_PHRASES:
        if text.startswith(phrase):
            text = text[len(phrase):].lstrip()
    return text


def format_response(text: str, mode: str = "TASK") -> str:
    """
    يطبق قواعد الأسلوب حسب نوع الرد:
    - TASK: مختصر ومباشر
    - CHAT/QUESTION/DISCUSSION: طبيعي ومفصل عند الحاجة
    """
    text = clean_response(text)

    if mode == "TASK":
        # لا مقدمات — النتيجة مباشرة
        return text

    if mode in ("QUESTION", "DISCUSSION"):
        # رد طبيعي بدون تكرار السؤال
        return text

    return text


def single_question(text: str) -> str:
    """
    يتأكد أن الرد لا يحتوي أكثر من سؤال واحد.
    إذا وجد أكثر من علامة استفهام يبقي الأول فقط.
    """
    parts = text.split("؟")
    if len(parts) > 2:
        return parts[0] + "؟"
    return text
