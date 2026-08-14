"""
PIE-001C — Analyzer Registry Foundation
الهدف: طبقة تسجيل المحللين فقط.
لا يحلل أي ملف. لا يقرأ AST. لا يبني Graph.
فقط: تسجيل + اكتشاف + التحقق من الدعم.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AnalyzerInfo:
    """معلومات محلل واحد — بدون منطق تحليل"""
    name: str
    language: str
    extensions: list
    description: str
    available: bool = True
    version: str = "0.1"
    analyzer_class: object = None


class AnalyzerRegistry:
    """
    سجل المحللين — يعرف من هو موجود وماذا يدعم.
    لا يستدعي أي محلل. لا يحلل أي ملف.
    """

    def __init__(self):
        self._analyzers: dict = {}

    def register(self, info: AnalyzerInfo) -> None:
        """تسجيل محلل جديد"""
        self._analyzers[info.language] = info

    def get(self, language: str) -> Optional[AnalyzerInfo]:
        """الحصول على معلومات محلل حسب اللغة"""
        return self._analyzers.get(language)

    def supports(self, extension: str) -> Optional[str]:
        """هل يوجد محلل يدعم هذا الامتداد؟ يُرجع اسم اللغة أو None"""
        for lang, info in self._analyzers.items():
            if extension in info.extensions and info.available:
                return lang
        return None

    def list_supported(self) -> list:
        """قائمة اللغات المدعومة حالياً"""
        return [
            {"language": info.language, "extensions": info.extensions}
            for info in self._analyzers.values()
            if info.available
        ]

    def count(self) -> int:
        return len(self._analyzers)


# السجل العالمي — نسخة واحدة فقط في النظام
_registry = AnalyzerRegistry()


def get_registry() -> AnalyzerRegistry:
    return _registry


def register_analyzer(info: AnalyzerInfo) -> None:
    _registry.register(info)


def supports_extension(ext: str) -> Optional[str]:
    return _registry.supports(ext)


def list_supported_languages() -> list:
    return _registry.list_supported()


# ── محللون مخطط لهم (غير موجودون بعد) ──
# هذه التسجيلات تُعلن "ماذا سيكون موجوداً لاحقاً"
# available=False يعني: معروف لكن غير جاهز بعد

def register_planned_analyzers():
    """تسجيل المحللين المخطط بناؤها — بدون تنفيذ حقيقي"""

    from .python_analyzer import PythonAnalyzer

    planned = [
        AnalyzerInfo("python_analyzer",   "python",
                     [".py"],             "محلل Python (AST)",
                     available=True,
                     analyzer_class=PythonAnalyzer),
        AnalyzerInfo("js_analyzer",       "javascript",
                     [".js", ".jsx"],     "محلل JavaScript", available=False),
        AnalyzerInfo("ts_analyzer",       "typescript",
                     [".ts", ".tsx"],     "محلل TypeScript", available=False),
        AnalyzerInfo("shell_analyzer",    "shell",
                     [".sh", ".bash"],    "محلل Shell Scripts", available=False),
        AnalyzerInfo("go_analyzer",       "go",
                     [".go"],             "محلل Go", available=False),
        AnalyzerInfo("rust_analyzer",     "rust",
                     [".rs"],             "محلل Rust", available=False),
    ]
    for info in planned:
        register_analyzer(info)


# تسجيل تلقائي عند الاستيراد
register_planned_analyzers()


if __name__ == "__main__":
    r = get_registry()
    print(f"محللون مسجلون: {r.count()}")
    print(f"محللون متاحون: {len(r.list_supported())}")
    print(f"يدعم .py: {r.supports('.py')}")
    print(f"يدعم .ts: {r.supports('.ts')}")
    print(f"يدعم .xyz: {r.supports('.xyz')}")
    print("\nاللغات المسجلة (حتى غير المتاحة):")
    for lang, info in r._analyzers.items():
        status = "✅" if info.available else "⏳ مخطط"
        print(f"  {status} {lang}: {info.extensions}")
