# CyberLab Agent v4.7
# llm/prompt_builder.py — Grounded Prompt Builder

import json
import os
from lab_v4_dev.core.project_context import CYBERLAB_ROOT, get_active_project
from lab_v4_dev.llm.context_builder import build_system_prompt

ROADMAP_FILE = "project_data/roadmap.json"

def _index_file() -> str:
    proj = get_active_project()
    from lab_v4_dev.awareness.project_index import _index_file as _idx
    cyberlab_roots = [CYBERLAB_ROOT, CYBERLAB_ROOT + "/lab_v4_dev"]
    if any(proj.root.startswith(r) for r in cyberlab_roots):
        return _idx()
    return "workspace/external_index/project_index.json"

def _load_index() -> dict:
    try:
        with open(_index_file(), "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def _load_roadmap() -> dict:
    try:
        from lab_v4_dev.awareness.project_knowledge import get_roadmap
        return get_roadmap()
    except:
        return {}

def build_project_context() -> str:
    """يبني سياق المشروع من البيانات الحقيقية فقط"""
    index   = _load_index()
    roadmap = _load_roadmap()
    proj    = get_active_project()

    if isinstance(index.get("files"), list):
        real_files = index["files"]
        listed = chr(10).join(f"- {p}" for p in real_files[:60])
        more = f"\n... و{len(real_files)-60} ملف إضافي" if len(real_files) > 60 else ""
        return f"""أنت مساعد هندسي لمشروع {proj.name}.

=== قواعد صارمة ===
1. استخدم فقط المعلومات أدناه — لا تخترع ملفات أو وظائف
2. إذا لم تجد المعلومة في البيانات أدناه → قل "غير موجود في البيانات المتاحة"
3. لا تستخدم معرفتك العامة عن Python أو البرمجة لاختراع ملفات

=== الملفات الحقيقية في المشروع ({len(real_files)} ملف) ===
{listed}{more}

=== ملاحظة ===
لا توجد بيانات أدوار/طبقات مصنّفة لهذا المشروع — فقط قائمة المسارات أعلاه.
"""

    real_files = list(index.keys())
    layers = {}
    for path, info in index.items():
        if not isinstance(info, dict):
            continue
        layer = info.get("layer", "?")
        layers.setdefault(layer, []).append(path)

    known = {}

    for path, info in index.items():
        if isinstance(info, dict):
            known[path] = {
                "layer": info.get("layer", ""),
                "role": info.get("role", ""),
                "functions": info.get("functions", []),
            }

    important = []
    for path, info in list(known.items()):
        if path.startswith("lab_v4_dev/") and any(
            x in path for x in ("gateway.py", "orchestrator.py")
        ):
            important.append(
                f"- {path}: functions={info.get('functions', [])}"
            )

    return f"""أنت مساعد هندسي لمشروع {proj.name}.

=== قواعد صارمة ===
1. استخدم فقط المعلومات أدناه
2. لا تخترع وظائف غير موجودة
3. إذا لم تجد المعلومة قل: غير موجود في البيانات المتاحة

=== ملفات مهمة ===
{chr(10).join(important)}

=== إجمالي الملفات ===
{len(real_files)}

=== الطبقات ===
{chr(10).join(f"- {layer}: {len(files)} ملف" for layer, files in layers.items())}

=== حالة التطوير ===
الإصدار: {roadmap.get('version','?')}
التركيز: {roadmap.get('current_focus','?')}
مكتمل: {', '.join(roadmap.get('completed',[]))}
"""

def build_search_prompt(query: str, results: list) -> str:
    """prompt للبحث في الكود — مقيد بالنتائج الحقيقية فقط"""
    if not results:
        return f"البحث عن '{query}' لم يعطِ نتائج في ملفات المشروع الحقيقية."

    results_text = "\n".join(
        f"- {r['path']}: {r.get('role','')}" for r in results
    )
    return f"""البحث عن '{query}' في المشروع أعطى هذه النتائج الحقيقية فقط:

{results_text}

تعليمات صارمة:
- لا تكتب أي كود أو محتوى لهذه الملفات — أنت لا تعرف محتواها الفعلي.
- لا تخترع أسماء متغيرات أو دوال أو إعدادات (مثل قواعد البيانات، SMTP، إلخ).
- اشرح فقط دور الملف بناءً على اسمه ومساره ودوره المذكور أعلاه، بجملة أو جملتين.
- إذا لم تكن متأكداً من التفاصيل، قل ذلك صريحاً."""

def build_release_prompt(version: str, content: str, question: str) -> str:
    """prompt لتحليل إصدار — مقيد بمحتوى التقرير الحقيقي"""
    return f"""أنت مساعد هندسي. حلل تقرير الإصدار {version} أدناه فقط.

قواعد:
- أجب فقط من محتوى التقرير
- لا تخمن معلومات غير موجودة
- إذا لم تجد المعلومة قل "غير مذكور في التقرير"

=== تقرير {version} ===
{content[:1000]}

السؤال: {question}"""


def build_cybersec_prompt(topic: str, level: str = "مبتدئ") -> tuple:
    """prompt متخصص للأمن السيبراني"""
    system = """أنت خبير أمن سيبراني ومعلم متخصص.
أسلوبك: شرح واضح خطوة بخطوة بالعربية.
قواعد:
1. ابدأ بتعريف المفهوم بجملة واحدة
2. اشرح كيف يعمل الهجوم (مثال عملي)
3. اشرح كيف تتم الحماية منه
4. أعطِ مثالاً على كود آمن وكود غير آمن
5. لا تتجاوز 600 كلمة"""

    prompt = f"""اشرح لي "{topic}" بأسلوب مناسب لمستوى {level}.
اتبع هذا الترتيب:
1. ما هو؟
2. كيف يعمل الهجوم؟ (مثال حقيقي)
3. كيف تحمي نفسك؟
4. مثال كود (ثغرة vs حماية)"""

    return system, prompt


def build_code_prompt(description: str, lang: str = "python") -> tuple:
    """prompt متخصص لكتابة الكود"""
    system = f"""أنت مبرمج {lang} محترف ومتخصص في الأمن السيبراني.
قواعد صارمة:
1. اكتب الكود داخل ```{lang} ... ``` فقط
2. متغيرات بالإنجليزية، تعليقات بالعربية
3. لا تستخدم input() أبداً
4. لا تضف أدوات خارج الطلب
5. الكود يعمل مباشرة بدون تدخل"""

    prompt = f"اكتب كود {lang} لـ: {description}"
    return system, prompt


def build_analysis_prompt(code: str, question: str = "") -> tuple:
    """prompt لتحليل الكود"""
    system = """أنت محلل كود أمني متخصص.
أجب بالعربية على هذه النقاط بالترتيب:
1. ماذا يفعل الكود؟
2. هل فيه ثغرات أمنية؟
3. هل فيه أخطاء منطقية؟
4. كيف تحسنه؟"""

    prompt = f"حلل هذا الكود:\n```\n{code[:1500]}\n```"
    if question:
        prompt += f"\n\nسؤال إضافي: {question}"
    return system, prompt




PROJECT_HINTS = (
    "المشروع","الوكيل","cyberlab","gateway","orchestrator",
    "project","lab_v4_dev","ملف","كود","module","class",
    "function","release","version"
)

CYBER_HINTS = (
    "sql","injection","xss","csrf","rce","ssti","idor",
    "linux","python","network","tcp","udp","http","https",
    "امن","أمن","سيبراني","اختراق","ثغره","ثغرة","استغلال",
    "malware","exploit","buffer","overflow","hash","crypto"
)

def _chat_domain(user_input: str):
    t = user_input.lower()

    if any(k.lower() in t for k in PROJECT_HINTS):
        return "project"

    if any(k.lower() in t for k in CYBER_HINTS):
        return "cyber"

    return "general"


def build_chat_prompt(user_input: str, history: list = None) -> tuple:
    """
    يبني system prompt و user prompt للمحادثة الطبيعية.
    يعيد (system, prompt).
    """
    domain = _chat_domain(user_input)

    if domain == "project":
        system = (
            build_system_prompt()
            + "\n\n"
            + build_project_context()
            + """

تعليمات إضافية:
- إذا كان السؤال يتعلق بالمشروع فاستخدم معلومات المشروع الحالية فقط.
- اعتمد على project_index الحقيقي.
- لا تخترع ملفات أو وظائف.
- إذا لم تجد المعلومة فقل: غير موجود في البيانات المتاحة.
- أجب بالعربية وباختصار."""

        )

    elif domain == "cyber":
        system = """أنت خبير أمن سيبراني ومبرمج محترف.

قواعد:
- أجب بالعربية الفصحى.
- اعتمد على الحقائق التقنية المعروفة.
- إذا لم تكن متأكداً من معلومة تاريخية أو تقنية فلا تخمن، بل اذكر أنك غير متأكد.
- لا تربط السؤال بمشروع CyberLab إلا إذا طلب المستخدم ذلك.
- احتفظ بالمصطلحات التقنية الإنجليزية مثل SQL Injection و Linux و Provider عند الحاجة ولا تترجمها ترجمة حرفية خاطئة.
- اشرح المفاهيم مع أمثلة واضحة ودقيقة."""

    else:
        system = """أنت مساعد عام.

قواعد:
- أجب بالعربية الفصحى.
- لا تختلق معلومات.
- إذا لم تكن متأكداً فاذكر ذلك.
- لا تفترض أن السؤال يتعلق بمشروع CyberLab إلا إذا ذكره المستخدم صراحة.
- احتفظ بالمصطلحات التقنية بلغتها الأصلية عند الحاجة بدلاً من ترجمتها ترجمة خاطئة."""


    # توجيه خاص لأسئلة المتابعة المرجعية
    if "ما علاقة" in user_input:
        system += """
- السؤال عن العلاقة بين ملف ومكونات المشروع.
- لا تشرح وظيفة الملف فقط.
- ركز على الاعتماد، التواصل، والموقع داخل المعمارية.
"""

    elif "ما دوره" in user_input or "ما وظيفته" in user_input:
        system += """
- السؤال عن الدور داخل المشروع.
- اشرح المسؤوليات الأساسية للملف ومكانه في النظام.
"""

    elif "كيف يعمل" in user_input:
        system += """
- السؤال عن طريقة العمل.
- اشرح تسلسل التنفيذ أو تدفق البيانات خطوة بخطوة.
"""


    prompt = user_input
    if history:
        context = "\n".join(
            f"{'\u0645\u0633\u062a\u062e\u062f\u0645' if h['role'] == 'user' else '\u0648\u0643\u064a\u0644'}: {h['content']}"
            for h in history[-4:]
        )
        prompt = context + "\n\u0645\u0633\u062a\u062e\u062f\u0645: " + user_input

    return system, prompt
