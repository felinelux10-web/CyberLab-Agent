"""Unified, scope-explicit retrieval over canonical dialogue exchanges.

Raw user/assistant exchanges remain the source of truth. This module only
selects and ranks evidence; it never rewrites archives or generates answers.
"""
from __future__ import annotations

import json
from typing import Any


class EvidenceRetriever:
    """Retrieve provenance-preserving exchanges from one declared scope."""

    VALID_SCOPES = {"live", "saved", "all_saved"}

    @classmethod
    def retrieve(
        cls,
        query: str,
        *,
        scope: str,
        session_id: str | None = None,
        live_state: Any = None,
        archive: Any = None,
        record: dict | None = None,
        limit: int = 8,
    ) -> list[dict]:
        selected_scope = str(scope or "").strip().casefold()
        if selected_scope not in cls.VALID_SCOPES:
            raise ValueError(f"unsupported evidence scope: {scope!r}")
        if not str(query or "").strip():
            return []
        cap = max(1, min(32, int(limit)))

        if selected_scope == "saved":
            wanted = str(session_id or "").strip()
            if not wanted:
                return []
            if record is None:
                from lab_v4_dev.memory.session_state import get_session_by_id
                record = get_session_by_id(wanted)
            if (
                not isinstance(record, dict)
                or str(record.get("session_id") or "").strip() != wanted
                or str(record.get("session_type") or "").casefold() != "dialogue"
            ):
                return []
            return cls._rank_record(record, query, cap, scope="saved", source_session_id=wanted)

        if selected_scope == "live":
            return cls._retrieve_live(
                query, session_id=session_id, live_state=live_state,
                archive=archive, limit=cap,
            )

        from lab_v4_dev.memory.session_state import get_session_index, get_session_by_id
        ranked = []
        for entry in get_session_index():
            if (
                not isinstance(entry, dict)
                or str(entry.get("session_type") or "").casefold() != "dialogue"
            ):
                continue
            source_id = str(entry.get("session_id") or "").strip()
            if not source_id:
                continue
            record = get_session_by_id(source_id)
            if (
                not isinstance(record, dict)
                or str(record.get("session_id") or "").strip() != source_id
                or str(record.get("session_type") or "").casefold() != "dialogue"
            ):
                continue
            ranked.extend(cls._rank_record(
                record, query, cap, scope="all_saved", source_session_id=source_id,
            ))
        ranked.sort(key=lambda item: (
            -float(item.get("score") or 0.0),
            str(item.get("timestamp") or ""),
            int(item.get("exchange_index") or 0),
        ))
        return ranked[:cap]

    @classmethod
    def _rank_record(
        cls,
        record: dict,
        query: str,
        limit: int,
        *,
        scope: str,
        source_session_id: str,
    ) -> list[dict]:
        from lab_v4_dev.memory.dialogue_knowledge import (
            retrieve_completed_dialogue_exchanges,
            _retrieve_dialogue_evidence_core,
        )
        evidence_owner_id, _ = retrieve_completed_dialogue_exchanges(record)
        if not evidence_owner_id:
            return []
        ranked = _retrieve_dialogue_evidence_core(record, query, limit=limit)
        result = []
        for item in ranked:
            if (
                not isinstance(item, dict)
                or str(item.get("session_id") or "").strip() != evidence_owner_id
                or not str(item.get("exchange_id") or "").strip()
                or not item.get("matched_terms")
                or not (
                    item.get("matched_user_terms")
                    or item.get("matched_assistant_terms")
                )
            ):
                continue
            result.append({
                **item,
                "evidence_scope": scope,
                "source_session_id": source_session_id,
            })
        return result

    @classmethod
    def _retrieve_live(
        cls,
        query: str,
        *,
        session_id: str | None,
        live_state: Any,
        archive: Any,
        limit: int,
    ) -> list[dict]:
        from lab_v4_dev.memory.dialogue_knowledge import _retrieve_dialogue_evidence_core
        from lab_v4_dev.memory.session_state import _load_sqlite_dialogue_exchanges

        if isinstance(live_state, dict):
            state = dict(live_state)
        elif live_state is not None:
            snapshot = getattr(live_state, "snapshot", None)
            if callable(snapshot):
                value = snapshot()
                state = dict(value) if isinstance(value, dict) else {}
            else:
                state = {
                    name: getattr(live_state, name, None)
                    for name in (
                        "session_id", "exchange_archive", "transcript_archive",
                        "history", "last_topic",
                    )
                }
        else:
            state = {}

        state_id = str(state.get("session_id") or "").strip()
        wanted = str(session_id or state_id).strip()
        if not wanted or (state_id and state_id != wanted):
            return []

        candidates = []
        for key in ("transcript_archive", "exchange_archive"):
            records = state.get(key)
            if isinstance(records, list):
                candidates.extend(item for item in records if isinstance(item, dict))

        # The durable archive supplements the bounded live snapshot. Search
        # and read neighboring messages only inside the exact owning session.
        durable_search_available = False
        if archive is not None:
            try:
                hits = archive.search_messages(query, session_id=wanted, limit=limit)
                durable_search_available = True
                messages = {}
                for hit in hits:
                    for message in archive.read_context(
                        hit["id"], before=2, after=2,
                    ):
                        messages[int(message["id"])] = message
                grouped = {}
                for message in sorted(
                    messages.values(),
                    key=lambda item: (
                        int(item.get("exchange_index") or 0),
                        0 if item.get("speaker") == "user" else 1,
                        int(item.get("id") or 0),
                    ),
                ):
                    if str(message.get("session_id") or "").strip() != wanted:
                        continue
                    exchange_id = str(message.get("exchange_id") or "").strip()
                    if not exchange_id:
                        continue
                    metadata = message.get("metadata")
                    if not isinstance(metadata, dict):
                        try:
                            metadata = json.loads(message.get("metadata_json") or "{}")
                        except (TypeError, ValueError, json.JSONDecodeError):
                            metadata = {}
                    if not isinstance(metadata, dict):
                        metadata = {}
                    exchange = grouped.setdefault(exchange_id, {
                        "session_id": wanted,
                        "exchange_id": exchange_id,
                        "exchange_index": int(message.get("exchange_index") or 0),
                        "user": "",
                        "assistant": "",
                        "target": message.get("topic"),
                        "intent": message.get("intent"),
                        "timestamp": message.get("created_at"),
                        "metadata": metadata,
                        "context_kind": metadata.get("context_kind"),
                        "conversation_domain": metadata.get("conversation_domain"),
                        "conversation_act": metadata.get("conversation_act"),
                        "recall_only": bool(metadata.get("recall_only")),
                        "state_boundary_only": bool(metadata.get("state_boundary_only")),
                        "response_failed": bool(metadata.get("response_failed")),
                        "response_status": metadata.get("response_status") or metadata.get("status"),
                    })
                    if message.get("speaker") == "user":
                        exchange["user"] = message.get("content") or ""
                    elif message.get("speaker") == "assistant":
                        exchange["assistant"] = message.get("content") or ""
                candidates.extend(grouped.values())
            except Exception:
                # The JSON/DialogueMemory snapshot remains a valid fallback;
                # an unavailable SQLite search must not widen the scope.
                durable_search_available = False

        # Load the complete SQLite transcript only when the indexed search
        # mechanism itself is unavailable, not merely because a valid query
        # returned zero hits. Empty search results must remain bounded.
        if not durable_search_available:
            try:
                candidates.extend(_load_sqlite_dialogue_exchanges(wanted))
            except Exception:
                pass

        by_id = {}
        for item in candidates:
            if not isinstance(item, dict):
                continue
            item_session = str(item.get("session_id") or wanted).strip()
            if item_session != wanted:
                continue
            exchange_id = str(item.get("exchange_id") or "").strip()
            if not exchange_id:
                continue
            prior = by_id.get(exchange_id)
            if prior is None:
                by_id[exchange_id] = dict(item, session_id=wanted)
            else:
                for key, value in item.items():
                    if prior.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
                        prior[key] = value

        data = {
            "session_id": wanted,
            "dialogue_state": {
                "session_id": wanted,
                "transcript_archive": list(by_id.values()),
            },
        }
        ranked = _retrieve_dialogue_evidence_core(data, query, limit=limit)
        return [
            {
                **item,
                "evidence_scope": "live",
                "source_session_id": wanted,
            }
            for item in ranked
            if isinstance(item, dict)
            and str(item.get("session_id") or "").strip() == wanted
            and str(item.get("exchange_id") or "").strip()
            and item.get("matched_terms")
            and (
                item.get("matched_user_terms")
                or item.get("matched_assistant_terms")
            )
        ]
