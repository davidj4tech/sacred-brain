from __future__ import annotations

from memory_governor.dream import ScoredMemory, format_score_table, score_memories
from memory_governor.schemas import ScoreThresholds


NOW = 1_700_000_000.0


def _mem(mid: str, text: str, age_days: float = 0.0, tags: list[str] | None = None) -> dict:
    return {
        "id": mid,
        "text": text,
        "metadata": {
            "timestamp": NOW - age_days * 86400,
            "tags": tags or [],
        },
    }


def _stats(recall_count: int, avg_relevance: float, distinct_queries: int, distinct_days: int) -> dict:
    return {
        "recall_count": recall_count,
        "avg_relevance": avg_relevance,
        "distinct_queries": distinct_queries,
        "distinct_days": distinct_days,
    }


def test_score_memories_empty() -> None:
    assert score_memories([], lambda mid: None, now_ts=NOW) == []


def test_score_memories_sorted_desc() -> None:
    memories = [
        _mem("weak", "rarely used thing", age_days=30),
        _mem("strong", "frequently recalled", age_days=1, tags=["x", "y"]),
        _mem("medium", "middling", age_days=5, tags=["x"]),
    ]
    rows = {
        "weak": _stats(1, 0.2, 1, 1),
        "strong": _stats(10, 0.8, 5, 5),
        "medium": _stats(3, 0.5, 2, 2),
    }
    scored = score_memories(memories, rows.get, now_ts=NOW)
    ids = [s.memory_id for s in scored]
    assert ids == ["strong", "medium", "weak"]


def test_score_memories_gate_thresholds_respected() -> None:
    memories = [_mem("m1", "text", age_days=1, tags=["a"])]
    rows = {"m1": _stats(10, 0.9, 4, 4)}
    scored = score_memories(
        memories,
        rows.get,
        now_ts=NOW,
        thresholds=ScoreThresholds(min_score=0.99),
    )
    assert scored[0].result.passed is False
    assert any("min_score" in r for r in scored[0].result.reasons)


def test_score_memories_skips_ids_missing() -> None:
    memories = [
        {"text": "no id here", "metadata": {}},
        _mem("present", "has id", age_days=0),
    ]
    scored = score_memories(memories, lambda mid: None, now_ts=NOW)
    assert len(scored) == 1
    assert scored[0].memory_id == "present"


def test_score_memories_handles_missing_stats() -> None:
    memories = [_mem("m1", "text", age_days=0)]
    scored = score_memories(memories, lambda mid: None, now_ts=NOW)
    assert len(scored) == 1
    assert scored[0].stats.recall_count == 0


def test_format_score_table_empty() -> None:
    out = format_score_table([])
    assert "no memories" in out


def test_format_score_table_summary_counts() -> None:
    memories = [
        _mem("pass1", "a", age_days=1, tags=["x", "y", "z"]),
        _mem("pass2", "b", age_days=2, tags=["x", "y"]),
        _mem("fail1", "c", age_days=100),
    ]
    rows = {
        "pass1": _stats(10, 0.9, 5, 5),
        "pass2": _stats(8, 0.8, 4, 4),
        "fail1": _stats(0, 0.0, 0, 0),
    }
    scored = score_memories(memories, rows.get, now_ts=NOW)
    table = format_score_table(scored)
    assert "2 / 3 would promote" in table


def test_format_score_table_truncates_long_text() -> None:
    long = "x" * 200
    scored = [
        ScoredMemory(
            memory_id="m1",
            text=long,
            stats=score_memories([_mem("m1", long)], lambda _mid: None, now_ts=NOW)[0].stats,
            result=score_memories([_mem("m1", long)], lambda _mid: None, now_ts=NOW)[0].result,
            memory={},
        )
    ]
    table = format_score_table(scored, text_width=40)
    assert "…" in table
    for line in table.splitlines():
        assert "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" not in line
