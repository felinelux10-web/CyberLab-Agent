"""Durable conversation archive, provenance-aware facts, and reusable skills.

The archive is additive: it shares the existing SQLite connection and never
rewrites or deletes legacy session files. FTS5 is optional at runtime; a LIKE
fallback keeps Termux builds without FTS5 usable.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class ConversationArchive:
    """Append-only message history plus provenance-aware long-term memory."""

    def __init__(self, database):
        self.database = database
        self.conn = getattr(database, "conn", None)
        if self.conn is None:
            raise RuntimeError("ConversationArchive requires a connected Database")
        self.fts_available = False
        self.normalized_fts_available = False
        self._initialize()

    def _initialize(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS memory_migrations (
            migration_key TEXT PRIMARY KEY,
            completed_at TEXT NOT NULL,
            imported_sessions INTEGER NOT NULL DEFAULT 0,
            imported_exchanges INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            session_id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            message_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            exchange_id TEXT NOT NULL,
            exchange_index INTEGER NOT NULL,
            speaker TEXT NOT NULL CHECK (speaker IN ('user','assistant','system','tool')),
            content TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'conversation',
            intent TEXT,
            topic TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(session_id, exchange_id, speaker)
        );
        CREATE INDEX IF NOT EXISTS idx_conversation_messages_session_order
            ON conversation_messages(session_id, exchange_index, id);
        CREATE INDEX IF NOT EXISTS idx_conversation_messages_exchange
            ON conversation_messages(session_id, exchange_id);
        CREATE TABLE IF NOT EXISTS memory_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            value TEXT NOT NULL,
            speaker TEXT NOT NULL DEFAULT 'user',
            source_kind TEXT NOT NULL DEFAULT 'explicit',
            source_session_id TEXT,
            source_exchange_id TEXT,
            evidence_message_id INTEGER,
            confidence REAL NOT NULL DEFAULT 1.0,
            status TEXT NOT NULL DEFAULT 'active',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memory_facts_subject
            ON memory_facts(subject, status);
        CREATE TABLE IF NOT EXISTS reusable_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            steps_json TEXT NOT NULL DEFAULT '[]',
            preconditions_json TEXT NOT NULL DEFAULT '[]',
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            last_outcome TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS skill_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL REFERENCES reusable_skills(id),
            outcome TEXT NOT NULL CHECK (outcome IN ('success','failure')),
            context_json TEXT NOT NULL DEFAULT '{}',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_skill_runs_skill
            ON skill_runs(skill_id, id DESC);
        """)
        self._ensure_memory_fact_temporal_schema()
        try:
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS conversation_messages_fts
                USING fts5(content, session_id UNINDEXED, speaker UNINDEXED,
                           tokenize='unicode61')
            """)
            self.fts_available = True
        except Exception:
            self.fts_available = False
        try:
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS conversation_messages_normalized_fts
                USING fts5(normalized_content, session_id UNINDEXED, speaker UNINDEXED,
                           tokenize='unicode61')
            """)
            self.normalized_fts_available = True
        except Exception:
            self.normalized_fts_available = False
        self.conn.commit()

    def _ensure_memory_fact_temporal_schema(self) -> None:
        """Add temporal/provenance fields to the existing fact index, without rebuilding it."""
        columns = {
            str(row[1])
            for row in self.conn.execute("PRAGMA table_info(memory_facts)").fetchall()
        }
        additions = {
            "valid_from": "TEXT",
            "invalidated_at": "TEXT",
            "supersedes": "INTEGER",
            "verification": "TEXT NOT NULL DEFAULT 'candidate'",
            "origin": "TEXT NOT NULL DEFAULT 'unknown'",
        }
        for name, declaration in additions.items():
            if name not in columns:
                self.conn.execute(
                    f"ALTER TABLE memory_facts ADD COLUMN {name} {declaration}"
                )
        self.conn.execute(
            """UPDATE memory_facts
               SET valid_from=COALESCE(NULLIF(valid_from,''), created_at)
               WHERE valid_from IS NULL OR valid_from=''"""
        )
        self.conn.execute(
            """UPDATE memory_facts
               SET origin=CASE
                   WHEN speaker='user' THEN 'user'
                   WHEN source_kind IN ('project_doc','project') THEN 'project_doc'
                   WHEN source_kind='provider' THEN 'provider'
                   WHEN speaker='assistant' THEN 'assistant'
                   ELSE 'unknown'
               END
               WHERE origin IS NULL OR origin='' OR origin='unknown'"""
        )
        self.conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_memory_facts_temporal
               ON memory_facts(source_session_id,predicate,valid_from,invalidated_at)"""
        )

    @staticmethod
    def _extract_explicit_user_fact(text: str) -> tuple[str, str] | None:
        """Extract only narrow first-person assertions; never infer from assistant text."""
        value = " ".join(str(text or "").split()).strip()
        if not value or len(value) > 500 or "?" in value or "؟" in value:
            return None
        arabic = re.match(
            r"^(?:(?:أنا|انا)\s+)?(أستخدم|استخدم|أستعمل|استعمل|أفضل|افضل|أفضّل|أعمل|اعمل|أدرس|ادرس|أتعلم|اتعلم|أعيش|اعيش|أسكن|اسكن|أملك|املك|أمتلك|امتلك|أصب|اصب|أسكب|اسكب|أضيف|اضيف|أنتظر|انتظر|أشكل|اشكل|أطلي|اطلي|ألون|الون)\s+(.+?)\s*[.!،]*$",
            value,
            flags=re.IGNORECASE,
        )
        english = re.match(
            r"^I\s+(use|prefer|work with|study|learn|live in|own)\s+(.+?)\s*[.!]*$",
            value,
            flags=re.IGNORECASE,
        )
        match = arabic or english
        if not match:
            return None
        verb = match.group(1).casefold()
        remainder = str(match.group(2) or "").strip(" .،؛:")
        if not remainder or len(remainder) > 300:
            return None
        mapping = {
            "أستخدم": "uses", "استخدم": "uses", "أستعمل": "uses", "استعمل": "uses",
            "use": "uses", "work with": "uses",
            "أفضل": "prefers", "افضل": "prefers", "أفضّل": "prefers", "prefer": "prefers",
            "أعمل": "works_as", "اعمل": "works_as",
            "أدرس": "studies", "ادرس": "studies", "study": "studies",
            "أتعلم": "learns", "اتعلم": "learns", "learn": "learns",
            "أعيش": "lives_in", "اعيش": "lives_in", "live in": "lives_in",
            "أسكن": "lives_in", "اسكن": "lives_in",
            "أملك": "owns", "املك": "owns", "أمتلك": "owns", "امتلك": "owns", "own": "owns",
            "أصب": "pours", "اصب": "pours", "أسكب": "pours", "اسكب": "pours",
            "أضيف": "adds", "اضيف": "adds",
            "أنتظر": "waits", "انتظر": "waits",
            "أشكل": "shapes", "اشكل": "shapes",
            "أطلي": "paints", "اطلي": "paints", "ألون": "paints", "الون": "paints",
        }
        return mapping.get(verb, "states"), remainder

    def migration_complete(self, migration_key: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM memory_migrations WHERE migration_key=?",
            (str(migration_key),),
        ).fetchone()
        return bool(row)

    def migrate_legacy_dialogue_sessions(self, records: list[dict]) -> dict:
        """Import legacy JSON dialogue transcripts once, without altering source files."""
        migration_key = "legacy_dialogue_transcripts_v2_provenance_repair"
        if not any(isinstance(item, dict) for item in (records or [])):
            # An empty or temporarily unavailable index must remain retryable.
            return {
                "status": "no_source_records",
                "imported_sessions": 0,
                "imported_exchanges": 0,
            }
        completed = self.conn.execute(
            "SELECT 1 FROM memory_migrations WHERE migration_key=?",
            (migration_key,),
        ).fetchone()
        if completed:
            return {"already_migrated": True, "imported_sessions": 0, "imported_exchanges": 0}

        dialogue_records = [
            item for item in (records or [])
            if isinstance(item, dict)
            and str(item.get("session_type") or "").casefold() == "dialogue"
        ]

        def has_transcript(record):
            dialogue = record.get("dialogue_state")
            if not isinstance(dialogue, dict):
                return False
            transcript = dialogue.get("transcript_archive")
            if not isinstance(transcript, list) or not transcript:
                transcript = dialogue.get("exchange_archive")
            failed = dialogue.get("failed_transcript_archive")
            if not isinstance(failed, list) or not failed:
                failed = dialogue.get("failed_exchange_archive")
            return (
                isinstance(transcript, list) and bool(transcript)
            ) or (
                isinstance(failed, list) and bool(failed)
            )

        pending_dialogue_records = [
            item for item in dialogue_records if not has_transcript(item)
        ]
        if dialogue_records and len(pending_dialogue_records) == len(dialogue_records):
            return {
                "status": "no_dialogue_transcripts",
                "imported_sessions": 0,
                "imported_exchanges": 0,
            }

        imported_sessions = 0
        imported_exchanges = 0
        now = _now()
        self.conn.execute("BEGIN")
        try:
            for record in records or []:
                if not isinstance(record, dict):
                    continue
                if str(record.get("session_type") or "").casefold() != "dialogue":
                    continue
                dialogue = record.get("dialogue_state")
                if not isinstance(dialogue, dict):
                    continue
                record_session_id = str(record.get("session_id") or "").strip()
                session_id = str(
                    dialogue.get("session_id") or record_session_id
                ).strip()
                if not session_id:
                    continue
                exchanges = dialogue.get("transcript_archive")
                if not isinstance(exchanges, list) or not exchanges:
                    exchanges = dialogue.get("exchange_archive") or []
                if not isinstance(exchanges, list):
                    exchanges = []
                failed_exchanges = dialogue.get("failed_transcript_archive")
                if not isinstance(failed_exchanges, list) or not failed_exchanges:
                    failed_exchanges = dialogue.get("failed_exchange_archive") or []
                if not isinstance(failed_exchanges, list):
                    failed_exchanges = []
                known_exchange_ids = {
                    str(item.get("exchange_id") or "")
                    for item in exchanges if isinstance(item, dict)
                }
                exchanges = list(exchanges)
                for failed_item in failed_exchanges:
                    if not isinstance(failed_item, dict):
                        continue
                    failed_id = str(failed_item.get("exchange_id") or "")
                    if failed_id and failed_id in known_exchange_ids:
                        continue
                    exchanges.append(failed_item)
                    if failed_id:
                        known_exchange_ids.add(failed_id)
                if not exchanges:
                    continue

                self.conn.execute(
                    """INSERT OR IGNORE INTO conversation_sessions
                       (session_id,title,created_at,updated_at)
                       VALUES (?,?,?,?)""",
                    (
                        session_id,
                        str(record.get("title") or record.get("topic") or "Imported dialogue")[:120],
                        str(record.get("created_at") or now),
                        str(record.get("updated_at") or now),
                    ),
                )
                session_imported = False
                for index, exchange in enumerate(exchanges, 1):
                    if not isinstance(exchange, dict):
                        continue
                    exchange_session = str(exchange.get("session_id") or "").strip()
                    context_kind = str(exchange.get("context_kind") or "").strip()
                    conversation_domain = str(
                        exchange.get("conversation_domain") or ""
                    ).strip()
                    if session_id != record_session_id:
                        # A nested DialogueMemory ID may differ from the outer
                        # checkpoint ID, but the identity bridge requires
                        # explicit dialogue-domain provenance on each exchange.
                        if (
                            exchange_session not in {record_session_id, session_id}
                            or not context_kind
                            or not conversation_domain
                        ):
                            continue
                    elif exchange_session and exchange_session != session_id:
                        continue
                    user = str(exchange.get("user") or "").strip()
                    assistant = str(exchange.get("assistant") or "").strip()
                    if not (user or assistant):
                        continue
                    legacy_id = str(exchange.get("exchange_id") or "").strip()
                    if not legacy_id:
                        seed = session_id + "|" + str(index) + "|" + user + "|" + assistant
                        legacy_id = uuid.uuid5(uuid.NAMESPACE_URL, seed).hex
                    try:
                        exchange_index = int(exchange.get("exchange_index") or index)
                    except (TypeError, ValueError):
                        exchange_index = index
                    created_at = str(
                        exchange.get("timestamp") or exchange.get("created_at") or now
                    )
                    meta_values = dict(exchange.get("metadata") or {})
                    if not isinstance(meta_values, dict):
                        meta_values = {}
                    meta_values.update({
                        "source": "legacy_session_import",
                        "legacy": True,
                        "context_kind": context_kind or None,
                        "conversation_domain": conversation_domain or None,
                        "conversation_act": str(exchange.get("conversation_act") or ""),
                        "context_transition": str(exchange.get("context_transition") or ""),
                        "knowledge_version": exchange.get("knowledge_version"),
                        "response_status": str(exchange.get("response_status") or ""),
                        "response_failed": bool(exchange.get("response_failed")),
                        "failure_message": str(exchange.get("failure_message") or ""),
                        "recall_only": bool(exchange.get("recall_only")),
                        "state_boundary_only": bool(exchange.get("state_boundary_only")),
                        "confidence": exchange.get("confidence"),
                    })
                    meta = _json({
                        key: value for key, value in meta_values.items()
                        if value is not None and value != ""
                    })
                    user_message_id = None
                    exchange_inserted = False
                    for speaker, body in (("user", user), ("assistant", assistant)):
                        if not body:
                            continue
                        cursor = self.conn.execute(
                            """INSERT OR IGNORE INTO conversation_messages
                               (session_id,exchange_id,exchange_index,speaker,content,
                                source,intent,topic,metadata_json,created_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (
                                session_id, legacy_id, exchange_index, speaker, body,
                                "legacy_json", exchange.get("intent"),
                                exchange.get("target"), meta, created_at,
                            ),
                        )
                        if cursor.rowcount <= 0:
                            continue
                        session_imported = True
                        exchange_inserted = True
                        if speaker == "user":
                            user_message_id = int(cursor.lastrowid)
                        if self.fts_available:
                            self.conn.execute(
                                """INSERT INTO conversation_messages_fts
                                   (rowid,content,session_id,speaker)
                                   VALUES (?,?,?,?)""",
                                (int(cursor.lastrowid), body, session_id, speaker),
                            )
                        self._index_normalized_message(
                            int(cursor.lastrowid), body, session_id, speaker,
                        )
                    explicit_fact = self._extract_explicit_user_fact(user)
                    if explicit_fact and user_message_id is not None:
                        predicate, fact_value = explicit_fact
                        self.conn.execute(
                            """INSERT INTO memory_facts
                               (subject,predicate,value,speaker,source_kind,source_session_id,
                                source_exchange_id,evidence_message_id,confidence,status,
                                metadata_json,created_at,updated_at,valid_from,invalidated_at,
                                supersedes,verification,origin)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                "user", predicate, fact_value, "user", "explicit",
                                session_id, legacy_id, user_message_id, 0.94, "active",
                                _json({"extraction": "legacy_first_person_assertion"}),
                                created_at, created_at, created_at, None, None,
                                "candidate", "user",
                            ),
                        )
                    if user_message_id is None and user:
                        existing_user = self.conn.execute(
                            """SELECT id FROM conversation_messages
                               WHERE session_id=? AND exchange_id=? AND speaker='user'""",
                            (session_id, legacy_id),
                        ).fetchone()
                        user_message_id = int(existing_user[0]) if existing_user else None
                    existing_assistant = self.conn.execute(
                        """SELECT id FROM conversation_messages
                           WHERE session_id=? AND exchange_id=? AND speaker='assistant'""",
                        (session_id, legacy_id),
                    ).fetchone()
                    assistant_message_id = (
                        int(existing_assistant[0]) if existing_assistant else None
                    )
                    if not exchange.get("recall_only") and not exchange.get("state_boundary_only"):
                        normalized_user = " ".join(user.split())
                        user_correction = bool(
                            re.match(r"^(?:بل|التصحيح|أصحح|اصحح|أقصد|اقصد)\b", normalized_user)
                            or "التصحيح أن" in normalized_user
                            or "التصحيح هو" in normalized_user
                        )
                        self._store_structured_facts(
                            session_id=session_id, exchange_id=legacy_id, speaker="user",
                            text=user, topic=str(exchange.get("target") or "") or None,
                            evidence_message_id=user_message_id, created_at=created_at,
                            correction=user_correction,
                        )
                        if assistant and not exchange.get("response_failed") and str(
                            exchange.get("response_status") or ""
                        ).casefold() != "needs_clarification":
                            self._store_structured_facts(
                                session_id=session_id, exchange_id=legacy_id, speaker="assistant",
                                text=assistant, topic=str(exchange.get("target") or "") or None,
                                evidence_message_id=assistant_message_id, created_at=created_at,
                            )
                    if exchange_inserted:
                        imported_exchanges += 1
                if session_imported:
                    imported_sessions += 1
                    self.conn.execute(
                        """UPDATE conversation_sessions SET
                           message_count=(SELECT COUNT(*) FROM conversation_messages WHERE session_id=?),
                           updated_at=? WHERE session_id=?""",
                        (session_id, now, session_id),
                    )
            if not pending_dialogue_records:
                self.conn.execute(
                    """INSERT INTO memory_migrations
                       (migration_key,completed_at,imported_sessions,imported_exchanges)
                       VALUES (?,?,?,?)""",
                    (migration_key, now, imported_sessions, imported_exchanges),
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return {
            "already_migrated": False,
            "status": "partial_retryable" if pending_dialogue_records else "migrated",
            "pending_dialogue_records": len(pending_dialogue_records),
            "imported_sessions": imported_sessions,
            "imported_exchanges": imported_exchanges,
        }

    def _store_structured_facts(
        self, *, session_id: str, exchange_id: str, speaker: str,
        text: str, topic: str | None, evidence_message_id: int | None,
        created_at: str, correction: bool = False,
    ) -> int:
        """Persist conservative attribute/value facts with exchange-level provenance."""
        if not text or speaker not in {"user", "assistant"}:
            return 0
        if not evidence_message_id:
            row = self.conn.execute(
                """SELECT id FROM conversation_messages
                   WHERE session_id=? AND exchange_id=? AND speaker=?""",
                (session_id, exchange_id, speaker),
            ).fetchone()
            evidence_message_id = int(row[0]) if row else None
        if not evidence_message_id:
            return 0

        from lab_v4_dev.memory.dialogue_knowledge import (
            _extract_structured_facts,
            _split_knowledge_sentences,
        )
        inserted = 0
        sentences = [text, *_split_knowledge_sentences(text)]
        for sentence in sentences:
            for fact in _extract_structured_facts(sentence):
                predicate = str(fact.get("attribute") or "").strip()
                value = str(fact.get("value") or "").strip()
                if not predicate or not value:
                    continue
                superseded_ids = []
                if correction and speaker == "user" and topic:
                    prior_rows = self.conn.execute(
                        """SELECT id, metadata_json FROM memory_facts
                           WHERE source_session_id=? AND speaker='user'
                             AND predicate=? AND status='active'
                             AND invalidated_at IS NULL
                             AND source_exchange_id<>?""",
                        (session_id, predicate, exchange_id),
                    ).fetchall()
                    for prior in prior_rows:
                        try:
                            prior_meta = json.loads(prior["metadata_json"] or "{}")
                        except (TypeError, ValueError, json.JSONDecodeError):
                            prior_meta = {}
                        if isinstance(prior_meta, dict) and str(
                            prior_meta.get("topic_id") or ""
                        ) == str(topic):
                            prior_id = int(prior["id"])
                            self.conn.execute(
                                """UPDATE memory_facts
                                   SET status='superseded', invalidated_at=?, updated_at=?
                                   WHERE id=? AND invalidated_at IS NULL""",
                                (created_at, created_at, prior_id),
                            )
                            superseded_ids.append(prior_id)
                exists = self.conn.execute(
                    """SELECT 1 FROM memory_facts
                       WHERE source_session_id=? AND source_exchange_id=?
                         AND speaker=? AND predicate=? AND value=? LIMIT 1""",
                    (session_id, exchange_id, speaker, predicate, value),
                ).fetchone()
                if exists:
                    continue
                self.conn.execute(
                    """INSERT INTO memory_facts
                       (subject,predicate,value,speaker,source_kind,source_session_id,
                        source_exchange_id,evidence_message_id,confidence,status,
                        metadata_json,created_at,updated_at,valid_from,invalidated_at,
                        supersedes,verification,origin)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "user" if speaker == "user" else "assistant",
                        predicate, value, speaker, "structured",
                        session_id, exchange_id, evidence_message_id,
                        float(fact.get("confidence") or 0.75), "active",
                        _json({
                            "attribute": predicate,
                            "topic_id": topic,
                            "evidence_text": fact.get("evidence_text") or sentence,
                            "extraction": "dialogue_knowledge_v5",
                        }),
                        created_at, created_at, created_at, None,
                        max(superseded_ids) if superseded_ids else None,
                        "candidate", "user" if speaker == "user" else "assistant",
                    ),
                )
                inserted += 1
        return inserted

    def migrate_structured_dialogue_facts(self) -> dict:
        """Backfill the versioned structured-fact index from canonical SQLite exchanges."""
        migration_key = "dialogue_structured_facts_v5"
        if self.migration_complete(migration_key):
            return {
                "already_migrated": True,
                "imported_sessions": 0,
                "imported_exchanges": 0,
                "imported_facts": 0,
            }
        session_rows = self.conn.execute(
            "SELECT DISTINCT session_id FROM conversation_messages ORDER BY session_id"
        ).fetchall()
        session_ids = [
            str(row[0] or "").strip()
            for row in session_rows
            if str(row[0] or "").strip()
        ]
        if not session_ids:
            return {
                "status": "no_dialogue_records",
                "imported_sessions": 0,
                "imported_exchanges": 0,
                "imported_facts": 0,
            }

        now = _now()
        imported_exchanges = 0
        imported_facts = 0
        self.conn.execute("BEGIN")
        try:
            for sid in session_ids:
                for exchange in self.load_exchanges(sid):
                    exchange_id = str(exchange.get("exchange_id") or "").strip()
                    if not exchange_id:
                        continue
                    if exchange.get("recall_only") or exchange.get("state_boundary_only"):
                        continue
                    user_text = str(exchange.get("user") or "")
                    assistant_text = str(exchange.get("assistant") or "")
                    created_at = str(exchange.get("timestamp") or now)
                    topic = str(exchange.get("target") or "").strip() or None
                    user_row = self.conn.execute(
                        """SELECT id FROM conversation_messages
                           WHERE session_id=? AND exchange_id=? AND speaker='user'""",
                        (sid, exchange_id),
                    ).fetchone()
                    assistant_row = self.conn.execute(
                        """SELECT id FROM conversation_messages
                           WHERE session_id=? AND exchange_id=? AND speaker='assistant'""",
                        (sid, exchange_id),
                    ).fetchone()
                    normalized_user = " ".join(user_text.split())
                    user_correction = bool(
                        re.match(
                            r"^(?:بل|التصحيح|أصحح|اصحح|أقصد|اقصد)\b",
                            normalized_user,
                        )
                        or "التصحيح أن" in normalized_user
                        or "التصحيح هو" in normalized_user
                    )
                    imported_facts += self._store_structured_facts(
                        session_id=sid,
                        exchange_id=exchange_id,
                        speaker="user",
                        text=user_text,
                        topic=topic,
                        evidence_message_id=int(user_row[0]) if user_row else None,
                        created_at=created_at,
                        correction=user_correction,
                    )
                    response_status = str(exchange.get("response_status") or "").casefold()
                    if (
                        assistant_text
                        and not exchange.get("response_failed")
                        and response_status != "needs_clarification"
                    ):
                        imported_facts += self._store_structured_facts(
                            session_id=sid,
                            exchange_id=exchange_id,
                            speaker="assistant",
                            text=assistant_text,
                            topic=topic,
                            evidence_message_id=(
                                int(assistant_row[0]) if assistant_row else None
                            ),
                            created_at=created_at,
                        )
                    imported_exchanges += 1
            self.conn.execute(
                """INSERT INTO memory_migrations
                   (migration_key,completed_at,imported_sessions,imported_exchanges)
                   VALUES (?,?,?,?)""",
                (migration_key, now, len(session_ids), imported_exchanges),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return {
            "already_migrated": False,
            "status": "migrated",
            "imported_sessions": len(session_ids),
            "imported_exchanges": imported_exchanges,
            "imported_facts": imported_facts,
        }

    def max_exchange_index(self, session_id: str) -> int:
        """Return the durable per-session exchange high-water mark."""
        sid = str(session_id or "").strip()
        if not sid:
            return 0
        row = self.conn.execute(
            "SELECT COALESCE(MAX(exchange_index), 0) FROM conversation_messages WHERE session_id=?",
            (sid,),
        ).fetchone()
        try:
            return max(0, int(row[0] if row else 0))
        except (TypeError, ValueError, OverflowError):
            return 0

    def append_exchange(
        self, *, session_id: str, user_text: str, assistant_text: str,
        source: str = "conversation", intent: str | None = None,
        topic: str | None = None, status: str | None = None,
        metadata: dict | None = None, exchange_id: str | None = None,
        exchange_index: int | None = None, created_at: str | None = None,
    ) -> str | None:
        """Persist one canonical exchange idempotently, preserving its source identity."""
        sid = str(session_id or "").strip()
        user = str(user_text or "").strip()
        assistant = str(assistant_text or "").strip()
        if not sid or not (user or assistant):
            return None
        canonical_id = str(exchange_id or uuid.uuid4().hex).strip()
        if not canonical_id:
            return None
        now = str(created_at or _now())
        meta = dict(metadata or {})
        if status:
            meta.setdefault("status", str(status))
            meta.setdefault("response_status", str(status))
        try:
            requested_index = int(exchange_index) if exchange_index is not None else 0
        except (TypeError, ValueError, OverflowError):
            requested_index = 0

        self.conn.execute("BEGIN")
        try:
            self.conn.execute(
                """INSERT OR IGNORE INTO conversation_sessions
                   (session_id, title, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (sid, (user[:120] if user else "Conversation"), now, now),
            )
            existing_rows = self.conn.execute(
                """SELECT speaker, content, exchange_index, created_at, metadata_json
                   FROM conversation_messages
                   WHERE session_id=? AND exchange_id=?""",
                (sid, canonical_id),
            ).fetchall()
            existing = {str(row["speaker"]): dict(row) for row in existing_rows}
            for speaker, body in (("user", user), ("assistant", assistant)):
                prior = existing.get(speaker)
                if body and prior and str(prior.get("content") or "") != body:
                    raise ValueError(
                        f"exchange identity collision for {sid}/{canonical_id}/{speaker}"
                    )

            if existing_rows:
                persisted_index = int(existing_rows[0]["exchange_index"] or 0)
                if persisted_index > 0:
                    requested_index = persisted_index
                persisted_time = str(existing_rows[0]["created_at"] or "")
                if persisted_time:
                    now = persisted_time
            if requested_index <= 0:
                row = self.conn.execute(
                    "SELECT COALESCE(MAX(exchange_index), 0) + 1 "
                    "FROM conversation_messages WHERE session_id=?",
                    (sid,),
                ).fetchone()
                requested_index = int(row[0] if row else 1)

            user_message_id = None
            assistant_message_id = None
            user_inserted = False
            for speaker, body in (("user", user), ("assistant", assistant)):
                if not body:
                    continue
                prior = existing.get(speaker)
                if prior:
                    try:
                        prior_meta = json.loads(prior.get("metadata_json") or "{}")
                    except (TypeError, ValueError, json.JSONDecodeError):
                        prior_meta = {}
                    if not isinstance(prior_meta, dict):
                        prior_meta = {}
                    merged_meta = {**prior_meta, **meta}
                    if merged_meta != prior_meta:
                        self.conn.execute(
                            """UPDATE conversation_messages SET metadata_json=?
                               WHERE session_id=? AND exchange_id=? AND speaker=?""",
                            (_json(merged_meta), sid, canonical_id, speaker),
                        )
                    row = self.conn.execute(
                        """SELECT id FROM conversation_messages
                           WHERE session_id=? AND exchange_id=? AND speaker=?""",
                        (sid, canonical_id, speaker),
                    ).fetchone()
                    if speaker == "user":
                        user_message_id = int(row[0]) if row else None
                    else:
                        assistant_message_id = int(row[0]) if row else None
                    continue
                cursor = self.conn.execute(
                    """INSERT OR IGNORE INTO conversation_messages
                       (session_id, exchange_id, exchange_index, speaker, content,
                        source, intent, topic, metadata_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sid, canonical_id, requested_index, speaker, body,
                        str(source), str(intent) if intent is not None else None,
                        str(topic) if topic is not None else None, _json(meta), now,
                    ),
                )
                if cursor.rowcount > 0:
                    message_id = int(cursor.lastrowid)
                    if speaker == "user":
                        user_message_id = message_id
                        user_inserted = True
                    else:
                        assistant_message_id = message_id
                    if self.fts_available:
                        self.conn.execute(
                            """INSERT OR IGNORE INTO conversation_messages_fts
                               (rowid, content, session_id, speaker)
                               VALUES (?, ?, ?, ?)""",
                            (message_id, body, sid, speaker),
                        )
                    self._index_normalized_message(message_id, body, sid, speaker)

            # Explicit facts are attached only when the canonical user message
            # is first inserted; retries cannot create duplicate fact records.
            if user_inserted and user_message_id is not None:
                explicit_fact = self._extract_explicit_user_fact(user)
                if explicit_fact:
                    predicate, fact_value = explicit_fact
                    self.conn.execute(
                        """INSERT INTO memory_facts
                           (subject,predicate,value,speaker,source_kind,source_session_id,
                            source_exchange_id,evidence_message_id,confidence,status,
                            metadata_json,created_at,updated_at,valid_from,invalidated_at,
                            supersedes,verification,origin)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            "user", predicate, fact_value, "user", "explicit",
                            sid, canonical_id, user_message_id, 0.94, "active",
                            _json({"extraction": "first_person_assertion"}),
                            now, now, now, None, None, "candidate", "user",
                        ),
                    )
            if not meta.get("recall_only") and not meta.get("state_boundary_only"):
                normalized_user = " ".join(user.split())
                user_correction = bool(
                    re.match(r"^(?:بل|التصحيح|أصحح|اصحح|أقصد|اقصد)\b", normalized_user)
                    or "التصحيح أن" in normalized_user
                    or "التصحيح هو" in normalized_user
                )
                self._store_structured_facts(
                    session_id=sid, exchange_id=canonical_id, speaker="user",
                    text=user, topic=str(topic or "") or None,
                    evidence_message_id=user_message_id, created_at=now,
                    correction=user_correction,
                )
                if assistant and not meta.get("response_failed") and str(
                    meta.get("response_status") or status or ""
                ).casefold() != "needs_clarification":
                    self._store_structured_facts(
                        session_id=sid, exchange_id=canonical_id, speaker="assistant",
                        text=assistant, topic=str(topic or "") or None,
                        evidence_message_id=assistant_message_id, created_at=now,
                    )
            self.conn.execute(
                """UPDATE conversation_sessions
                   SET updated_at=?, message_count=(
                       SELECT COUNT(*) FROM conversation_messages WHERE session_id=?
                   ), title=CASE WHEN title='Conversation' AND ?<>'' THEN ? ELSE title END
                   WHERE session_id=?""",
                (now, sid, user, user[:120], sid),
            )
            self.conn.commit()
            return canonical_id
        except Exception:
            self.conn.rollback()
            raise

    @staticmethod
    def _normalized_search_text(value: str) -> str:
        from lab_v4_dev.memory.dialogue_knowledge import _token_list
        return " ".join(_token_list(value))

    @classmethod
    def _normalized_fts_query(cls, query: str) -> str:
        tokens = cls._normalized_search_text(query).split()
        return " OR ".join(
            '"' + token.replace('"', '""') + '"'
            for token in tokens[:20]
        )

    def _index_normalized_message(
        self, message_id: int, content: str, session_id: str, speaker: str,
    ) -> None:
        if not self.normalized_fts_available:
            return
        normalized = self._normalized_search_text(content)
        self.conn.execute(
            """INSERT OR REPLACE INTO conversation_messages_normalized_fts
               (rowid,normalized_content,session_id,speaker)
               VALUES (?,?,?,?)""",
            (int(message_id), normalized, str(session_id), str(speaker)),
        )

    def rebuild_normalized_search_index(self, *, batch_size: int = 200) -> dict:
        """Explicitly rebuild the derived normalized FTS index in bounded batches."""
        if not self.normalized_fts_available:
            return {
                "status": "fts5_unavailable",
                "indexed_messages": 0,
                "complete": False,
            }
        cap = max(1, min(2000, int(batch_size)))
        migration_key = "normalized_conversation_fts_v1"
        self.conn.execute("DELETE FROM memory_migrations WHERE migration_key=?", (migration_key,))
        self.conn.execute("DELETE FROM conversation_messages_normalized_fts")
        self.conn.commit()

        last_id = 0
        indexed = 0
        try:
            while True:
                rows = self.conn.execute(
                    """SELECT id,content,session_id,speaker
                       FROM conversation_messages WHERE id>?
                       ORDER BY id LIMIT ?""",
                    (last_id, cap),
                ).fetchall()
                if not rows:
                    break
                entries = []
                for row in rows:
                    entries.append((
                        int(row[0]),
                        self._normalized_search_text(str(row[1] or "")),
                        str(row[2] or ""),
                        str(row[3] or ""),
                    ))
                self.conn.executemany(
                    """INSERT OR REPLACE INTO conversation_messages_normalized_fts
                       (rowid,normalized_content,session_id,speaker)
                       VALUES (?,?,?,?)""",
                    entries,
                )
                self.conn.commit()
                last_id = int(rows[-1][0])
                indexed += len(entries)
            self.conn.execute(
                """INSERT INTO memory_migrations
                   (migration_key,completed_at,imported_sessions,imported_exchanges)
                   VALUES (?,?,0,0)""",
                (migration_key, _now()),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return {
            "status": "completed",
            "indexed_messages": indexed,
            "complete": True,
            "batch_size": cap,
        }

    @staticmethod
    def _fts_query(query: str) -> str:
        tokens = re.findall(r"[\w\u0600-\u06ff]+", str(query or ""), flags=re.UNICODE)
        stop = {
            "ما", "ماذا", "هل", "هي", "هو", "الذي", "التي", "من", "في",
            "عن", "على", "الى", "إلى", "مع", "هذا", "هذه", "ذلك",
            "the", "what", "which", "did", "do", "i", "you", "me", "my",
        }
        tokens = [
            token for token in tokens
            if token.casefold().replace("أ", "ا").replace("إ", "ا") not in stop
        ]
        return " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens[:20])

    def search_messages(self, query: str, *, session_id: str | None = None,
                        limit: int = 20) -> list[dict]:
        needle = str(query or "").strip()
        if not needle:
            return []
        cap = max(1, min(100, int(limit)))
        if (
            self.normalized_fts_available
            and self.migration_complete("normalized_conversation_fts_v1")
        ):
            expression = self._normalized_fts_query(needle)
            if expression:
                sql = """SELECT m.* FROM conversation_messages_normalized_fts f
                         JOIN conversation_messages m ON m.id=f.rowid
                         WHERE conversation_messages_normalized_fts MATCH ?"""
                params: list[Any] = [expression]
                if session_id:
                    sql += " AND m.session_id=?"
                    params.append(str(session_id))
                sql += " ORDER BY m.id DESC LIMIT ?"
                params.append(cap)
                try:
                    indexed = [
                        dict(row)
                        for row in self.conn.execute(sql, params).fetchall()
                    ]
                    if indexed:
                        return indexed
                except Exception:
                    pass
        if self.fts_available:
            expression = self._fts_query(needle)
            if expression:
                sql = """SELECT m.* FROM conversation_messages_fts f
                         JOIN conversation_messages m ON m.id=f.rowid
                         WHERE conversation_messages_fts MATCH ?"""
                params: list[Any] = [expression]
                if session_id:
                    sql += " AND m.session_id=?"
                    params.append(str(session_id))
                sql += " ORDER BY m.id DESC LIMIT ?"
                params.append(cap)
                try:
                    indexed = [
                        dict(row)
                        for row in self.conn.execute(sql, params).fetchall()
                    ]
                    # An existing but incomplete/stale FTS index is not proof
                    # that no evidence exists. Fall through to the SQL LIKE
                    # path when FTS returns no rows.
                    if indexed:
                        return indexed
                except Exception:
                    # Preserve the bounded LIKE fallback for SQLite builds
                    # without a working FTS5 tokenizer/index.
                    pass
        tokens = re.findall(r"[\w\u0600-\u06ff]+", needle, flags=re.UNICODE)[:20]
        tokens = tokens or [needle]
        sql = (
            "SELECT * FROM conversation_messages WHERE ("
            + " OR ".join("content LIKE ?" for _ in tokens)
            + ")"
        )
        params: list[Any] = ["%" + token + "%" for token in tokens]
        if session_id:
            sql += " AND session_id=?"
            params.append(str(session_id))
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(cap)
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def read_context(self, message_id: int, *, before: int = 2,
                     after: int = 2) -> list[dict]:
        """Read neighboring exchanges from the same session as a search hit."""
        hit = self.conn.execute(
            "SELECT session_id, exchange_index FROM conversation_messages WHERE id=?",
            (int(message_id),),
        ).fetchone()
        if not hit:
            return []
        sid, index = str(hit[0]), int(hit[1])
        low = max(1, index - max(0, min(20, int(before))))
        high = index + max(0, min(20, int(after)))
        rows = self.conn.execute(
            """SELECT * FROM conversation_messages
               WHERE session_id=? AND exchange_index BETWEEN ? AND ?
               ORDER BY exchange_index, CASE speaker WHEN 'user' THEN 0 ELSE 1 END, id""",
            (sid, low, high),
        ).fetchall()
        return [dict(row) for row in rows]

    def load_exchanges(self, session_id: str) -> list[dict]:
        """Return the complete ordered transcript grouped into user/assistant exchanges."""
        sid = str(session_id or "").strip()
        if not sid:
            return []
        rows = self.conn.execute(
            """SELECT * FROM conversation_messages WHERE session_id=?
               ORDER BY exchange_index, CASE speaker WHEN 'user' THEN 0 ELSE 1 END, id""",
            (sid,),
        ).fetchall()
        grouped: dict[str, dict] = {}
        order: list[str] = []
        for row in rows:
            item = dict(row)
            exchange_id = str(item.get("exchange_id") or "")
            if not exchange_id:
                continue
            try:
                metadata = json.loads(item.get("metadata_json") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            response_status = str(
                metadata.get("response_status") or metadata.get("status") or ""
            ).casefold()
            response_failed = response_status in {
                "error", "failed", "denied", "unsupported",
            } or bool(metadata.get("response_failed"))
            if exchange_id not in grouped:
                grouped[exchange_id] = {
                    "session_id": sid,
                    "exchange_id": exchange_id,
                    "exchange_index": int(item.get("exchange_index") or 0),
                    "user": "",
                    "assistant": "",
                    "target": item.get("topic"),
                    "intent": item.get("intent"),
                    "timestamp": item.get("created_at"),
                    "source": item.get("source"),
                    "metadata": metadata,
                    "context_kind": metadata.get("context_kind"),
                    "conversation_domain": metadata.get("conversation_domain"),
                    "conversation_act": metadata.get("conversation_act"),
                    "context_transition": metadata.get("context_transition"),
                    "knowledge_version": metadata.get("knowledge_version"),
                    "recall_only": bool(metadata.get("recall_only")),
                    "state_boundary_only": bool(metadata.get("state_boundary_only")),
                    "response_status": response_status,
                    "response_failed": response_failed,
                    "failure_message": str(
                        metadata.get("failure_message")
                        or metadata.get("error_message")
                        or ""
                    ),
                }
                order.append(exchange_id)
            if item.get("speaker") == "user":
                grouped[exchange_id]["user"] = item.get("content") or ""
            elif item.get("speaker") == "assistant":
                grouped[exchange_id]["assistant"] = item.get("content") or ""
        return [grouped[key] for key in order]

    def validate_fact(self, fact_id: int) -> dict:
        """Validate fact provenance against its exact source message before prompt use."""
        row = self.conn.execute(
            """SELECT f.*,m.session_id AS message_session_id,
                      m.exchange_id AS message_exchange_id,
                      m.speaker AS message_speaker,
                      m.content AS message_content
               FROM memory_facts f
               LEFT JOIN conversation_messages m ON m.id=f.evidence_message_id
               WHERE f.id=?""",
            (int(fact_id),),
        ).fetchone()
        if row is None:
            return {"status": "missing", "fact_id": int(fact_id)}
        fact = dict(row)
        reason = None
        if not fact.get("evidence_message_id") or fact.get("message_content") is None:
            reason = "missing_source_message"
        elif str(fact.get("source_session_id") or "") != str(fact.get("message_session_id") or ""):
            reason = "source_session_mismatch"
        elif (
            fact.get("source_exchange_id")
            and str(fact.get("source_exchange_id")) != str(fact.get("message_exchange_id") or "")
        ):
            reason = "source_exchange_mismatch"
        elif str(fact.get("speaker") or "") != str(fact.get("message_speaker") or ""):
            reason = "source_speaker_mismatch"
        else:
            expected_origin = {
                "user": "user",
                "assistant": "assistant",
            }.get(str(fact.get("speaker") or "").casefold())
            origin = str(fact.get("origin") or "unknown").casefold()
            source_kind = str(fact.get("source_kind") or "").casefold()
            if expected_origin and origin not in {expected_origin, "provider"}:
                reason = "origin_speaker_mismatch"
            elif origin == "project_doc" and source_kind not in {"project", "project_doc"}:
                reason = "origin_source_kind_mismatch"
            elif origin == "provider" and source_kind != "provider":
                reason = "origin_source_kind_mismatch"
            else:
                try:
                    metadata = json.loads(fact.get("metadata_json") or "{}")
                except (TypeError, ValueError, json.JSONDecodeError):
                    metadata = {}
                source_text = (
                    str(metadata.get("evidence_text") or "")
                    if isinstance(metadata, dict) else ""
                ) or str(fact.get("message_content") or "")
                normalized_value = self._normalized_search_text(str(fact.get("value") or ""))
                normalized_source = self._normalized_search_text(source_text)
                if not normalized_value or normalized_value not in normalized_source:
                    reason = "value_not_present_in_source"

        verification = "rejected" if reason else "validated"
        try:
            metadata = json.loads(fact.get("metadata_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["validation"] = {
            "status": verification,
            "reason": reason,
            "validated_at": _now(),
        }
        self.conn.execute(
            """UPDATE memory_facts
               SET verification=?, metadata_json=?, updated_at=?
               WHERE id=?""",
            (verification, _json(metadata), _now(), int(fact_id)),
        )
        return {
            "status": verification,
            "reason": reason,
            "fact_id": int(fact_id),
        }

    def validate_candidate_facts(
        self,
        *,
        source_session_id: str | None = None,
        limit: int = 200,
    ) -> dict:
        """Validate a bounded batch of candidate facts with exact source links."""
        sql = "SELECT id FROM memory_facts WHERE verification='candidate'"
        params: list[Any] = []
        if source_session_id:
            sql += " AND source_session_id=?"
            params.append(str(source_session_id))
        sql += " ORDER BY id LIMIT ?"
        params.append(max(1, min(200, int(limit))))
        ids = [
            int(row[0])
            for row in self.conn.execute(sql, params).fetchall()
        ]
        results = [self.validate_fact(fact_id) for fact_id in ids]
        return {
            "checked": len(results),
            "validated": sum(item["status"] == "validated" for item in results),
            "rejected": sum(item["status"] == "rejected" for item in results),
            "candidate": sum(item["status"] == "candidate" for item in results),
        }

    def save_fact(
        self, *, subject: str, predicate: str, value: str,
        speaker: str = "user", source_kind: str = "explicit",
        source_session_id: str | None = None,
        source_exchange_id: str | None = None,
        evidence_message_id: int | None = None,
        confidence: float = 1.0, status: str = "active",
        metadata: dict | None = None,
        valid_from: str | None = None,
        invalidated_at: str | None = None,
        supersedes: int | None = None,
        verification: str = "candidate",
        origin: str | None = None,
    ) -> int:
        """Store a fact with source, verification and temporal provenance."""
        subject, predicate, value = map(lambda x: str(x or "").strip(),
                                        (subject, predicate, value))
        if not subject or not predicate or not value:
            raise ValueError("subject, predicate and value are required")
        verification = str(verification or "candidate").casefold()
        if verification not in {"candidate", "validated", "rejected"}:
            raise ValueError("verification must be candidate, validated or rejected")
        if origin is None:
            if str(speaker).casefold() == "user":
                origin = "user"
            elif str(source_kind).casefold() in {"project", "project_doc"}:
                origin = "project_doc"
            elif str(source_kind).casefold() == "provider":
                origin = "provider"
            elif str(speaker).casefold() == "assistant":
                origin = "assistant"
            else:
                origin = "unknown"
        origin = str(origin).casefold()
        if origin not in {"user", "project_doc", "provider", "assistant", "unknown"}:
            raise ValueError("origin must be user, project_doc, provider, assistant or unknown")
        score = max(0.0, min(1.0, float(confidence)))
        now = _now()
        effective_valid_from = str(valid_from or now)
        cur = self.conn.execute(
            """INSERT INTO memory_facts
               (subject,predicate,value,speaker,source_kind,source_session_id,
                source_exchange_id,evidence_message_id,confidence,status,
                metadata_json,created_at,updated_at,valid_from,invalidated_at,
                supersedes,verification,origin)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (subject, predicate, value, str(speaker), str(source_kind),
             source_session_id, source_exchange_id, evidence_message_id,
             score, str(status), _json(metadata or {}), now, now,
             effective_valid_from, invalidated_at, supersedes,
             verification, origin),
        )
        fact_id = int(cur.lastrowid)
        if evidence_message_id:
            self.validate_fact(fact_id)
        self.conn.commit()
        return fact_id

    def save_user_fact(self, *, subject: str = "user", predicate: str,
                       value: str, **provenance) -> int:
        return self.save_fact(
            subject=subject, predicate=predicate, value=value,
            speaker="user", source_kind="explicit", **provenance
        )

    def save_agent_knowledge(self, *, subject: str = "agent", predicate: str,
                             value: str, **provenance) -> int:
        return self.save_fact(
            subject=subject, predicate=predicate, value=value,
            speaker="assistant", source_kind="agent_knowledge", **provenance
        )

    def save_assistant_suggestion(self, *, subject: str = "user", predicate: str,
                                  value: str, **provenance) -> int:
        return self.save_fact(
            subject=subject, predicate=predicate, value=value,
            speaker="assistant", source_kind="suggestion", **provenance
        )

    def search_facts(
        self,
        query: str = "",
        *,
        subject: str | None = None,
        speaker: str | None = None,
        source_kind: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        sql = "SELECT * FROM memory_facts WHERE status='active' AND invalidated_at IS NULL AND verification<>'rejected'"
        params: list[Any] = []
        if subject:
            sql += " AND subject=?"
            params.append(str(subject))
        if speaker:
            sql += " AND speaker=?"
            params.append(str(speaker))
        if source_kind:
            sql += " AND source_kind=?"
            params.append(str(source_kind))
        if query:
            sql += " AND (subject LIKE ? OR predicate LIKE ? OR value LIKE ?)"
            pattern = "%" + str(query) + "%"
            params.extend([pattern, pattern, pattern])
        sql += " ORDER BY confidence DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(200, int(limit))))
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def get_fact_history(
        self,
        *,
        subject: str | None = None,
        predicate: str | None = None,
        source_session_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Return active and superseded fact versions with their source links."""
        sql = "SELECT * FROM memory_facts WHERE 1=1"
        params: list[Any] = []
        if subject:
            sql += " AND subject=?"
            params.append(str(subject))
        if predicate:
            sql += " AND predicate=?"
            params.append(str(predicate))
        if source_session_id:
            sql += " AND source_session_id=?"
            params.append(str(source_session_id))
        sql += " ORDER BY COALESCE(valid_from,created_at), id LIMIT ?"
        params.append(max(1, min(500, int(limit))))
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def search_relevant_facts(self, query: str, *, limit: int = 12) -> list[dict]:
        """Retrieve user facts using meaningful query terms and verb synonyms."""
        text = str(query or "")
        tokens = re.findall(r"[\w\u0600-\u06ff]+", text, flags=re.UNICODE)
        stop = {
            "ما", "ماذا", "هل", "انا", "أنا", "انت", "أنت", "الذي", "التي",
            "هو", "هي", "من", "في", "عن", "على", "الى", "إلى", "مع",
            "the", "what", "which", "did", "do", "i", "you", "my", "me",
        }
        terms = []
        for token in tokens:
            normalized = token.casefold().replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
            if normalized in stop or len(normalized) < 3:
                continue
            terms.append(normalized)
            if normalized.startswith(("استخدم", "استعمل")):
                terms.append("uses")
            elif normalized.startswith(("افضل", "احب")):
                terms.append("prefers")
        found = {}
        for term in dict.fromkeys(terms):
            # Personal-memory retrieval is user-authored evidence only.
            # Assistant knowledge and suggestions remain separately searchable
            # through search_facts(..., speaker="assistant").
            for fact in self.search_facts(
                term, subject="user", speaker="user", limit=limit
            ):
                found[int(fact["id"])] = fact
        return sorted(
            found.values(),
            key=lambda item: (float(item.get("confidence") or 0), str(item.get("updated_at") or "")),
            reverse=True,
        )[:max(1, min(50, int(limit)))]

    def save_skill(self, *, name: str, description: str = "",
                   steps: list | None = None, preconditions: list | None = None) -> int:
        label = str(name or "").strip()
        if not label:
            raise ValueError("skill name is required")
        now = _now()
        self.conn.execute(
            """INSERT INTO reusable_skills
               (name,description,steps_json,preconditions_json,updated_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                 description=excluded.description,
                 steps_json=excluded.steps_json,
                 preconditions_json=excluded.preconditions_json,
                 updated_at=excluded.updated_at""",
            (label, str(description or ""), _json(steps or []),
             _json(preconditions or []), now),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM reusable_skills WHERE name=?", (label,)
        ).fetchone()
        return int(row[0])

    def record_skill_run(self, skill_id: int, *, success: bool,
                         context: dict | None = None, notes: str = "") -> None:
        outcome = "success" if success else "failure"
        now = _now()
        self.conn.execute("BEGIN")
        try:
            self.conn.execute(
                """INSERT INTO skill_runs(skill_id,outcome,context_json,notes,created_at)
                   VALUES (?,?,?,?,?)""",
                (int(skill_id), outcome, _json(context or {}), str(notes or ""), now),
            )
            column = "success_count" if success else "failure_count"
            self.conn.execute(
                f"""UPDATE reusable_skills SET {column}={column}+1,
                    last_outcome=?, updated_at=? WHERE id=?""",
                (outcome, now, int(skill_id)),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def search_skills(self, query: str = "", *, limit: int = 20) -> list[dict]:
        sql = "SELECT * FROM reusable_skills"
        params: list[Any] = []
        if query:
            sql += " WHERE name LIKE ? OR description LIKE ? OR steps_json LIKE ?"
            pattern = "%" + str(query) + "%"
            params.extend([pattern, pattern, pattern])
        sql += " ORDER BY CASE WHEN (success_count + failure_count)=0 THEN 0 ELSE (success_count * 1.0 / (success_count + failure_count)) END DESC, success_count DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(100, int(limit))))
        result = []
        for row in self.conn.execute(sql, params).fetchall():
            item = dict(row)
            for key in ("steps_json", "preconditions_json"):
                try:
                    item[key.removesuffix("_json")] = json.loads(item.pop(key))
                except (TypeError, ValueError):
                    item[key.removesuffix("_json")] = []
            result.append(item)
        return result

    def search_relevant_skills(self, query: str = "", *, limit: int = 5) -> list[dict]:
        """Return only reusable procedures with a better-than-failed run history."""
        tokens = []
        for raw_token in str(query or "").replace("_", " ").split():
            token = raw_token.strip("؟?!.,،؛:()[]{}\\\\\\\"'").casefold()
            if len(token) >= 3 and token not in {
                "the", "and", "for", "with", "from", "this", "that",
                "من", "على", "الى", "إلى", "في", "عن", "كيف", "ماذا",
                "هل", "اريد", "أريد", "اريد", "اريد",
            } and token not in tokens:
                tokens.append(token)
        if not tokens:
            return []

        candidates: dict[int, dict] = {}
        for token in tokens:
            for skill in self.search_skills(token, limit=max(10, limit * 3)):
                successes = int(skill.get("success_count") or 0)
                failures = int(skill.get("failure_count") or 0)
                if successes < 1 or successes <= failures:
                    continue
                skill_id = int(skill.get("id") or 0)
                if not skill_id:
                    continue
                item = candidates.setdefault(skill_id, dict(skill))
                item["_query_match_count"] = int(
                    item.get("_query_match_count") or 0
                ) + 1

        ranked = sorted(
            candidates.values(),
            key=lambda item: (
                int(item.get("_query_match_count") or 0),
                int(item.get("success_count") or 0)
                / max(
                    1,
                    int(item.get("success_count") or 0)
                    + int(item.get("failure_count") or 0),
                ),
                int(item.get("success_count") or 0),
                str(item.get("updated_at") or ""),
            ),
            reverse=True,
        )
        for item in ranked:
            item.pop("_query_match_count", None)
        return ranked[:max(1, min(20, int(limit)))]
