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
        try:
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS conversation_messages_fts
                USING fts5(content, session_id UNINDEXED, speaker UNINDEXED,
                           tokenize='unicode61')
            """)
            self.fts_available = True
        except Exception:
            self.fts_available = False
        self.conn.commit()

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
        migration_key = "legacy_dialogue_transcripts_v1"
        completed = self.conn.execute(
            "SELECT 1 FROM memory_migrations WHERE migration_key=?",
            (migration_key,),
        ).fetchone()
        if completed:
            return {"already_migrated": True, "imported_sessions": 0, "imported_exchanges": 0}

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
                session_id = str(dialogue.get("session_id") or record.get("session_id") or "").strip()
                if not session_id:
                    continue
                exchanges = dialogue.get("transcript_archive")
                if not isinstance(exchanges, list) or not exchanges:
                    exchanges = dialogue.get("exchange_archive") or []
                if not isinstance(exchanges, list) or not exchanges:
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
                    exchange_session = str(exchange.get("session_id") or session_id).strip()
                    if exchange_session != session_id:
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
                    meta = _json({"source": "legacy_session_import", "legacy": True})
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
                    explicit_fact = self._extract_explicit_user_fact(user)
                    if explicit_fact and user_message_id is not None:
                        predicate, fact_value = explicit_fact
                        self.conn.execute(
                            """INSERT INTO memory_facts
                               (subject,predicate,value,speaker,source_kind,source_session_id,
                                source_exchange_id,evidence_message_id,confidence,status,
                                metadata_json,created_at,updated_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                "user", predicate, fact_value, "user", "explicit",
                                session_id, legacy_id, user_message_id, 0.94, "active",
                                _json({"extraction": "legacy_first_person_assertion"}),
                                created_at, created_at,
                            ),
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
            "imported_sessions": imported_sessions,
            "imported_exchanges": imported_exchanges,
        }

    def append_exchange(
        self, *, session_id: str, user_text: str, assistant_text: str,
        source: str = "conversation", intent: str | None = None,
        topic: str | None = None, status: str | None = None,
        metadata: dict | None = None,
    ) -> str | None:
        """Append both sides of one exchange exactly once under a unique ID."""
        sid = str(session_id or "").strip()
        user = str(user_text or "").strip()
        assistant = str(assistant_text or "").strip()
        if not sid or not (user or assistant):
            return None
        exchange_id = uuid.uuid4().hex
        now = _now()
        meta = dict(metadata or {})
        if status:
            meta["status"] = str(status)
        self.conn.execute("BEGIN")
        try:
            self.conn.execute(
                """INSERT OR IGNORE INTO conversation_sessions
                   (session_id, title, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (sid, (user[:120] if user else "Conversation"), now, now),
            )
            row = self.conn.execute(
                "SELECT COALESCE(MAX(exchange_index), 0) + 1 FROM conversation_messages WHERE session_id=?",
                (sid,),
            ).fetchone()
            exchange_index = int(row[0] if row else 1)
            user_message_id = None
            for speaker, body in (("user", user), ("assistant", assistant)):
                if not body:
                    continue
                cursor = self.conn.execute(
                    """INSERT INTO conversation_messages
                       (session_id, exchange_id, exchange_index, speaker, content,
                        source, intent, topic, metadata_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (sid, exchange_id, exchange_index, speaker, body,
                     str(source), str(intent) if intent is not None else None,
                     str(topic) if topic is not None else None, _json(meta), now),
                )
                message_id = int(cursor.lastrowid)
                if speaker == "user":
                    user_message_id = message_id
                if self.fts_available:
                    self.conn.execute(
                        """INSERT INTO conversation_messages_fts
                           (rowid, content, session_id, speaker)
                           VALUES (?, ?, ?, ?)""",
                        (message_id, body, sid, speaker),
                    )
            explicit_fact = self._extract_explicit_user_fact(user)
            if explicit_fact and user_message_id is not None:
                predicate, fact_value = explicit_fact
                self.conn.execute(
                    """INSERT INTO memory_facts
                       (subject,predicate,value,speaker,source_kind,source_session_id,
                        source_exchange_id,evidence_message_id,confidence,status,
                        metadata_json,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ("user", predicate, fact_value, "user", "explicit", sid,
                     exchange_id, user_message_id, 0.94, "active",
                     _json({"extraction": "first_person_assertion"}), now, now),
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
            return exchange_id
        except Exception:
            self.conn.rollback()
            raise

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
                    return [dict(row) for row in self.conn.execute(sql, params).fetchall()]
                except Exception:
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
                }
                order.append(exchange_id)
            if item.get("speaker") == "user":
                grouped[exchange_id]["user"] = item.get("content") or ""
            elif item.get("speaker") == "assistant":
                grouped[exchange_id]["assistant"] = item.get("content") or ""
        return [grouped[key] for key in order]

    def save_fact(
        self, *, subject: str, predicate: str, value: str,
        speaker: str = "user", source_kind: str = "explicit",
        source_session_id: str | None = None,
        source_exchange_id: str | None = None,
        evidence_message_id: int | None = None,
        confidence: float = 1.0, status: str = "active",
        metadata: dict | None = None,
    ) -> int:
        """Store a fact with explicit provenance; callers own extraction policy."""
        subject, predicate, value = map(lambda x: str(x or "").strip(),
                                        (subject, predicate, value))
        if not subject or not predicate or not value:
            raise ValueError("subject, predicate and value are required")
        score = max(0.0, min(1.0, float(confidence)))
        now = _now()
        cur = self.conn.execute(
            """INSERT INTO memory_facts
               (subject,predicate,value,speaker,source_kind,source_session_id,
                source_exchange_id,evidence_message_id,confidence,status,
                metadata_json,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (subject, predicate, value, str(speaker), str(source_kind),
             source_session_id, source_exchange_id, evidence_message_id,
             score, str(status), _json(metadata or {}), now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def search_facts(self, query: str = "", *, subject: str | None = None,
                     limit: int = 50) -> list[dict]:
        sql = "SELECT * FROM memory_facts WHERE status='active'"
        params: list[Any] = []
        if subject:
            sql += " AND subject=?"
            params.append(str(subject))
        if query:
            sql += " AND (subject LIKE ? OR predicate LIKE ? OR value LIKE ?)"
            pattern = "%" + str(query) + "%"
            params.extend([pattern, pattern, pattern])
        sql += " ORDER BY confidence DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(200, int(limit))))
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
            for fact in self.search_facts(term, limit=limit):
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
