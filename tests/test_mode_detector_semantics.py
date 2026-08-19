from lab_v4_dev.conversation.mode_detector import detect_mode


def test_explicit_code_request_is_task_even_with_chat_word():
    assert detect_mode("اكتب سكريبت يطبع مرحبا") == "TASK"


def test_arabic_explanation_request_is_question():
    assert detect_mode("اشرح SQL Injection") == "QUESTION"


def test_file_function_question_is_question():
    assert detect_mode("ما وظيفة orchestrator.py") == "QUESTION"


def test_follow_up_role_question_remains_follow_up():
    assert detect_mode("ما دوره في المشروع؟") == "FOLLOW_UP"


def test_follow_up_how_it_works_remains_follow_up():
    assert detect_mode("كيف يعمل؟") == "FOLLOW_UP"


def test_explicit_analysis_remains_task():
    assert detect_mode("حلل المشروع كله وقل لي ماذا ينقص") == "TASK"


def test_plain_greeting_is_chat():
    assert detect_mode("مرحبا") == "CHAT"
