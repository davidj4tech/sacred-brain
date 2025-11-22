"""FastAPI app wiring for the hippocampus service."""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import HippocampusSettings, load_settings
from .logging_config import configure_logging
from .mem0_adapter import Mem0Adapter
from .models import (
    ExperienceCreate,
    HealthResponse,
    MemoryCreateResponse,
    MemoryDeleteResponse,
    MemoryQueryResponse,
    SummaryResponse,
    SummarizeRequest,
)


def create_app(settings: HippocampusSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings)

    application = FastAPI(title="Sacred Brain – Hippocampus", version="0.1.0")
    adapter = Mem0Adapter(
        enabled=settings.mem0.enabled,
        api_key=settings.mem0.api_key,
        backend=settings.mem0.backend,
        backend_url=settings.mem0.backend_url,
        summary_max_length=settings.mem0.summary_max_length,
        default_query_limit=settings.mem0.query_limit,
        persistence_path=settings.mem0.persistence_path,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.state.mem0_adapter = adapter
    application.state.settings = settings

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.post("/memories", response_model=MemoryCreateResponse)
    async def create_memory(
        experience: ExperienceCreate,
        adapter: Mem0Adapter = Depends(get_adapter),
    ) -> MemoryCreateResponse:
        record = adapter.add_experience(experience)
        return MemoryCreateResponse(memory=record)

    @application.delete("/memories/{memory_id}", response_model=MemoryDeleteResponse)
    async def delete_memory(
        memory_id: str,
        adapter: Mem0Adapter = Depends(get_adapter),
    ) -> MemoryDeleteResponse:
        deleted = adapter.delete_memory(memory_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Memory not found")
        return MemoryDeleteResponse(deleted=True)

    @application.get("/memories/{user_id}", response_model=MemoryQueryResponse)
    async def query_memories(
        user_id: str,
        query: str = Query(..., min_length=1),
        limit: int | None = Query(None, ge=1, le=100),
        adapter: Mem0Adapter = Depends(get_adapter),
    ) -> MemoryQueryResponse:
        records = adapter.query_memories(user_id=user_id, query=query, limit=limit)
        return MemoryQueryResponse(memories=records)

    @application.post("/summaries", response_model=SummaryResponse)
    async def summarize(
        payload: SummarizeRequest,
        adapter: Mem0Adapter = Depends(get_adapter),
    ) -> SummaryResponse:
        summary = adapter.summarize_texts(payload.texts)
        if not summary:
            raise HTTPException(status_code=400, detail="No texts provided to summarize")
        return SummaryResponse(summary=summary)

    return application


def get_adapter(request: Request) -> Mem0Adapter:
    adapter = getattr(request.app.state, "mem0_adapter", None)
    if not adapter:
        raise RuntimeError("Mem0 adapter has not been initialised")
    return adapter


app = create_app()
