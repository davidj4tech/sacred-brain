from __future__ import annotations

import os
import re
from typing import Any

import math

from memory_governor.schemas import (
    CandidateStats,
    ObserveRequest,
    ScoreResult,
    ScoreSignals,
    ScoreThresholds,
)


def _keyword_score(text: str) -> float:
    text_l = text.lower()
    keywords = [
        "remember",
        "note",
        "important",
        "prefer",
        "always",
        "never",
        "please",
        "do not",
        "don't",
        "todo",
        "task",
        "tomorrow",
        "next week",
    ]
    hits = sum(1 for kw in keywords if kw in text_l)
    return min(1.0, 0.15 * hits)


def extract_tier_and_text(text: str, default_tier: str) -> tuple[str, str]:
    """Return (clean_text, tier).

    Tier rules:
    - If text starts with 'raw:' or 'private:' -> tier=raw
    - If text starts with 'safe:' -> tier=safe
    - Otherwise -> default_tier

    Prefix is stripped from stored text.
    """

    t = text.strip()
    low = t.lower()

    for prefix, tier in (
        ("raw:", "raw"),
        ("private:", "raw"),
        ("safe:", "safe"),
    ):
        if low.startswith(prefix):
            return t[len(prefix) :].lstrip(), tier

    return t, default_tier


def default_tier_for_event(event: ObserveRequest) -> str:
    """Compute default tier for an event based on scope (e.g., raw-by-default rooms)."""

    # Raw-by-default room allowlist
    raw_rooms = {
        r.strip()
        for r in (os.environ.get("MG_RAW_ROOM_IDS", "") or "").split(",")
        if r.strip()
    }

    try:
        if event.scope.kind == "room" and event.scope.id in raw_rooms:
            return "raw"
    except Exception:
        pass

    return "safe"


LOW_SALIENCE_SOURCES: dict[str, float] = {
    # PreCompact / session-tail dumps are long and keyword-dense by nature.
    # Cap so they flood working memory as context, not as candidates.
    "claude-code:precompact": 0.35,
    "opencode:precompact": 0.35,
    "codex:precompact": 0.35,
    "pi:precompact": 0.35,
}


def classify_observation(event: ObserveRequest) -> tuple[float, str]:
    """Return salience and decision kind."""

    text = event.text.strip()
    base = 0.1 + min(0.5, len(text) / 4000.0)
    base += _keyword_score(text)

    # Boost for explicit markers or commands
    if text.lower().startswith(("!remember", "!recall")) or event.metadata.get("reason") == "explicit":
        base = max(base, 0.9)

    # Preferential/commitment phrases boost
    if re.search(r"\b(always|never|prefer|i will|i'll|please remember)\b", text, re.IGNORECASE):
        base = max(base, 0.6)

    salience = min(1.0, base)
    cap = LOW_SALIENCE_SOURCES.get(event.source)
    if cap is not None:
        salience = min(salience, cap)
    if salience < 0.2:
        kind = "ignore"
    elif salience < 0.4:
        kind = "working"
    else:
        kind = "candidate"
    return salience, kind


def canonicalize_memory(text: str) -> str:
    # Strip whitespace, collapse spaces, keep short factual statement.
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:500]


def consolidate_events(
    events: list[dict[str, Any]],
    mode: str = "all",
) -> dict[str, list[dict[str, Any]]]:
    """Produce simple extractions for episodic/semantic/procedural."""

    episodic: list[dict[str, Any]] = []
    semantic: list[dict[str, Any]] = []
    procedural: list[dict[str, Any]] = []

    for evt in events:
        text = evt.get("text", "")
        meta = evt.get("metadata") or {}
        tier = meta.get("tier") or "safe"

        provenance = {
            "source": evt.get("source"),
            "event_id": evt.get("event_id"),
            "scope_id": evt.get("scope_id"),
            "scope_kind": evt.get("scope_kind"),
            "timestamp": evt.get("timestamp"),
            "tier": tier,
        }
        lower = text.lower()

        if mode in ("all", "episodic"):
            episodic.append(
                {
                    "text": text,
                    "kind": "episodic",
                    "confidence": 0.5,
                    "tier": tier,
                    "provenance": provenance,
                }
            )
        if mode in ("all", "semantic"):
            if any(tok in lower for tok in ["prefer", "always", "never", "like", "please remember", "compose", "plugin"]):
                semantic.append(
                    {
                        "text": canonicalize_memory(text),
                        "kind": "semantic",
                        "confidence": 0.7 if any(tok in lower for tok in ["prefer", "always", "never"]) else 0.6,
                        "tier": tier,
                        "provenance": provenance,
                    }
                )
        if mode in ("all", "procedural"):
            if any(lower.startswith(tok) for tok in ("run", "use", "start", "stop", "runbook", "task", "todo")) or "runbook" in lower or "restart" in lower:
                procedural.append(
                    {
                        "text": canonicalize_memory(text),
                        "kind": "procedural",
                        "confidence": 0.65 if "runbook" in lower else 0.55,
                        "tier": tier,
                        "provenance": provenance,
                    }
                )

    return {
        "episodic": episodic,
        "semantic": semantic,
        "procedural": procedural,
    }


SCORE_WEIGHTS = ScoreSignals(
    frequency=0.24,
    relevance=0.30,
    query_diversity=0.15,
    recency=0.15,
    consolidation=0.10,
    conceptual_richness=0.06,
)

RECENCY_HALFLIFE_DAYS = 14.0
FREQUENCY_SATURATION = 10  # recall_count at which frequency ≈ 1.0
DIVERSITY_SATURATION = 5
CONSOLIDATION_SATURATION = 7
RICHNESS_SATURATION = 6


def _log_saturate(value: float, saturation: int) -> float:
    if value <= 0:
        return 0.0
    return min(1.0, math.log2(1.0 + value) / math.log2(1.0 + saturation))


def _linear_saturate(value: float, saturation: int) -> float:
    if value <= 0:
        return 0.0
    return min(1.0, value / saturation)


def build_candidate_stats(
    recall_stats_row: dict | None,
    memory: dict | None,
    now_ts: float | None = None,
) -> CandidateStats:
    """Adapter: combine recall_stats row with a Hippocampus memory dict.

    Pure function — callers pass in the data. `recall_stats_row` is the dict
    returned by WorkingStore.get_recall_stats(). `memory` is a Hippocampus
    memory dict (id, text, metadata). Either may be None.
    """
    import time as _time

    row = recall_stats_row or {}
    mem = memory or {}
    meta = mem.get("metadata") or {}

    ts = meta.get("timestamp") or meta.get("ts") or meta.get("created_at")
    now = now_ts if now_ts is not None else _time.time()
    age_days = max(0.0, (float(now) - float(ts)) / 86400.0) if ts else 0.0

    tags = meta.get("tags") or meta.get("keywords") or []
    tag_count = len(tags) if isinstance(tags, list) else 0

    scope_depth = 1
    scope = meta.get("scope")
    if isinstance(scope, dict):
        cur = scope
        while isinstance(cur, dict) and cur.get("parent"):
            scope_depth += 1
            cur = cur.get("parent")
    else:
        sp = meta.get("scope_path")
        if isinstance(sp, str) and sp:
            scope_depth = max(1, sp.count("/") + 1)

    return CandidateStats(
        recall_count=int(row.get("recall_count") or 0),
        avg_relevance=float(row.get("avg_relevance") or 0.0),
        distinct_queries=int(row.get("distinct_queries") or 0),
        distinct_days=int(row.get("distinct_days") or 0),
        age_days=age_days,
        tag_count=tag_count,
        scope_depth=scope_depth,
    )


def score_candidate(
    stats: CandidateStats,
    thresholds: ScoreThresholds | None = None,
) -> ScoreResult:
    """Compute a weighted score for a promotion candidate.

    Pure function. Inputs are pre-aggregated (see CandidateStats). Callers are
    responsible for gathering recall_count, avg_relevance, etc. from store and
    stream_log.
    """

    thresholds = thresholds or ScoreThresholds()

    signals = ScoreSignals(
        frequency=_log_saturate(stats.recall_count, FREQUENCY_SATURATION),
        relevance=max(0.0, min(1.0, stats.avg_relevance)),
        query_diversity=_linear_saturate(stats.distinct_queries, DIVERSITY_SATURATION),
        recency=math.exp(-stats.age_days / RECENCY_HALFLIFE_DAYS) if stats.age_days >= 0 else 0.0,
        consolidation=_linear_saturate(stats.distinct_days, CONSOLIDATION_SATURATION),
        conceptual_richness=_linear_saturate(
            stats.tag_count + max(0, stats.scope_depth - 1), RICHNESS_SATURATION
        ),
    )

    weighted = ScoreSignals(
        frequency=signals.frequency * SCORE_WEIGHTS.frequency,
        relevance=signals.relevance * SCORE_WEIGHTS.relevance,
        query_diversity=signals.query_diversity * SCORE_WEIGHTS.query_diversity,
        recency=signals.recency * SCORE_WEIGHTS.recency,
        consolidation=signals.consolidation * SCORE_WEIGHTS.consolidation,
        conceptual_richness=signals.conceptual_richness * SCORE_WEIGHTS.conceptual_richness,
    )

    score = (
        weighted.frequency
        + weighted.relevance
        + weighted.query_diversity
        + weighted.recency
        + weighted.consolidation
        + weighted.conceptual_richness
    )

    reasons: list[str] = []
    if score < thresholds.min_score:
        reasons.append(f"score {score:.3f} below min_score {thresholds.min_score:.3f}")
    if stats.recall_count < thresholds.min_recall_count:
        reasons.append(
            f"recall_count {stats.recall_count} below min_recall_count {thresholds.min_recall_count}"
        )
    if stats.distinct_queries < thresholds.min_unique_queries:
        reasons.append(
            f"distinct_queries {stats.distinct_queries} below min_unique_queries {thresholds.min_unique_queries}"
        )

    passed = not reasons

    return ScoreResult(
        score=round(score, 4),
        signals=signals,
        weighted=weighted,
        passed=passed,
        threshold=thresholds.min_score,
        reasons=reasons,
    )
