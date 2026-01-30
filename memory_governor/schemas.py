from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Scope(BaseModel):
    kind: Literal["room", "user", "global"]
    id: str


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
