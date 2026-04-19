from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from memory_governor.store import WorkingStore


@pytest.fixture
def store(tmp_path: Path) -> WorkingStore:
    return WorkingStore(tmp_path / "state.db", ttl_hours=24)


def test_bump_recall_creates_row(store: WorkingStore) -> None:
    store.bump_recall("mem-1")
    stats = store.get_recall_stats("mem-1")
    assert stats is not None
    assert stats["memory_id"] == "mem-1"
    assert stats["recall_count"] == 1
    assert stats["last_recalled_at"] > 0


def test_bump_recall_increments(store: WorkingStore) -> None:
    store.bump_recall("mem-1")
    store.bump_recall("mem-1")
    store.bump_recall("mem-1")
    stats = store.get_recall_stats("mem-1")
    assert stats["recall_count"] == 3


def test_bump_recall_updates_timestamp(store: WorkingStore) -> None:
    store.bump_recall("mem-1", now_ts=1000)
    store.bump_recall("mem-1", now_ts=2000)
    stats = store.get_recall_stats("mem-1")
    assert stats["last_recalled_at"] == 2000


def test_bump_recall_empty_id_noop(store: WorkingStore) -> None:
    store.bump_recall("")
    assert store.get_recall_stats("") is None


def test_get_recall_counts_batch(store: WorkingStore) -> None:
    store.bump_recall("a")
    store.bump_recall("a")
    store.bump_recall("b")
    counts = store.get_recall_counts(["a", "b", "c"])
    assert counts == {"a": 2, "b": 1}


def test_get_recall_counts_empty(store: WorkingStore) -> None:
    assert store.get_recall_counts([]) == {}


def test_recently_recalled_ids(store: WorkingStore) -> None:
    now = int(time.time())
    store.bump_recall("recent", now_ts=now)
    store.bump_recall("old", now_ts=now - 86400 * 60)
    protected = store.recently_recalled_ids(now - 86400 * 30)
    assert "recent" in protected
    assert "old" not in protected


def test_get_recall_stats_missing(store: WorkingStore) -> None:
    assert store.get_recall_stats("nonexistent") is None
