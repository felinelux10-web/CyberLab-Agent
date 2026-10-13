"""Terminal startup dashboard and clearly marked interactive prompt."""

import re
import shutil
import textwrap

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
BOLD = "\033[1m"


class BootUI:
    """Render compact, color-coded startup status for narrow Termux screens."""

    def __init__(self):
        detected = shutil.get_terminal_size((40, 20)).columns
        self.width = max(32, min(detected, 56))
        self.inner = self.width - 4
        self.color = bool(getattr(__import__("sys").stdout, "isatty", lambda: False)())

    def _paint(self, text, color):
        return f"{color}{text}{RESET}" if self.color else text

    def _line(self, text=""):
        text = str(text)
        visible = re.sub(r"\\033\\[[0-9;]*m", "", text)
        if len(visible) > self.inner and visible == text:
            text = text[: self.inner - 1] + "…"
            visible = text
        padding = max(0, self.inner - len(visible))
        print("│ " + text + (" " * padding) + " │")

    def _border(self, kind="middle", color=CYAN):
        left, right = {"top": ("┌", "┐"), "middle": ("├", "┤"), "bottom": ("└", "┘")}[kind]
        print(self._paint(left + "─" * (self.width - 2) + right, color))

    def start(self):
        print()
        self._border("top", CYAN)
        self._line(self._paint("CYBERLAB AGENT", BOLD + CYAN))
        self._line("STARTUP / SYSTEM CHECK")
        self._border()
        self._line("COMPONENT      STATUS")
        self._border()

    def row(self, component, detail, state="OK"):
        styles = {
            "OK": ("[✓]", GREEN),
            "WARN": ("[!]", YELLOW),
            "FAIL": ("[X]", RED),
            "INFO": ("[..]", CYAN),
            "PENDING": ("[↻]", MAGENTA),
        }
        marker, color = styles.get(state, ("[..]", CYAN))
        label_width = 12
        prefix = f"{marker} {component[:label_width]:<{label_width}} "
        available = max(8, self.inner - len(prefix))
        chunks = textwrap.wrap(str(detail), width=available, break_long_words=True) or [""]
        first = self._paint(prefix, color) + chunks[0]
        self._line(first)
        for chunk in chunks[1:]:
            self._line(" " * len(prefix) + chunk)

    def section(self, title, state="INFO"):
        color = {"OK": GREEN, "WARN": YELLOW, "FAIL": RED, "PENDING": MAGENTA}.get(state, CYAN)
        self._border("middle", color)
        self._line(self._paint(title, BOLD + color))

    def ready(self):
        self._border("middle", GREEN)
        self._line(self._paint("STATUS: READY", BOLD + GREEN))
        self._line("اكتب الأوامر بعد المؤشر الأخضر أدناه")
        self._border("bottom", GREEN)
        print()

    def prompt(self):
        """A highly visible command-entry marker shown before every input."""
        print()
        label = self._paint(" CYBERLAB › ", BOLD + GREEN)
        hint = self._paint(" اكتب الأمر هنا ", GREEN)
        print(label + hint, end="", flush=True)
        return input()
