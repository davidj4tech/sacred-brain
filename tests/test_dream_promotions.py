from __future__ import annotations

from pathlib import Path

import pytest

from memory_governor.dream import ScoredMemory, record_passing_promotions, score_memories
from memory_governor.schemas import CandidateStats, ScoreResult, ScoreSignals, ScoreThresholds
from memory_governor.store import WorkingStore


@pytest.fixture
def store(tmp_path: Path) -> WorkingStore:
    return WorkingStore(tmp_path / "state.db", ttl_hours=24)


def test_record_and_get_single(store: WorkingStore) -> None:
    store.record_dream_promotion("m1", 0.72, {"frequency": 0.2}, now_ts=1000)
    row = store.get_dream_promotion("m1")
    assert row is not None
    assert row["memory_id"] == "m1"
    assert row["last_dreamed_at"] == 1000
    assert row["dream_count"] == 1
    assert row["last_score"] == pytest.approx(0.72)
    assert row["last_signals"] == {"frequency": 0.2}


def test_record_increments_count(store: WorkingStore) -> None:
    store.record_dream_promotion("m1", 0.5, {}, now_ts=1000)
    store.record_dream_promotion("m1", 0.6, {}, now_ts=2000)
    store.record_dream_promotion("m1", 0.7, {}, now_ts=3000)
    row = store.get_dream_promotion("m1")
    assert row["dream_count"] == 3
    assert row["last_dreamed_at"] == 3000
    assert row["last_score"] == pytest.approx(0.7)


def test_record_empty_id_noop(store: WorkingStore) -> None:
    store.record_dream_promotion("", 0.5)
    assert store.get_dream_promotion("") is None


def test_batch_lookup(store: WorkingStore) -> None:
    store.record_dream_promotion("a", 0.5, now_ts=1000)
    store.record_dream_promotion("b", 0.6, now_ts=1100)
    rows = store.get_dream_promotions(["a", "b", "c"])
    assert set(rows.keys()) == {"a", "b"}
    assert rows["a"]["last_score"] == pytest.approx(0.5)
    assert rows["b"]["last_dreamed_at"] == 1100


def test_batch_lookup_empty(store: WorkingStore) -> None:
    assert store.get_dream_promotions([]) == {}


def test_dreamed_within_filters_by_ts(store: WorkingStore) -> None:
    store.record_dream_promotion("recent", 0.5, now_ts=2000)
    store.record_dream_promotion("old", 0.5, now_ts=100)
    ids = store.dreamed_within(1000)
    assert "recent" in ids
    assert "old" not in ids


def test_get_missing_returns_none(store: WorkingStore) -> None:
    assert store.get_dream_promotion("nope") is None


def _scored(mid: str, passed: bool, score: float = 0.5) -> ScoredMemory:
    return ScoredMemory(
        memory_id=mid,
        text="t",
        stats=CandidateStats(),
        result=ScoreResult(
            score=score,
            signals=ScoreSignals(),
            weighted=ScoreSignals(frequency=0.1),
            passed=passed,
            threshold=0.35,
            reasons=[] if passed else ["below"],
        ),
        memory={},
    )


def test_record_passing_promotions_only_writes_passing() -> None:
    calls: list[tuple[str, float, dict]] = []

    def recorder(mid: str, score: float, signals: dict) -> None:
        calls.append((mid, score, signals))

    scored = [
        _scored("pass1", True, 0.7),
        _scored("fail1", False, 0.2),
        _scored("pass2", True, 0.5),
    ]
    count = record_passing_promotions(scored, recorder)
    assert count == 2
    assert [c[0] for c in calls] == ["pass1", "pass2"]
    assert calls[0][1] == pytest.approx(0.7)
    assert calls[0][2] == {
        "frequency": 0.1,
        "relevance": 0.0,
        "query_diversity": 0.0,
        "recency": 0.0,
        "consolidation": 0.0,
        "conceptual_richness": 0.0,
    }


def test_record_passing_promotions_empty() -> None:
    calls = []
    count = record_passing_promotions([], lambda *a, **k: calls.append(a))
    assert count == 0
    assert calls == []
