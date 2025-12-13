from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from memory_governor.mem_policy import canonicalize_memory
from memory_governor.schemas import ObserveRequest, Scope


def _scope_key(scope: Scope) -> str:
    return f"{scope.kind}:{scope.id}"


class WorkingStore:
    """SQLite-backed working/stream memory store with dedupe."""

    def __init__(self, db_path: Path, ttl_hours: int = 24) -> None:
        self.db_path = db_path
        self.ttl_hours = ttl_hours
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS working_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT,
                    user_id TEXT,
                    text TEXT,
                    normalized_text TEXT,
                    ts INTEGER,
                    scope_key TEXT,
                    scope_kind TEXT,
                    scope_id TEXT,
                    event_id TEXT,
                    metadata TEXT,
                    inserted_at INTEGER DEFAULT (strftime('%s','now')),
                    consolidated INTEGER DEFAULT 0
                );
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_working_event ON working_events(source, event_id) WHERE event_id IS NOT NULL;"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS consolidation_state (
                    scope_key TEXT PRIMARY KEY,
                    last_ts INTEGER
                );
                """
            )
            conn.commit()
            # Ensure normalized_text exists (SQLite add column is idempotent)
            try:
                conn.execute("ALTER TABLE working_events ADD COLUMN normalized_text TEXT")
            except sqlite3.OperationalError:
                pass

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_working_norm ON working_events(user_id, normalized_text, ts)"
            )

    def add_working(self, event: ObserveRequest) -> bool:
        """Returns True if inserted, False if deduped."""
        scope_key = _scope_key(event.scope)
        metadata_json = json.dumps(event.metadata or {})
        ts = int(event.timestamp or time.time())
        normalized = canonicalize_memory(event.text).lower()
        dedupe_cutoff = ts - 24 * 3600
        with sqlite3.connect(self.db_path) as conn:
            if event.metadata.get("event_id"):
                existing = conn.execute(
                    "SELECT 1 FROM working_events WHERE source=? AND event_id=? LIMIT 1",
                    (event.source, event.metadata["event_id"]),
                ).fetchone()
                if existing:
                    return False
            # Dedupe on normalized text for same user within last 24h
            existing_norm = conn.execute(
                """
                SELECT 1 FROM working_events
                WHERE user_id=? AND normalized_text=? AND ts>=?
                LIMIT 1
                """,
                (event.user_id, normalized, dedupe_cutoff),
            ).fetchone()
            if existing_norm:
                return False
            conn.execute(
                """
                INSERT INTO working_events (source, user_id, text, normalized_text, ts, scope_key, scope_kind, scope_id, event_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.source,
                    event.user_id,
                    event.text,
                    normalized,
                    ts,
                    scope_key,
                    event.scope.kind,
                    event.scope.id,
                    event.metadata.get("event_id"),
                    metadata_json,
                ),
            )
            conn.commit()
        return True

    def cleanup(self) -> None:
        cutoff = int(time.time() - self.ttl_hours * 3600)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM working_events WHERE ts < ?", (cutoff,))
            conn.commit()

    def recent_for_scope(self, scope: Scope, limit: int = 100) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, source, user_id, text, ts, scope_kind, scope_id, event_id, metadata
                FROM working_events
                WHERE scope_kind=? AND scope_id=?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (scope.kind, scope.id, limit),
            ).fetchall()
        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "source": row[1],
                    "user_id": row[2],
                    "text": row[3],
                    "timestamp": row[4],
                    "scope_kind": row[5],
                    "scope_id": row[6],
                    "event_id": row[7],
                    "metadata": json.loads(row[8] or "{}"),
                }
            )
        return results

    def mark_consolidated(self, scope: Scope, up_to_ts: int) -> None:
        scope_key = _scope_key(scope)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO consolidation_state(scope_key, last_ts) VALUES(?, ?)
                ON CONFLICT(scope_key) DO UPDATE SET last_ts=excluded.last_ts
                """,
                (scope_key, up_to_ts),
            )
            conn.commit()

    def consolidated_cursor(self, scope: Scope) -> Optional[int]:
        scope_key = _scope_key(scope)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT last_ts FROM consolidation_state WHERE scope_key=?", (scope_key,)
            ).fetchone()
            return row[0] if row else None


class StreamLog:
    def __init__(self, path: Path, ttl_days: int = 14) -> None:
        self.path = path
        self.ttl_days = ttl_days
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: Dict[str, Any]) -> None:
        ts = int(record.get("timestamp") or time.time())
        record["timestamp"] = ts
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def cleanup(self) -> None:
        if not self.path.exists():
            return
        cutoff = int(time.time() - self.ttl_days * 86400)
        lines = self.path.read_text(encoding="utf-8").splitlines()
        kept: List[str] = []
        for line in lines:
            try:
                obj = json.loads(line)
                if int(obj.get("timestamp", 0)) >= cutoff:
                    kept.append(line)
            except Exception:
                continue
        self.path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


class DurableQueue:
    """In-process queue with JSONL spool."""

    def __init__(self, spool_path: Path) -> None:
        self.spool_path = spool_path
        spool_path.parent.mkdir(parents=True, exist_ok=True)
        self.backlog: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.spool_path.exists():
            return
        for line in self.spool_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                self.backlog.append(json.loads(line))
            except Exception:
                continue

    def _persist(self) -> None:
        lines = [json.dumps(item) for item in self.backlog]
        self.spool_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def enqueue(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        job = {"id": str(uuid.uuid4()), "payload": payload, "ts": int(time.time())}
        self.backlog.append(job)
        self._persist()
        return job

    def pending(self) -> List[Dict[str, Any]]:
        return list(self.backlog)

    def mark_done(self, job_id: str) -> None:
        self.backlog = [item for item in self.backlog if item.get("id") != job_id]
        self._persist()
