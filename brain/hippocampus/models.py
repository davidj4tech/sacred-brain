"""Pydantic models for the hippocampus API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExperienceCreate(BaseModel):
    user_id: str = Field(..., description="Who generated the experience")
    text: str = Field(..., min_length=1, description="Raw text to store")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryRecord(BaseModel):
    id: str
    user_id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    score: Optional[float] = None


class MemoryCreateResponse(BaseModel):
    memory: MemoryRecord


class MemoryQueryResponse(BaseModel):
    memories: List[MemoryRecord]


class MemoryDeleteResponse(BaseModel):
    deleted: bool


class SummarizeRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1)


class SummaryResponse(BaseModel):
    summary: str


class HealthResponse(BaseModel):
    status: str


class MatrixRelayRequest(BaseModel):
    room_id: str
    sender: str
    body: str
    context: List[str] = Field(default_factory=list)


class MatrixRelayResponse(BaseModel):
    reply: str
