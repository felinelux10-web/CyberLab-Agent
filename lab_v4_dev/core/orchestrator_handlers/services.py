"""Explicit service capabilities exposed to handlers; never pass the Agent itself."""

from dataclasses import dataclass
from typing import Any


@dataclass
class HandlerServices:
    state: Any = None
    session: Any = None
    memory: Any = None
    dialogue_memory: Any = None
    restore_session_snapshot: Any = None
    restore_session_context: Any = None
    metadata: Any = None
    db: Any = None
    analyzed_files: Any = None
    impact_analyzed: Any = None


def build_handler_services(orchestrator) -> HandlerServices:
    agent = getattr(orchestrator, "agent", None)

    analyzed_files = getattr(orchestrator, "_analyzed_files", None)
    if analyzed_files is None:
        analyzed_files = set()
        setattr(orchestrator, "_analyzed_files", analyzed_files)

    impact_analyzed = getattr(orchestrator, "_impact_analyzed", None)
    if impact_analyzed is None:
        impact_analyzed = set()
        setattr(orchestrator, "_impact_analyzed", impact_analyzed)

    return HandlerServices(
        state=getattr(agent, "state", None),
        session=getattr(agent, "session", None),
        memory=getattr(agent, "memory", None),
        dialogue_memory=getattr(agent, "dialogue_memory", None),
        restore_session_snapshot=getattr(agent, "restore_session_snapshot", None),
        restore_session_context=getattr(agent, "restore_session_context", None),
        metadata=getattr(agent, "_meta", None),
        db=getattr(agent, "db", None),
        analyzed_files=analyzed_files,
        impact_analyzed=impact_analyzed,
    )


__all__ = ["HandlerServices", "build_handler_services"]
