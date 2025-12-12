from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Scope(BaseModel):
    kind: Literal["room", "user", "global"]
    id: str


class ObserveRequest(BaseModel):
    source: str
    user_id: str
    text: str
    timestamp: Optional[int] = None
    scope: Scope
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RememberResponse(BaseModel):
    status: str
    memory_id: Optional[str] = None


class RecallFilters(BaseModel):
    kinds: Optional[List[str]] = None
    min_confidence: Optional[float] = None
    since_days: Optional[int] = None
    scope: Optional[Scope] = None


class RecallRequest(BaseModel):
    user_id: str
    query: str
    k: int = 5
    filters: RecallFilters = Field(default_factory=RecallFilters)


class RecallItem(BaseModel):
    text: str
    kind: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: Optional[int] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)


class RecallResponse(BaseModel):
    results: List[RecallItem]


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
