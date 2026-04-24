from __future__ import annotations

import math

from memory_governor.mem_policy import (
    FREQUENCY_SATURATION,
    SCORE_WEIGHTS,
    score_candidate,
)
from memory_governor.schemas import CandidateStats, ScoreThresholds


def _strong_stats(**overrides) -> CandidateStats:
    base = dict(
        recall_count=8,
        avg_relevance=0.8,
        distinct_queries=4,
        distinct_days=5,
        age_days=2.0,
        tag_count=3,
        scope_depth=2,
    )
    base.update(overrides)
    return CandidateStats(**base)


def test_empty_stats_fails_all_gates() -> None:
    # CandidateStats() leaves age_days=0 → recency=1.0, so score ≈ 0.15 from
    # the recency band alone. Still well below default min_score and both
    # count gates, so it should fail with three reasons.
    r = score_candidate(CandidateStats())
    assert r.passed is False
    assert len(r.reasons) == 3
    assert any("min_score" in reason for reason in r.reasons)
    assert any("min_recall_count" in reason for reason in r.reasons)
    assert any("min_unique_queries" in reason for reason in r.reasons)


def test_strong_candidate_passes() -> None:
    r = score_candidate(_strong_stats())
    assert r.passed is True
    assert r.reasons == []
    assert r.score > 0.5


def test_frequency_log_saturates() -> None:
    low = score_candidate(_strong_stats(recall_count=1)).signals.frequency
    mid = score_candidate(_strong_stats(recall_count=FREQUENCY_SATURATION)).signals.frequency
    huge = score_candidate(_strong_stats(recall_count=10_000)).signals.frequency
    assert low < mid
    assert mid == 1.0
    assert huge == 1.0


def test_recency_decays() -> None:
    fresh = score_candidate(_strong_stats(age_days=0.0)).signals.recency
    aged = score_candidate(_strong_stats(age_days=14.0)).signals.recency
    ancient = score_candidate(_strong_stats(age_days=100.0)).signals.recency
    assert fresh == 1.0
    assert math.isclose(aged, math.exp(-1.0), rel_tol=1e-6)
    assert ancient < aged < fresh


def test_weights_sum_to_one() -> None:
    total = (
        SCORE_WEIGHTS.frequency
        + SCORE_WEIGHTS.relevance
        + SCORE_WEIGHTS.query_diversity
        + SCORE_WEIGHTS.recency
        + SCORE_WEIGHTS.consolidation
        + SCORE_WEIGHTS.conceptual_richness
    )
    assert math.isclose(total, 1.0, abs_tol=1e-9)


def test_score_bounded_0_1() -> None:
    maxed = CandidateStats(
        recall_count=10_000,
        avg_relevance=1.0,
        distinct_queries=100,
        distinct_days=100,
        age_days=0.0,
        tag_count=100,
        scope_depth=10,
    )
    r = score_candidate(maxed)
    assert 0.0 <= r.score <= 1.0
    assert math.isclose(r.score, 1.0, abs_tol=1e-6)


def test_gate_min_recall_count() -> None:
    stats = _strong_stats(recall_count=1)
    r = score_candidate(stats, ScoreThresholds(min_recall_count=2))
    assert r.passed is False
    assert any("recall_count" in reason for reason in r.reasons)


def test_gate_min_unique_queries() -> None:
    stats = _strong_stats(distinct_queries=1)
    r = score_candidate(stats, ScoreThresholds(min_unique_queries=2))
    assert r.passed is False
    assert any("distinct_queries" in reason for reason in r.reasons)


def test_gate_min_score() -> None:
    weak = CandidateStats(recall_count=2, distinct_queries=2, age_days=999.0)
    r = score_candidate(weak, ScoreThresholds(min_score=0.9))
    assert r.passed is False
    assert any("min_score" in reason for reason in r.reasons)


def test_weighted_sum_matches_score() -> None:
    r = score_candidate(_strong_stats())
    total = (
        r.weighted.frequency
        + r.weighted.relevance
        + r.weighted.query_diversity
        + r.weighted.recency
        + r.weighted.consolidation
        + r.weighted.conceptual_richness
    )
    assert math.isclose(total, r.score, abs_tol=1e-3)


def test_signals_are_in_unit_interval() -> None:
    r = score_candidate(_strong_stats(avg_relevance=2.0, age_days=-5.0))
    for name in (
        "frequency",
        "relevance",
        "query_diversity",
        "recency",
        "consolidation",
        "conceptual_richness",
    ):
        v = getattr(r.signals, name)
        assert 0.0 <= v <= 1.0, f"{name}={v} out of [0,1]"
