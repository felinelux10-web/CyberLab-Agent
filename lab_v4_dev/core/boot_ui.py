"""Compact, aligned terminal dashboard for startup status and saved sessions."""

import select
import shutil
import sys
import textwrap

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"


class BootUI:
    """Render compact horizontal/vertical tables for Termux and terminals."""

    def __init__(self):
        self.width = max(32, min(shutil.get_terminal_size((56, 20)).columns, 78))
        self.color = bool(getattr(sys.stdout, "isatty", lambda: False)())

    def _paint(self, text, color):
        return f"{color}{text}{RESET}" if self.color else text

    @property
    def _inner_width(self):
        return max(30, self.width - 2)

    def _rule(self, char="─"):
        print(self._paint(char * self._inner_width, GREEN))

    def _box_line(self, left="│", right="│", fill=" "):
        return f"{left}{fill * self._inner_width}{right}"

    def _table_border(self, left="╠", junction="╬", right="╣"):
        return self._paint(f"{left}{'─' * self._inner_width}{right}", GREEN)

    def _frame_text(self, value=""):
        value = str(value)
        visible = value.replace(GREEN, "").replace(RED, "").replace(RESET, "")
        if len(visible) > self._inner_width:
            value = visible[: max(0, self._inner_width - 1)] + "…"
            visible = value
        padding = " " * max(0, self._inner_width - len(visible))
        print(f"║{value}{padding}║")
    def _status_marker(self, state):
        markers = {
            "OK": GREEN,
            "FAIL": RED,
            "WARN": RED,
            "PENDING": RED,
            "INFO": GREEN,
        }
        return self._paint("●" if state != "INFO" else "·", markers.get(state, GREEN))

    def _status_widths(self):
        component_width = min(12, max(8, self._inner_width // 5))
        status_width = 6
        detail_width = max(
            6, self._inner_width - (1 + status_width + 3 + component_width + 3 + 1)
        )
        return status_width, component_width, detail_width

    def _print_status_header(self):
        status_width, component_width, detail_width = self._status_widths()
        content = (
            f" {'STATUS':<{status_width}} │ "
            f"{'COMPONENT':<{component_width}} │ "
            f"{'DETAILS':<{detail_width}} "
        )
        self._frame_text(content)
        print(self._table_border())

    def start(self):
        print()
        print(self._table_border("╔", "═", "╗"))
        self._frame_text(f"  {self._paint('CYBERLAB AGENT', GREEN)}")
        self._frame_text("  STARTUP STATUS")
        print(self._table_border())
        self._print_status_header()

    def row(self, component, detail, state="OK"):
        """Print one compact, aligned status row with wrapped details."""
        if str(component).upper() == "SESSIONS":
            self._frame_text(f"  {detail}")
            print(self._table_border())
            return

        status_width, component_width, detail_width = self._status_widths()
        detail_lines = textwrap.wrap(
            str(detail),
            width=detail_width,
            break_long_words=True,
            break_on_hyphens=False,
        ) or [""]

        marker = self._status_marker(state)
        visible_status = f"● {state}" if state != "INFO" else "· INFO"
        status_cell = marker + f" {state}"
        status_cell += " " * max(0, status_width - len(visible_status))

        for index, line in enumerate(detail_lines):
            current_status = status_cell if index == 0 else " " * status_width
            component_cell = str(component) if index == 0 else ""
            content = (
                f" {current_status} │ "
                f"{component_cell:<{component_width}} │ "
                f"{line:<{detail_width}} "
            )
            self._frame_text(content)
        print(self._table_border())

    def section(self, title, state="INFO"):
        """Start a titled section; saved sessions use a compact data table."""
        print()
        print(self._table_border("╔", "═", "╗"))
        self._frame_text(f"  {str(title).upper()}")
        print(self._table_border())

        if str(title).strip().casefold() == "saved sessions":
            session_width = 10
            type_width = 10
            topic_width = max(1, self._inner_width - 28)
            content = (
                f" {'SESSION':<{session_width}} │ "
                f"{'TYPE/STATE':<{type_width}} │ "
                f"{'TOPIC':<{topic_width}} "
            )
            self._frame_text(content)
            print(self._table_border())

    def session_card(self, number, summary, state="INFO"):
        """Render a saved session as one compact row, not a separate card."""
        raw_summary = str(summary).strip()
        if " — " in raw_summary:
            topic, label = raw_summary.rsplit(" — ", 1)
        elif " - " in raw_summary:
            topic, label = raw_summary.rsplit(" - ", 1)
        else:
            topic, label = raw_summary, ""

        normalized_label = label.strip().upper()
        if "DIALOGUE" in normalized_label:
            type_state = "DIALOGUE"
        elif "RESUMABLE" in normalized_label:
            type_state = "WORK-RES"
        elif "REVIEW" in normalized_label:
            type_state = "WORK-REV"
        else:
            type_state = "WORK"

        session_width = 10
        type_width = 10
        topic_width = max(1, self._inner_width - 28)
        topic = " ".join(topic.split())
        if len(topic) > topic_width:
            topic = topic[: max(0, topic_width - 1)].rstrip() + "…"

        marker = self._status_marker(state)
        type_cell = marker + " " + type_state
        type_cell += " " * max(0, type_width - len("● " + type_state))
        content = (
            f" SESSION {number:<{max(1, session_width - 8)}} │ "
            f"{type_cell} │ "
            f"{topic:<{topic_width}} "
        )
        self._frame_text(content)
        print(self._table_border())

    def close_section(self):
        print(self._table_border("╚", "═", "╝"))

    def detail_card(self, title, lines):
        """Render localized saved-session details after explicit selection."""
        print()
        print(self._table_border("╔", "═", "╗"))
        self._frame_text(f"  {title}")
        print(self._table_border())
        for label, value in lines:
            text = f"{label}: {value}"
            wrapped = textwrap.wrap(
                text, width=max(12, self._inner_width - 4), break_long_words=True
            ) or [""]
            for line in wrapped:
                self._frame_text(f"  {line}")
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
