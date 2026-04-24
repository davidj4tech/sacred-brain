from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Scope(BaseModel):
    kind: Literal["room", "user", "global", "project", "topic"]
    id: str
    parent: "Scope | None" = None


Scope.model_rebuild()


class ObserveRequest(BaseModel):
    source: str
    user_id: str
    text: str
    timestamp: int | None = None
    scope: Scope
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObserveDecision(BaseModel):
    salience: float
    kind: Literal["ignore", "working", "candidate"]


class ObserveResponse(BaseModel):
    status: str
    action: Literal["working", "stream"]
    decision: ObserveDecision


class RememberRequest(BaseModel):
    source: str
    user_id: str
    text: str
    kind: Literal["semantic", "episodic", "procedural", "working", "stream"] = "semantic"
    scope: Scope
    metadata: dict[str, Any] = Field(default_factory=dict)


class RememberResponse(BaseModel):
    status: str
    memory_id: str | None = None


class RecallFilters(BaseModel):
    kinds: list[str] | None = None
    tiers: list[str] | None = None  # e.g., ["safe"], ["safe","raw"], ["archive"]
    min_confidence: float | None = None
    since_days: int | None = None
    scope: Scope | None = None
    include_stale: bool = False


class RecallRequest(BaseModel):
    user_id: str
    query: str
    k: int = 5
    filters: RecallFilters = Field(default_factory=RecallFilters)


class RecallItem(BaseModel):
    text: str
    kind: str | None = None
    tier: str | None = None
    confidence: float | None = None
    timestamp: int | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    disputed: bool = False


class OutcomeRequest(BaseModel):
    memory_id: str
    user_id: str
    outcome: Literal["good", "bad", "stale"]
    note: str | None = None
    source: str | None = None


class OutcomeResponse(BaseModel):
    status: str
    memory_id: str
    confidence_after: float
    action: Literal["noop", "deleted"] = "noop"


class RecallResponse(BaseModel):
    results: list[RecallItem]


class ConsolidateRequest(BaseModel):
    scope: Scope
    mode: Literal["episodic", "semantic", "procedural", "all"] = "all"
    max_items: int = 20


class ConsolidateCounts(BaseModel):
    episodic: int = 0
    semantic: int = 0
    procedural: int = 0


class ConsolidateResponse(BaseModel):
    status: str
    written: ConsolidateCounts
    skipped: int = 0


class ScoreSignals(BaseModel):
    frequency: float = 0.0
    relevance: float = 0.0
    query_diversity: float = 0.0
    recency: float = 0.0
    consolidation: float = 0.0
    conceptual_richness: float = 0.0


class ScoreResult(BaseModel):
    score: float
    signals: ScoreSignals
    weighted: ScoreSignals
    passed: bool
    threshold: float
    reasons: list[str] = Field(default_factory=list)


class CandidateStats(BaseModel):
    """Inputs to score_candidate gathered from store + stream_log."""

    recall_count: int = 0
    avg_relevance: float = 0.0
    distinct_queries: int = 0
    distinct_days: int = 0
    age_days: float = 0.0
    tag_count: int = 0
    scope_depth: int = 1


class ScoreThresholds(BaseModel):
    min_score: float = 0.35
    min_recall_count: int = 2
    min_unique_queries: int = 2


class PromoteExplainRequest(BaseModel):
    memory_id: str
    user_id: str
    thresholds: ScoreThresholds | None = None


class PromoteExplainResponse(BaseModel):
    memory_id: str
    text: str
    stats: CandidateStats
    result: ScoreResult
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_dreamed_at: int | None = None
    dream_count: int = 0
