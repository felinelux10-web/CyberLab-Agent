"""Small dependency-free terminal dashboard for CyberLab Agent startup."""

import shutil
import textwrap


class BootUI:
    """Render startup milestones as consistently aligned terminal rows."""

    def __init__(self):
        detected = shutil.get_terminal_size((40, 20)).columns
        self.width = max(32, min(detected, 56))
        self.inner = self.width - 4

    def _line(self, text=""):
        text = str(text)
        if len(text) > self.inner:
            text = text[: self.inner - 1] + "…"
        print("│ " + text.ljust(self.inner) + " │")

    def start(self):
        print()
        print("┌" + "─" * (self.width - 2) + "┐")
        self._line("CYBERLAB AGENT")
        self._line("STARTUP / SYSTEM CHECK")
        print("├" + "─" * (self.width - 2) + "┤")
        self._line("COMPONENT      STATUS")
        print("├" + "─" * (self.width - 2) + "┤")

    def row(self, component, detail, state="OK"):
        marker = {"OK": "[OK]", "WARN": "[!]", "FAIL": "[X]", "INFO": "[..]"}.get(state, "[..]")
        label_width = 12
        prefix = f"{marker} {component[:label_width]:<{label_width}} "
        available = max(8, self.inner - len(prefix))
        chunks = textwrap.wrap(str(detail), width=available) or [""]
        self._line(prefix + chunks[0])
        for chunk in chunks[1:]:
            self._line(" " * len(prefix) + chunk)

    def section(self, title):
        print("├" + "─" * (self.width - 2) + "┤")
        self._line(title)

    def ready(self):
        print("├" + "─" * (self.width - 2) + "┤")
        self._line("STATUS: READY")
        self._line("اكتب 'مساعدة' أو 'exit'")
        print("└" + "─" * (self.width - 2) + "┘")
        print()
