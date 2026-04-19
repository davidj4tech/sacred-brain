from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from memory_governor.mem_policy import canonicalize_memory
from memory_governor.schemas import ObserveRequest, Scope
from memory_governor.scopes import scope_path


def _clamp_confidence(val: float) -> float:
    if val < 0.0:
        return 0.0
    if val > 0.99:
        return 0.99
    return val


def _scope_key(scope: Scope) -> str:
    # Legacy flat key. Retained because existing rows were keyed this way.
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

            try:
                conn.execute("ALTER TABLE working_events ADD COLUMN scope_path TEXT")
            except sqlite3.OperationalError:
                pass
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_working_scope_path ON working_events(scope_path)"
            )
            # Backfill scope_path from legacy scope_kind/scope_id for rows that predate the column
            conn.execute(
                "UPDATE working_events SET scope_path = scope_kind || ':' || scope_id "
                "WHERE scope_path IS NULL AND scope_kind IS NOT NULL AND scope_id IS NOT NULL"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recall_stats (
                    memory_id TEXT PRIMARY KEY,
                    last_recalled_at INTEGER NOT NULL,
                    recall_count INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_recall_last ON recall_stats(last_recalled_at)"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_outcomes (
                    memory_id        TEXT PRIMARY KEY,
                    confidence_delta REAL NOT NULL DEFAULT 0.0,
                    salience_delta   REAL NOT NULL DEFAULT 0.0,
                    disputed         INTEGER NOT NULL DEFAULT 0,
                    stale            INTEGER NOT NULL DEFAULT 0,
                    last_outcome     TEXT,
                    last_outcome_ts  INTEGER,
                    history_json     TEXT NOT NULL DEFAULT '[]'
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_outcomes_last_ts ON memory_outcomes(last_outcome_ts)"
            )

    def bump_recall(self, memory_id: str, now_ts: int | None = None) -> None:
        """Increment recall_count and stamp last_recalled_at for memory_id."""
        if not memory_id:
            return
        ts = int(now_ts or time.time())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO recall_stats(memory_id, last_recalled_at, recall_count)
                VALUES(?, ?, 1)
                ON CONFLICT(memory_id) DO UPDATE SET
                    last_recalled_at = excluded.last_recalled_at,
                    recall_count = recall_stats.recall_count + 1
                """,
                (memory_id, ts),
            )
            conn.commit()

    def get_recall_stats(self, memory_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT memory_id, last_recalled_at, recall_count FROM recall_stats WHERE memory_id=?",
                (memory_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "memory_id": row[0],
            "last_recalled_at": row[1],
            "recall_count": row[2],
        }

    def get_recall_counts(self, memory_ids: list[str]) -> dict[str, int]:
        """Batch lookup for ranking. Returns {memory_id: recall_count} for known ids only."""
        if not memory_ids:
            return {}
        placeholders = ",".join("?" * len(memory_ids))
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT memory_id, recall_count FROM recall_stats WHERE memory_id IN ({placeholders})",
                tuple(memory_ids),
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def recently_recalled_ids(self, since_ts: int) -> list[str]:
        """Memory IDs with last_recalled_at >= since_ts. Used by prune to skip hot memories."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT memory_id FROM recall_stats WHERE last_recalled_at >= ? ORDER BY last_recalled_at DESC",
                (int(since_ts),),
            ).fetchall()
        return [row[0] for row in rows]

    def _outcome_row(self, conn: sqlite3.Connection, memory_id: str) -> dict[str, Any]:
        row = conn.execute(
            "SELECT confidence_delta, salience_delta, disputed, stale, last_outcome, last_outcome_ts, history_json "
            "FROM memory_outcomes WHERE memory_id=?",
            (memory_id,),
        ).fetchone()
        if not row:
            return {
                "confidence_delta": 0.0,
                "salience_delta": 0.0,
                "disputed": 0,
                "stale": 0,
                "last_outcome": None,
                "last_outcome_ts": None,
                "history": [],
            }
        return {
            "confidence_delta": row[0],
            "salience_delta": row[1],
            "disputed": row[2],
            "stale": row[3],
            "last_outcome": row[4],
            "last_outcome_ts": row[5],
            "history": json.loads(row[6] or "[]"),
        }

    def apply_outcome(
        self,
        memory_id: str,
        outcome: str,
        base_confidence: float,
        source: str | None = None,
        note: str | None = None,
        now_ts: int | None = None,
    ) -> dict[str, Any]:
        """Apply an outcome to a memory. Returns {confidence_before, confidence_after, row}."""
        if outcome not in {"good", "bad", "stale"}:
            raise ValueError(f"unknown outcome: {outcome!r}")
        ts = int(now_ts or time.time())
        with sqlite3.connect(self.db_path) as conn:
            current = self._outcome_row(conn, memory_id)
            confidence_before = _clamp_confidence(base_confidence + current["confidence_delta"])

            new_conf_delta = current["confidence_delta"]
            new_sal_delta = current["salience_delta"]
            disputed = current["disputed"]
            stale = current["stale"]

            if outcome == "good":
                new_conf_delta += 0.05
                new_sal_delta += 0.05
            elif outcome == "bad":
                target_effective = confidence_before * 0.7
                new_conf_delta = target_effective - base_confidence
                disputed = 1
            elif outcome == "stale":
                stale = 1

            confidence_after = _clamp_confidence(base_confidence + new_conf_delta)

            history = current["history"]
            history.append({
                "ts": ts,
                "outcome": outcome,
                "source": source,
                "note": note,
                "confidence_before": confidence_before,
                "confidence_after": confidence_after,
            })
            if len(history) > 10:
                history = history[-10:]

            conn.execute(
                """
                INSERT INTO memory_outcomes(memory_id, confidence_delta, salience_delta, disputed, stale, last_outcome, last_outcome_ts, history_json)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    confidence_delta = excluded.confidence_delta,
                    salience_delta   = excluded.salience_delta,
                    disputed         = excluded.disputed,
                    stale            = excluded.stale,
                    last_outcome     = excluded.last_outcome,
                    last_outcome_ts  = excluded.last_outcome_ts,
                    history_json     = excluded.history_json
                """,
                (
                    memory_id, new_conf_delta, new_sal_delta, disputed, stale,
                    outcome, ts, json.dumps(history),
                ),
            )
            conn.commit()

        return {
            "confidence_before": confidence_before,
            "confidence_after": confidence_after,
            "row": {
                "confidence_delta": new_conf_delta,
                "salience_delta": new_sal_delta,
                "disputed": disputed,
                "stale": stale,
                "last_outcome": outcome,
                "last_outcome_ts": ts,
                "history": history,
            },
        }

    def get_outcome(self, memory_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = self._outcome_row(conn, memory_id)
        if row["last_outcome"] is None and row["confidence_delta"] == 0.0 and row["salience_delta"] == 0.0:
            return None
        return row

    def get_outcomes_bulk(self, memory_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not memory_ids:
            return {}
        placeholders = ",".join("?" * len(memory_ids))
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT memory_id, confidence_delta, salience_delta, disputed, stale, last_outcome, last_outcome_ts "
                f"FROM memory_outcomes WHERE memory_id IN ({placeholders})",
                tuple(memory_ids),
            ).fetchall()
        return {
            row[0]: {
                "confidence_delta": row[1],
                "salience_delta": row[2],
                "disputed": bool(row[3]),
                "stale": bool(row[4]),
                "last_outcome": row[5],
                "last_outcome_ts": row[6],
            }
            for row in rows
        }

    def stale_ids(self) -> set[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT memory_id FROM memory_outcomes WHERE stale=1"
            ).fetchall()
        return {row[0] for row in rows}

    def recent_outcome_ids(self, since_ts: int) -> set[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT memory_id FROM memory_outcomes WHERE last_outcome_ts >= ?",
                (int(since_ts),),
            ).fetchall()
        return {row[0] for row in rows}

    def add_working(self, event: ObserveRequest) -> bool:
        """Returns True if inserted, False if deduped."""
        scope_key = _scope_key(event.scope)
        spath = scope_path(event.scope)
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
                INSERT INTO working_events (source, user_id, text, normalized_text, ts, scope_key, scope_kind, scope_id, event_id, metadata, scope_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    spath,
                ),
            )
            conn.commit()
        return True

    def cleanup(self) -> None:
        cutoff = int(time.time() - self.ttl_hours * 3600)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM working_events WHERE ts < ?", (cutoff,))
            conn.commit()

    def recent_for_scope(
        self, scope: Scope, limit: int = 100, include_ancestors: bool = False
    ) -> list[dict[str, Any]]:
        spath = scope_path(scope)
        with sqlite3.connect(self.db_path) as conn:
            if include_ancestors:
                from memory_governor.scopes import ancestor_paths
                paths = ancestor_paths(spath)
                placeholders = ",".join("?" * len(paths))
                rows = conn.execute(
                    f"""
                    SELECT id, source, user_id, text, ts, scope_kind, scope_id, event_id, metadata
                    FROM working_events
                    WHERE scope_path IN ({placeholders})
                    ORDER BY ts DESC
                    LIMIT ?
                    """,
                    (*paths, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, source, user_id, text, ts, scope_kind, scope_id, event_id, metadata
                    FROM working_events
                    WHERE scope_path=?
                       OR (scope_path IS NULL AND scope_kind=? AND scope_id=?)
                    ORDER BY ts DESC
                    LIMIT ?
                    """,
                    (spath, scope.kind, scope.id, limit),
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

    def distinct_scopes(self, prefix: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            if prefix:
                rows = conn.execute(
                    """
                    SELECT scope_path, scope_kind, scope_id, COUNT(*) AS c, MAX(ts) AS last_seen
                    FROM working_events
                    WHERE scope_path IS NOT NULL
                      AND (scope_path = ? OR scope_path LIKE ? || '/%' OR scope_path LIKE '%/' || ?)
                    GROUP BY scope_path
                    ORDER BY last_seen DESC
                    LIMIT ?
                    """,
                    (prefix, prefix, prefix, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT scope_path, scope_kind, scope_id, COUNT(*) AS c, MAX(ts) AS last_seen
                    FROM working_events
                    WHERE scope_path IS NOT NULL
                    GROUP BY scope_path
                    ORDER BY last_seen DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [
            {"path": row[0], "kind": row[1], "id": row[2], "count": row[3], "last_seen": row[4]}
            for row in rows
        ]

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

    def consolidated_cursor(self, scope: Scope) -> int | None:
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

    def append(self, record: dict[str, Any]) -> None:
        ts = int(record.get("timestamp") or time.time())
        record["timestamp"] = ts
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def cleanup(self) -> None:
        if not self.path.exists():
            return
        cutoff = int(time.time() - self.ttl_days * 86400)
        lines = self.path.read_text(encoding="utf-8").splitlines()
        kept: list[str] = []
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
        self.backlog: list[dict[str, Any]] = []
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

    def enqueue(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = {"id": str(uuid.uuid4()), "payload": payload, "ts": int(time.time())}
        self.backlog.append(job)
        self._persist()
        return job

    def pending(self) -> list[dict[str, Any]]:
        return list(self.backlog)

    def mark_done(self, job_id: str) -> None:
        self.backlog = [item for item in self.backlog if item.get("id") != job_id]
        self._persist()
