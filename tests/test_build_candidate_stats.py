from __future__ import annotations

import math

from memory_governor.mem_policy import build_candidate_stats


NOW = 1_700_000_000.0


def test_empty_inputs() -> None:
    stats = build_candidate_stats(None, None, now_ts=NOW)
    assert stats.recall_count == 0
    assert stats.avg_relevance == 0.0
    assert stats.distinct_queries == 0
    assert stats.distinct_days == 0
    assert stats.age_days == 0.0
    assert stats.tag_count == 0
    assert stats.scope_depth == 1


def test_pulls_recall_aggregates() -> None:
    row = {
        "recall_count": 5,
        "avg_relevance": 0.42,
        "distinct_queries": 3,
        "distinct_days": 4,
    }
    stats = build_candidate_stats(row, {"metadata": {}}, now_ts=NOW)
    assert stats.recall_count == 5
    assert stats.avg_relevance == 0.42
    assert stats.distinct_queries == 3
    assert stats.distinct_days == 4


def test_age_days_from_timestamp() -> None:
    mem = {"metadata": {"timestamp": NOW - 86400 * 7}}
    stats = build_candidate_stats(None, mem, now_ts=NOW)
    assert math.isclose(stats.age_days, 7.0, rel_tol=1e-6)


def test_age_days_accepts_ts_field() -> None:
    mem = {"metadata": {"ts": NOW - 86400 * 2}}
    stats = build_candidate_stats(None, mem, now_ts=NOW)
    assert math.isclose(stats.age_days, 2.0, rel_tol=1e-6)


def test_future_timestamp_clamped_to_zero() -> None:
    mem = {"metadata": {"timestamp": NOW + 86400}}
    stats = build_candidate_stats(None, mem, now_ts=NOW)
    assert stats.age_days == 0.0


def test_tags_counted() -> None:
    mem = {"metadata": {"tags": ["a", "b", "c"]}}
    stats = build_candidate_stats(None, mem, now_ts=NOW)
    assert stats.tag_count == 3


def test_keywords_fallback() -> None:
    mem = {"metadata": {"keywords": ["x", "y"]}}
    stats = build_candidate_stats(None, mem, now_ts=NOW)
    assert stats.tag_count == 2


def test_scope_depth_from_parent_chain() -> None:
    mem = {
        "metadata": {
            "scope": {
                "kind": "project",
                "id": "sb",
                "parent": {"kind": "user", "id": "sam", "parent": {"kind": "global", "id": "root"}},
            }
        }
    }
    stats = build_candidate_stats(None, mem, now_ts=NOW)
    assert stats.scope_depth == 3


def test_scope_depth_from_scope_path_string() -> None:
    mem = {"metadata": {"scope_path": "project:sb/user:sam"}}
    stats = build_candidate_stats(None, mem, now_ts=NOW)
    assert stats.scope_depth == 2


def test_scope_depth_defaults_to_one() -> None:
    mem = {"metadata": {"scope": {"kind": "user", "id": "sam"}}}
    stats = build_candidate_stats(None, mem, now_ts=NOW)
    assert stats.scope_depth == 1
