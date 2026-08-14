# CyberLab Agent v4.9
# core/code_engine.py

import os
import re
from datetime import datetime
from lab_v4_dev.llm.gateway import ask

WORKSPACE = "workspace"
SYSTEM = """أنت مبرمج Python دقيق ومنضبط.
قواعد صارمة لا استثناء فيها:
1. نفذ الطلب بدقة — لا تضف أدوات أو imports غير مطلوبة
2. متغيرات وأسماء دوال بالإنجليزية فقط
3. تعليقات بالعربية مقبولة
4. لا تستخدم input() أبداً
5. لا تضف أوامر نظام (os.system, subprocess) إلا إذا طُلب صراحة
6. لا تضف صلاحيات أو أدوات أمان إلا إذا طُلب صراحة
7. الكود يعمل مباشرة بدون تدخل
8. إذا الطلب: فحص منفذ → استخدم socket فقط
9. إذا الطلب: HTTP → استخدم requests فقط
10. لا تخرج عن نطاق الطلب أبداً
"""

def detect_language(code):
    if "import " in code or "def " in code: return "python"
    if "#!/bin/bash" in code or "echo " in code: return "bash"
    if "#include" in code: return "c"
    return "python"

def extract_code(text):
    m = re.search(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()

def save_file(code, filename, folder="scripts"):
    path = os.path.join(WORKSPACE, folder, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    return path


TEMPLATES = {
    "port_check": """import socket

def check_port(host, port, timeout=1):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    result = s.connect_ex((host, port))
    s.close()
    return result == 0

host  = "{host}"
ports = {ports}
for port in ports:
    status = "مفتوح" if check_port(host, port) else "مغلق"
    print(f"المنفذ {{port}}: {{status}}")
""",
    "ping_host": """import socket

hosts = {hosts}
for host in hosts:
    try:
        ip = socket.gethostbyname(host)
        print(f"{{host}} → {{ip}} متاح")
    except:
        print(f"{{host}} → غير متاح")
""",
    "file_read": """with open("{filepath}", "r", encoding="utf-8") as f:
    content = f.read()
print(content[:500])
""",
    "http_get": """import urllib.request

url = "{url}"
try:
    with urllib.request.urlopen(url, timeout=5) as r:
        print(f"Status: {{r.status}}")
        print(r.read(200).decode())
except Exception as e:
    print(f"خطأ: {{e}}")
""",
    "list_files": """import os

path = "{path}"
for f in os.listdir(path):
    size = os.path.getsize(os.path.join(path, f))
    print(f"{{f}} — {{size}} bytes")
""",
}

def _match_template(description: str) -> str:
    import re
    desc = description.lower()

    if any(w in desc for w in ["فحص منفذ","يفحص منفذ","يفحص المنفذ","يفحص المنافذ","check port","port scan","منافذ","فحص المنافذ","فحص منافذ"]):
        ip    = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|localhost)", desc)
        host  = ip.group(1) if ip else "127.0.0.1"
        # احذف أرقام IP قبل استخراج المنافذ
        clean_desc = re.sub(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "", desc)
        ports = [int(p) for p in re.findall(r"(?<![\d])(\d{1,5})(?![\d])", clean_desc) if 1<=int(p)<=65535] or [80,443,8080]
        return TEMPLATES["port_check"].format(host=host, ports=ports)

    if any(w in desc for w in ["ping","فحص موقع","هل موقع","يفحص مواقع","فحص مواقع","تحقق من موقع","مواقع"]):
        hosts = re.findall(r"[\w.-]+\.(?:com|org|net|io|gov|edu)", description) or ["google.com"]
        return TEMPLATES["ping_host"].format(hosts=hosts)

    if any(w in desc for w in ["اقرا ملف","read file","محتوى ملف"]):
        f = re.search(r"[\w./]+\.[\w]+", desc)
        filepath = f.group(0) if f else "file.txt"
        return TEMPLATES["file_read"].format(filepath=filepath)

    if any(w in desc for w in ["http get","طلب http","جلب صفحة"]):
        u = re.search(r"https?://[\S]+", desc)
        url = u.group(0) if u else "http://example.com"
        return TEMPLATES["http_get"].format(url=url)

    return None

def generate_code(description):
    # جرب template أولاً — أدق وأسرع
    t = _match_template(description)
    if t:
        ts   = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        path = save_file(t, f"script_{ts}.py", "scripts")
        return {"status":"success","code":t,
                "explanation":f"✅ كود جاهز للتنفيذ\n{description}",
                "saved_to":path}

    prompt = """اكتب كود Python دقيق للطلب التالي.

الطلب: """ + description + """

قواعد صارمة:
- نفذ الطلب حرفياً بدون إضافات
- استخدم socket للشبكة، requests للـ HTTP
- لا تضف أدوات غير مطلوبة
- الكود داخل ```python ... ```
- ثم شرح قصير بالعربية

مثال إذا الطلب "فحص منفذ":
```python
import socket
def check_port(host, port):
    s = socket.socket()
    s.settimeout(1)
    result = s.connect_ex((host, port))
    s.close()
    return result == 0
print(check_port('127.0.0.1', 80))
```"""
    result = ask(prompt, system=SYSTEM, max_tokens=800)
    if result["status"] != "success":
        return {"status": "failed", "text": result.get("text","")}
    text = result.get("text","")
    code = extract_code(text)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = save_file(code, "script_" + ts + ".py", "scripts")
    return {"status":"success","code":code,"explanation":text,"saved_to":path}

def analyze_code(code, question=""):
    lang   = detect_language(code)
    prompt = "حلل هذا الكود بالعربية:\n```" + lang + "\n" + code[:2000] + "\n```\n1.ماذا يفعل؟\n2.هل فيه اخطاء؟\n3.هل فيه ثغرات؟\n4.كيف يتحسن؟"
    if question: prompt += "\nسؤال: " + question
    result = ask(prompt, system=SYSTEM, max_tokens=600)
    return {"status":result["status"],"language":lang,"analysis":result.get("text","")}

def modify_code(code, instruction):
    if not instruction or len(instruction.strip()) < 5:
        return {"status":"needs_clarification","text":"ماذا تريد أن أعدل؟ صف التعديل المطلوب بوضوح."}
    if not code or not code.strip():
        return {"status":"failed","text":"لا يوجد كود للتعديل"}
    lang   = detect_language(code)
    prompt = "عدل هذا الكود:\n```" + lang + "\n" + code[:2000] + "\n```\nالتعديل: " + instruction + "\naكتب الكود المعدل داخل ```" + lang + "...``` ثم اشرح التغييرات."
    result = ask(prompt, system=SYSTEM, max_tokens=800)
    if result["status"] != "success":
        return {"status":"failed","text":result.get("text","")}
    text = result.get("text","")
    modified = extract_code(text)
    # لا نحفظ هنا — SafePipeline سيتولى الحفظ
    return {"status":"success","code":modified,"explanation":text,"saved_to":None}
