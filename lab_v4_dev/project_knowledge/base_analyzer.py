"""
PIE-001D — Base Analyzer Interface
العقد الموحد الذي يلتزم به جميع محللات اللغات مستقبلاً.
مستقل تماماً عن أي لغة برمجة.
لا منطق تحليل — فقط تعريف الواجهة.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SymbolInfo:
    """رمز واحد في الكود (دالة، كلاس، متغير...)"""
    name: str
    kind: str           # "function" | "class" | "variable" | "import" | ...
    line: int
    end_line: Optional[int] = None
    parent: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class DependencyInfo:
    """اعتمادية واحدة (استيراد، مرجع خارجي...)"""
    source: str         # الملف المصدر
    target: str         # الملف/الوحدة المستهدفة
    kind: str           # "import" | "call" | "inherit" | ...
    line: Optional[int] = None


@dataclass
class AnalysisResult:
    """ناتج تحليل ملف واحد"""
    file_path: str
    language: str
    symbols: list = field(default_factory=list)       # list[SymbolInfo]
    dependencies: list = field(default_factory=list)  # list[DependencyInfo]
    errors: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class BaseAnalyzer(ABC):
    """
    الواجهة الأساسية لجميع محللات اللغات.
    كل محلل مستقبلي يجب أن يرث من هذه الكلاس
    ويُنفّذ جميع الـ abstract methods.
    """

    @abstractmethod
    def supports(self, file_path: str) -> bool:
        """
        هل هذا المحلل يدعم هذا الملف؟
        مثال: PythonAnalyzer يتحقق من امتداد .py
        """
        ...

    @abstractmethod
    def analyze(self, file_path: str) -> AnalysisResult:
        """
        تحليل ملف كامل وإرجاع النتيجة.
        النقطة الرئيسية للتحليل.
        """
        ...

    @abstractmethod
    def collect_symbols(self, file_path: str) -> list:
        """
        استخراج الرموز فقط (دوال، كلاسات...).
        list[SymbolInfo]
        """
        ...

    @abstractmethod
    def collect_dependencies(self, file_path: str) -> list:
        """
        استخراج الاعتماديات فقط (imports...).
        list[DependencyInfo]
        """
        ...

    @abstractmethod
    def metadata(self) -> dict:
        """
        معلومات عن المحلل نفسه.
        مثال: {"name": "python", "version": "1.0", "extensions": [".py"]}
        """
        ...


# ── التحقق من أن الواجهة قابلة للتوريث ──
if __name__ == "__main__":

    class _DummyAnalyzer(BaseAnalyzer):
        """محلل وهمي للتحقق فقط — ليس للاستخدام"""
        def supports(self, f): return f.endswith(".dummy")
        def analyze(self, f): return AnalysisResult(f, "dummy")
        def collect_symbols(self, f): return []
        def collect_dependencies(self, f): return []
        def metadata(self): return {"name": "dummy", "extensions": [".dummy"]}

    a = _DummyAnalyzer()
    print("BaseAnalyzer interface ✅")
    print(f"supports .dummy: {a.supports('test.dummy')}")
    print(f"supports .py:    {a.supports('test.py')}")
    result = a.analyze("test.dummy")
    print(f"analyze returns: AnalysisResult(file={result.file_path}, lang={result.language})")
    print(f"metadata: {a.metadata()}")
    print("\nالواجهة جاهزة — أي محلل مستقبلي يرث من BaseAnalyzer ✅")
