from __future__ import annotations

import time
from pathlib import Path

import pytest

from memory_governor.store import WorkingStore


@pytest.fixture
def store(tmp_path: Path) -> WorkingStore:
    return WorkingStore(tmp_path / "state.db", ttl_hours=24)


def test_outcome_good_bumps_confidence(store: WorkingStore) -> None:
    r1 = store.apply_outcome("m1", "good", base_confidence=0.5, source="t")
    assert r1["confidence_before"] == pytest.approx(0.5)
    assert r1["confidence_after"] == pytest.approx(0.55)
    r2 = store.apply_outcome("m1", "good", base_confidence=0.5, source="t")
    assert r2["confidence_after"] == pytest.approx(0.60)


def test_outcome_bad_multiplies(store: WorkingStore) -> None:
    r = store.apply_outcome("m1", "bad", base_confidence=0.7, source="t")
    assert r["confidence_before"] == pytest.approx(0.7)
    assert r["confidence_after"] == pytest.approx(0.49, rel=1e-3)
    row = store.get_outcome("m1")
    assert row["disputed"] == 1


def test_outcome_bad_below_threshold(store: WorkingStore) -> None:
    # Repeated bad outcomes drive confidence toward zero
    base = 0.3
    for _ in range(5):
        r = store.apply_outcome("m1", "bad", base_confidence=base, source="t")
    assert r["confidence_after"] < 0.2


def test_outcome_stale_hides(store: WorkingStore) -> None:
    store.apply_outcome("m1", "stale", base_confidence=0.8, source="t")
    assert "m1" in store.stale_ids()
    row = store.get_outcome("m1")
    assert row["stale"] == 1
    assert row["last_outcome"] == "stale"
    # stale does not change confidence
    assert row["confidence_delta"] == 0.0


def test_outcome_history_bounded(store: WorkingStore) -> None:
    for i in range(15):
        store.apply_outcome("m1", "good", base_confidence=0.5, source=f"s{i}")
    row = store.get_outcome("m1")
    assert len(row["history"]) == 10
    # Last entry is the most recent
    assert row["history"][-1]["source"] == "s14"


def test_outcome_clamps_confidence(store: WorkingStore) -> None:
    # Many good posts should clamp at 0.99
    for _ in range(50):
        r = store.apply_outcome("m1", "good", base_confidence=0.5, source="t")
    assert r["confidence_after"] == pytest.approx(0.99)


def test_outcomes_bulk(store: WorkingStore) -> None:
    store.apply_outcome("m1", "good", base_confidence=0.5)
    store.apply_outcome("m2", "bad", base_confidence=0.7)
    store.apply_outcome("m3", "stale", base_confidence=0.9)
    bulk = store.get_outcomes_bulk(["m1", "m2", "m3", "missing"])
    assert set(bulk.keys()) == {"m1", "m2", "m3"}
    assert bulk["m1"]["last_outcome"] == "good"
    assert bulk["m2"]["disputed"] is True
    assert bulk["m3"]["stale"] is True


def test_recent_outcome_ids(store: WorkingStore) -> None:
    now = int(time.time())
    store.apply_outcome("recent", "good", base_confidence=0.5, now_ts=now)
    store.apply_outcome("old", "good", base_confidence=0.5, now_ts=now - 86400 * 30)
    protected = store.recent_outcome_ids(now - 86400 * 7)
    assert "recent" in protected
    assert "old" not in protected


def test_apply_outcome_rejects_unknown(store: WorkingStore) -> None:
    with pytest.raises(ValueError):
        store.apply_outcome("m1", "bogus", base_confidence=0.5)


def test_get_outcome_missing(store: WorkingStore) -> None:
    assert store.get_outcome("never-set") is None
