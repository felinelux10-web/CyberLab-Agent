"""Professional terminal UI for startup status and command entry."""

import select
import shutil
import sys
import textwrap

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"


class BootUI:
    """Render a compact, bordered startup dashboard for Termux and terminals."""

    def __init__(self):
        self.width = max(40, min(shutil.get_terminal_size((56, 20)).columns, 78))
        self.color = bool(getattr(sys.stdout, "isatty", lambda: False)())

    def _paint(self, text, color):
        return f"{color}{text}{RESET}" if self.color else text

    @property
    def _inner_width(self):
        return max(34, self.width - 2)

    def _rule(self, char="─"):
        print(self._paint(char * self._inner_width, GREEN))

    def _box_line(self, left="│", right="│", fill=" "):
        return f"{left}{fill * self._inner_width}{right}"

    def _table_border(self, left, junction, right):
        return self._paint(
            f"{left}{'─' * self._inner_width}{right}", GREEN
        )

    def _status_marker(self, state):
        markers = {
            "OK": self._paint("●", GREEN),
            "FAIL": self._paint("●", RED),
            "WARN": self._paint("●", RED),
            "PENDING": self._paint("●", RED),
            "INFO": self._paint("·", GREEN),
        }
        return markers.get(state, self._paint("·", GREEN))

    def start(self):
        print()
        self._rule("═")
        print(self._box_line("║", "║", " "))
        print(f"║  {self._paint('CYBERLAB AGENT', GREEN):<{self._inner_width - 2}}║")
        print(f"║  {'STARTUP STATUS':<{self._inner_width - 2}}║")
        print(self._box_line("║", "║", " "))
        print(self._table_border("╠", "╬", "╣"))
        print(f"║  {'STATUS':<9} │ {'COMPONENT':<13} │ {'DETAILS':<{max(8, self._inner_width - 31)}}║")
        print(self._table_border("╠", "╬", "╣"))

    def row(self, component, detail, state="OK"):
        """Print one wrapped row in the startup status table."""
        marker = self._status_marker(state)
        component_text = str(component)
        detail_lines = textwrap.wrap(
            str(detail),
            width=max(8, self._inner_width - 31),
            break_long_words=True,
        ) or [""]
        status = f"{marker} {state:<5}"
        for index, line in enumerate(detail_lines):
            status_cell = status if index == 0 else " " * 7
            component_cell = component_text if index == 0 else ""
            print(
                f"║  {status_cell:<9} │ {component_cell:<13} │ "
                f"{line:<{max(8, self._inner_width - 31)}}║"
            )
        print(self._table_border("╠", "╬", "╣"))

    def section(self, title, state="INFO"):
        """Start a titled section while keeping headings in default text."""
        print()
        print(self._table_border("╔", "═", "╗"))
        title_text = str(title).upper()
        print(f"║  {title_text:<{self._inner_width - 2}}║")
        print(self._table_border("╠", "═", "╣"))

    def session_card(self, number, summary, state="INFO"):
        """Render one saved-session summary in its own bordered card."""
        marker = self._status_marker(state)
        title = f"{marker} SESSION {number}"
        summary_lines = textwrap.wrap(
            str(summary),
            width=max(12, self._inner_width - 6),
            break_long_words=True,
        ) or [""]
        print(f"║  {title:<{self._inner_width - 2}}║")
        for line in summary_lines:
            print(f"║  {line:<{self._inner_width - 2}}║")
        print(self._table_border("╠", "═", "╣"))

    def close_section(self):
        print(self._table_border("╚", "═", "╝"))

    def detail_card(self, title, lines):
        """Render localized saved-session details in one separate card."""
        print()
        print(self._table_border("╔", "═", "╗"))
        print(f"║  {str(title):<{self._inner_width - 2}}║")
        print(self._table_border("╠", "═", "╣"))
        for label, value in lines:
            text = f"{label}: {value}"
            wrapped = textwrap.wrap(
                text, width=max(12, self._inner_width - 4), break_long_words=True
            ) or [""]
            for line in wrapped:
                print(f"║  {line:<{self._inner_width - 2}}║")
        print(self._table_border("╚", "═", "╝"))

    def ready(self):
        print()
        self._rule("═")
        print(f"{self._paint('●', GREEN)} AGENT READY")
        print()

    @staticmethod
    def _combine_pasted_lines(first_line, continuation_lines):
        """Combine a terminal paste into one logical user message."""
        lines = [str(first_line or "").rstrip("\r\n")]
        lines.extend(str(line or "").rstrip("\r\n") for line in continuation_lines)
        return "\n".join(lines).strip()

    def _read_pasted_continuation(self, first_line, *, idle_timeout=0.12):
        """Collect lines already queued by a multiline terminal paste."""
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
        self._rule("─")
        print(self._paint("✦ CYBERLAB", GREEN))
        first_line = input("> ")
        return self._read_pasted_continuation(first_line)
