# CyberLab Agent — Project Intelligence Engine
# project_knowledge/language_registry.py
#
# PIE-001B: Language Registry
# المسؤولية الوحيدة: تعريف اللغات البرمجية وامتداداتها وقابليتها للتحليل.
# لا يعتمد على أي مكوّن آخر في المشروع.
# لإضافة لغة جديدة: أضف سطراً واحداً فقط في LANGUAGES.

LANGUAGES = {
    # Python
    ".py"  : {"language": "python",      "analyzable": True},
    # JavaScript / TypeScript
    ".js"  : {"language": "javascript",  "analyzable": True},
    ".jsx" : {"language": "javascript",  "analyzable": True},
    ".ts"  : {"language": "typescript",  "analyzable": True},
    ".tsx" : {"language": "typescript",  "analyzable": True},
    # Shell
    ".sh"  : {"language": "bash",        "analyzable": True},
    ".ps1" : {"language": "powershell",  "analyzable": True},
    # Systems
    ".c"   : {"language": "c",           "analyzable": True},
    ".cpp" : {"language": "cpp",         "analyzable": True},
    ".h"   : {"language": "c_header",    "analyzable": False},
    ".rs"  : {"language": "rust",        "analyzable": True},
    ".go"  : {"language": "go",          "analyzable": True},
    # JVM
    ".java": {"language": "java",        "analyzable": True},
    ".kt"  : {"language": "kotlin",      "analyzable": True},
    # Web
    ".html": {"language": "html",        "analyzable": False},
    ".css" : {"language": "css",         "analyzable": False},
    ".php" : {"language": "php",         "analyzable": True},
    ".rb"  : {"language": "ruby",        "analyzable": True},
    # Data / Config
    ".json": {"language": "json",        "analyzable": False},
    ".yaml": {"language": "yaml",        "analyzable": False},
    ".yml" : {"language": "yaml",        "analyzable": False},
    ".toml": {"language": "toml",        "analyzable": False},
    ".sql" : {"language": "sql",         "analyzable": False},
    # Docs
    ".md"  : {"language": "markdown",    "analyzable": False},
    ".txt" : {"language": "text",        "analyzable": False},
}


def get_language(extension: str) -> str:
    """إرجاع اسم اللغة لامتداد معيّن"""
    return LANGUAGES.get(extension.lower(), {}).get("language", "unknown")


def is_analyzable(extension: str) -> bool:
    """هل يمكن تحليل هذا الامتداد لاحقاً؟"""
    return LANGUAGES.get(extension.lower(), {}).get("analyzable", False)


def get_info(extension: str) -> dict:
    """إرجاع كامل معلومات الامتداد"""
    ext = extension.lower()
    return {
        "extension" : ext,
        "language"  : get_language(ext),
        "analyzable": is_analyzable(ext),
    }


def supported_extensions() -> list:
    """قائمة بجميع الامتدادات المعروفة"""
    return list(LANGUAGES.keys())
