"""
Series 8 — Runtime Environment

المسؤولية:
- وصف بيئة التشغيل الحالية.
- لا ينفذ أوامر.
- لا يقرأ أو يكتب ملفات.
"""


import platform
import sys


class RuntimeEnvironment:

    def __init__(self):
        self.python_version = sys.version.split()[0]
        self.platform = platform.system()
        self.machine = platform.machine()
        self.runtime_name = "CyberLab Runtime"

    def to_dict(self):
        return {
            "python_version": self.python_version,
            "platform": self.platform,
            "machine": self.machine,
            "runtime_name": self.runtime_name,
        }
