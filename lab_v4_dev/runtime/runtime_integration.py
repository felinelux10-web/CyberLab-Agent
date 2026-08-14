"""
Series 8 — Runtime Integration

المسؤولية:
- نقطة الوصول الموحدة للـ Runtime.
"""

from .runtime_manager import RuntimeManager


_runtime = RuntimeManager()


def get_runtime():
    return _runtime
