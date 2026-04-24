from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_governor.rem import (
    REM_MODEL,
    RemInputs,
    build_rem_messages,
    format_dream_entry,
    gather_rem_inputs,
)
from memory_governor.store import WorkingStore


@pytest.fixture
def store(tmp_path: Path) -> WorkingStore:
    return WorkingStore(tmp_path / "state.db", ttl_hours=24)


def _write_stream(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_gather_filters_stream_by_cutoff(store: WorkingStore, tmp_path: Path) -> None:
    log = tmp_path / "stream.log"
    now = 100_000
    _write_stream(log, [
        {"timestamp": now - 3600, "kind": "recall", "memory_id": "recent"},
        {"timestamp": now - 86400 * 3, "kind": "recall", "memory_id": "old"},
    ])
    inputs = gather_rem_inputs(store, log, since_hours=24, top_k=5, now_ts=now)
    ids = [e.get("memory_id") for e in inputs.stream_events]
    assert "recent" in ids
    assert "old" not in ids
    assert inputs.now_ts == now


def test_gather_collects_promoted_today(store: WorkingStore, tmp_path: Path) -> None:
    now = 100_000
    store.record_dream_promotion("fresh", 0.7, {}, now_ts=now - 3600)
    store.record_dream_promotion("stale", 0.6, {}, now_ts=now - 86400 * 3)
    inputs = gather_rem_inputs(store, tmp_path / "missing.log", since_hours=24, now_ts=now)
    ids = [p["memory_id"] for p in inputs.promoted_today]
    assert "fresh" in ids
    assert "stale" not in ids


def test_gather_includes_top_recalled(store: WorkingStore, tmp_path: Path) -> None:
    store.bump_recall("a", now_ts=1000)
    store.bump_recall("a", now_ts=1001)
    store.bump_recall("a", now_ts=1002)
    store.bump_recall("b", now_ts=1000)
    inputs = gather_rem_inputs(store, tmp_path / "x.log", top_k=5, now_ts=2000)
    assert [r["memory_id"] for r in inputs.top_recalled][0] == "a"


def test_missing_stream_log_is_empty(store: WorkingStore, tmp_path: Path) -> None:
    inputs = gather_rem_inputs(store, tmp_path / "nope.log", now_ts=1000)
    assert inputs.stream_events == []


def test_is_empty_reports_nothing_to_reflect(store: WorkingStore, tmp_path: Path) -> None:
    inputs = gather_rem_inputs(store, tmp_path / "nope.log", now_ts=1000)
    assert inputs.is_empty is True


def test_build_messages_has_cache_markers() -> None:
    inputs = RemInputs(now_ts=1000, stream_events=[{"kind": "recall", "memory_id": "m"}])
    msgs = build_rem_messages(inputs)
    assert msgs[0]["role"] == "system"
    cache_types = [b.get("cache_control", {}).get("type") for b in msgs[0]["content"]]
    assert cache_types == ["ephemeral", "ephemeral"]
    assert msgs[1]["role"] == "user"
    # User block must not be cache-marked (per-night data).
    assert all("cache_control" not in b for b in msgs[1]["content"])


def test_build_messages_includes_data_block() -> None:
    inputs = RemInputs(
        now_ts=1000,
        stream_events=[{"kind": "recall", "memory_id": "m42", "query": "docker"}],
        promoted_today=[{"memory_id": "p1", "last_score": 0.55, "dream_count": 1}],
        top_recalled=[{"memory_id": "r1", "recall_count": 8}],
    )
    msgs = build_rem_messages(inputs)
    blob = msgs[1]["content"][0]["text"]
    assert "m42" in blob
    assert "p1" in blob
    assert "r1" in blob
    assert "0.550" in blob


def test_format_dream_entry_frontmatter() -> None:
    inputs = RemInputs(
        now_ts=1_700_000_000,
        stream_events=[{"timestamp": 1, "kind": "x"}, {"timestamp": 2, "kind": "y"}],
        promoted_today=[{"memory_id": "a"}, {"memory_id": "b"}],
    )
    out = format_dream_entry("hello world", inputs)
    assert out.startswith("---\n")
    assert "promoted_count: 2" in out
    assert "input_event_count: 2" in out
    assert f"reflection_model: {REM_MODEL}" in out
    assert out.rstrip().endswith("hello world")
