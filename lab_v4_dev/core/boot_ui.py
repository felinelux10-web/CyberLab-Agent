"""Minimal terminal UI for startup status and command entry."""

import select
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

    @staticmethod
    def _combine_pasted_lines(first_line, continuation_lines):
        """Combine a terminal paste into one logical user message."""
        lines = [str(first_line or "").rstrip("\r\n")]
        lines.extend(str(line or "").rstrip("\r\n") for line in continuation_lines)
        return "\n".join(lines).strip()

    def _read_pasted_continuation(self, first_line, *, idle_timeout=0.12):
        """Collect lines already queued by a multiline terminal paste.

        A normal interactive line still returns after a short idle window.
        This prevents each line of a pasted numbered prompt becoming a separate
        request while preserving the existing one-line CLI workflow.
        """
        if not getattr(sys.stdin, "isatty", lambda: False)():
            return str(first_line or "").strip()

        continuation = []
        while True:
            try:
                ready, _, _ = select.select([sys.stdin], [], [], idle_timeout)
            except (OSError, ValueError, TypeError):
                break
            if not ready:
                break
            line = sys.stdin.readline()
            if line == "":
                break
            continuation.append(line)

        return self._combine_pasted_lines(first_line, continuation)

    def prompt(self):
        """Show the prompt and preserve multiline terminal pastes as one message."""
        print()
        self._rule()
        print(self._paint("✦ CYBERLAB", GREEN))
        first_line = input("> ")
        return self._read_pasted_continuation(first_line)
