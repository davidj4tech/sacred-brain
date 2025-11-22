"""Adapter that hides the specifics of the Mem0 client."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import ExperienceCreate, MemoryRecord

LOGGER = logging.getLogger(__name__)
DEFAULT_PERSISTENCE_PATH = Path(__file__).resolve().parents[2] / "data" / "hippocampus_memories.sqlite"


@dataclass
class Mem0Adapter:
    api_key: str | None = None
    backend: str = "sqlite"
    summary_max_length: int = 480
    default_query_limit: int = 5
    persistence_path: str | Path | None = None
    client: Any | None = None
    plan: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = self._build_client()
        if self.plan is None:
            self.plan = self._build_adapter_plan()

    def _build_adapter_plan(self) -> str:
        """Describe the Mem0Adapter integration strategy for future work."""
        return (
            "Mem0Adapter plan:\n"
            "1. Detect backend preference (mem0 cloud, sqlite persistence, in-memory).\n"
            "2. Provide a Mem0 SDK client wrapper when API key + package available.\n"
            "3. Keep SQLite fallback as default, with in-memory option for tests.\n"
            "4. Normalise outputs into MemoryRecord structures.\n"
            "Next increment: integrate official Mem0 SDK calls alongside persistence fallback."
        )

    def _build_client(self) -> Any:
        backend = (self.backend or "").lower()
        persistence_path = self._resolve_persistence_path()

        if backend in {"inmemory", "memory"}:
            LOGGER.info("Using in-memory Mem0 backend")
            return InMemoryMem0Client(max_summary_chars=self.summary_max_length)

        if backend in {"sqlite", "persistent", "fallback"}:
            LOGGER.info("Using SQLite persistence backend at %s", persistence_path)
            return self._build_sqlite_client(persistence_path)

        if backend in {"cloud", "mem0", "remote"} and not self.api_key:
            LOGGER.warning("Cloud backend requested but no API key provided; using SQLite fallback at %s", persistence_path)
            return self._build_sqlite_client(persistence_path)

        if self.api_key:
            try:
                return self._build_mem0_client()
            except ModuleNotFoundError as exc:
                LOGGER.warning("mem0 package missing, falling back to SQLite backend: %s", exc)
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Failed to initialise mem0 client, falling back to SQLite backend: %s", exc, exc_info=True)

        LOGGER.info("Mem0 backend not configured; using SQLite fallback at %s", persistence_path)
        return self._build_sqlite_client(persistence_path)

    def _build_mem0_client(self) -> Any:
        module = import_module("mem0")
        client_cls = getattr(module, "Mem0Client", None) or getattr(module, "Mem0", None)
        if not client_cls:
            raise ModuleNotFoundError("Mem0 client class missing")
        return client_cls(api_key=self.api_key)

    def _build_sqlite_client(self, persistence_path: Path) -> "SQLiteMem0Client":
        return SQLiteMem0Client(
            db_path=persistence_path,
            max_summary_chars=self.summary_max_length,
        )

    def _resolve_persistence_path(self) -> Path:
        if self.persistence_path:
            try:
                return Path(self.persistence_path).expanduser()
            except TypeError:
                LOGGER.warning("Invalid persistence path %s, using default", self.persistence_path)
        return DEFAULT_PERSISTENCE_PATH

    def add_experience(self, experience: ExperienceCreate) -> MemoryRecord:
        payload = self.client.add_memory(
            user_id=experience.user_id,
            text=experience.text,
            metadata=experience.metadata,
        )
        return self._to_record(payload)

    def query_memories(self, user_id: str, query: str, limit: Optional[int] = None) -> List[MemoryRecord]:
        result = self.client.query_memories(
            user_id=user_id,
            query=query,
            limit=limit or self.default_query_limit,
        )
        records = []
        for item in result or []:
            records.append(self._to_record(item))
        return records

    def delete_memory(self, memory_id: str) -> bool:
        if hasattr(self.client, "delete_memory"):
            result = self.client.delete_memory(memory_id=memory_id)
            if isinstance(result, bool):
                return result
            if isinstance(result, dict):
                return bool(result.get("deleted", True))
        LOGGER.warning("Mem0 client does not support deletion; returning False")
        return False

    def summarize_texts(self, texts: Iterable[str]) -> str:
        texts = list(texts)
        if not texts:
            return ""
        if hasattr(self.client, "summarize"):
            summary = self.client.summarize(texts=texts, max_length=self.summary_max_length)
            if isinstance(summary, str):
                return summary
        # Fallback heuristic summary
        return _truncate(" ".join(texts), self.summary_max_length)

    def _to_record(self, raw: Dict[str, Any]) -> MemoryRecord:
        if not isinstance(raw, dict):
            raise TypeError("Mem0 client must return dictionaries")
        record_id = raw.get("id") or raw.get("_id") or raw.get("memory_id") or str(uuid.uuid4())
        metadata = raw.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {"value": metadata}
        return MemoryRecord(
            id=str(record_id),
            user_id=str(raw.get("user_id", "unknown")),
            text=str(raw.get("text", "")),
            metadata=metadata,
            score=_maybe_float(raw.get("score")),
        )


@dataclass
class InMemoryMem0Client:
    max_summary_chars: int = 480
    _storage: List[Dict[str, Any]] = field(default_factory=list)

    def add_memory(self, user_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        memory_id = str(uuid.uuid4())
        payload = {
            "id": memory_id,
            "user_id": user_id,
            "text": text,
            "metadata": metadata or {},
            "score": 1.0,
        }
        self._storage.append(payload)
        return payload

    def query_memories(self, user_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        matches = [
            memo
            for memo in self._storage
            if memo["user_id"] == user_id and query_lower in memo["text"].lower()
        ]
        return matches[:limit]

    def summarize(self, texts: List[str], max_length: Optional[int] = None) -> str:
        max_chars = max_length or self.max_summary_chars
        return _truncate(" ".join(texts), max_chars)

    def delete_memory(self, memory_id: str) -> bool:
        before = len(self._storage)
        self._storage = [memo for memo in self._storage if memo["id"] != memory_id]
        return len(self._storage) < before


@dataclass
class SQLiteMem0Client:
    db_path: str | Path
    max_summary_chars: int = 480
    _conn: sqlite3.Connection = field(init=False, repr=False)
    _lock: threading.Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.db_path = Path(self.db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    metadata TEXT,
                    score REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)")

    def add_memory(self, user_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        memory_id = str(uuid.uuid4())
        payload = {
            "id": memory_id,
            "user_id": user_id,
            "text": text,
            "metadata": metadata or {},
            "score": 1.0,
        }
        metadata_json = json.dumps(payload["metadata"])
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO memories (id, user_id, text, metadata, score) VALUES (?, ?, ?, ?, ?)",
                (memory_id, user_id, text, metadata_json, payload["score"]),
            )
        return payload

    def query_memories(self, user_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        query_pattern = f"%{query.lower()}%"
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, user_id, text, metadata, score
                FROM memories
                WHERE user_id = ?
                  AND LOWER(text) LIKE ?
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (user_id, query_pattern, limit),
            ).fetchall()
        return [self._row_to_payload(row) for row in rows]

    def summarize(self, texts: List[str], max_length: Optional[int] = None) -> str:
        max_chars = max_length or self.max_summary_chars
        return _truncate(" ".join(texts), max_chars)

    def delete_memory(self, memory_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return cur.rowcount > 0

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            conn = getattr(self, "_conn", None)
            if conn:
                conn.close()
                self._conn = None

    def _row_to_payload(self, row: sqlite3.Row) -> Dict[str, Any]:
        metadata_str = row["metadata"]
        metadata: Dict[str, Any]
        if metadata_str:
            try:
                metadata = json.loads(metadata_str)
            except json.JSONDecodeError:
                metadata = {"raw": metadata_str}
        else:
            metadata = {}
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "text": row["text"],
            "metadata": metadata,
            "score": row["score"],
        }


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)] + "..."


def _maybe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Mem0RemoteClient:
    """Wrapper around the optional mem0 SDK targeting a self-hosted endpoint."""

    backend_url: str
    api_key: str | None = None
    summary_max_length: int = 480
    default_query_limit: int = 5
    _client: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = self._build_sdk_client()

    def _build_sdk_client(self) -> Any:
        module = import_module("mem0")
        client_cls = getattr(module, "Mem0", None) or getattr(module, "Mem0Client", None)
        if not client_cls:
            raise ModuleNotFoundError("Mem0 SDK does not expose Mem0/Mem0Client")
        kwargs = {"api_key": self.api_key} if self.api_key else {}
        # Many SDKs expose a base_url argument for self-hosted deployments.
        kwargs["base_url"] = self.backend_url
        return client_cls(**kwargs)

    def add_memory(self, user_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._client.add_memory(user_id=user_id, text=text, metadata=metadata)

    def query_memories(self, user_id: str, query: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        return self._client.query_memories(user_id=user_id, query=query, limit=limit or self.default_query_limit)

    def delete_memory(self, memory_id: str) -> bool | Dict[str, Any]:
        return self._client.delete_memory(memory_id=memory_id)

    def summarize(self, texts: List[str], max_length: Optional[int] = None) -> str:
        if hasattr(self._client, "summarize"):
            return self._client.summarize(texts=texts, max_length=max_length or self.summary_max_length)
        return _truncate(" ".join(texts), max_length or self.summary_max_length)


__all__ = ["Mem0Adapter", "InMemoryMem0Client", "SQLiteMem0Client", "Mem0RemoteClient"]
