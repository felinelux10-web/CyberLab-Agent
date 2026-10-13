"""Minimal terminal UI for startup status and command entry."""

import shutil
import sys
import textwrap

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"


class BootUI:
    """Render restrained status text suitable for a narrow Termux terminal."""

    def __init__(self):
        self.width = max(32, min(shutil.get_terminal_size((40, 20)).columns, 72))
        self.color = bool(getattr(sys.stdout, "isatty", lambda: False)())

    def _paint(self, text, color):
        return f"{color}{text}{RESET}" if self.color else text

    def _rule(self):
        # Keep the separator long while respecting the actual terminal width.
        print(self._paint("─" * max(24, self.width - 2), GREEN))

    def start(self):
        print()
        print("إقلاع الوكيل")
        print("الحالة   المكوّن")

    def row(self, component, detail, state="OK"):
        markers = {
            "OK": self._paint("●", GREEN),
            "FAIL": self._paint("●", RED),
            "WARN": self._paint("●", RED),
            "PENDING": self._paint("●", RED),
            "INFO": "·",
        }
        marker = markers.get(state, "·")
        prefix = f"{marker}  {component:<12} "
        continuation_indent = " " * len(prefix)
        available = max(10, self.width - len(prefix))
        lines = textwrap.wrap(str(detail), width=available, break_long_words=True) or [""]
        print(prefix + lines[0])
        for line in lines[1:]:
            print(continuation_indent + line)
        # Visually separate components without bringing back dashboard boxes.
        print()

    def section(self, title, state="INFO"):
        # Section headings remain in the terminal's default text color.
        print()
        print(title)

    def ready(self):
        print()
        print(f"{self._paint('●', GREEN)} الوكيل جاهز")
        print()

    def prompt(self):
        """Show a green identity marker and separator before each command."""
        print()
        self._rule()
        print(self._paint("✦ CYBERLAB", GREEN))
        return input("> ")
