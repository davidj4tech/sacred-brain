"""FastAPI app wiring for the hippocampus service."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from sacred_brain.astrology import BirthInfo, compute_bias_note
from sacred_brain.sam_pipeline import last_route_info

from .agno_integration import build_agno_agent
from .bot_router import BotRouter
from .config import AuthSettings, HippocampusSettings, load_settings
from .logging_config import configure_logging
from .mem0_adapter import Mem0Adapter
from .models import (
    ExperienceCreate,
    HealthResponse,
    MatrixRelayRequest,
    MatrixRelayResponse,
    MemoryCreateResponse,
    MemoryDeleteResponse,
    MemoryQueryResponse,
    SummarizeRequest,
    SummaryResponse,
)
from .reflection import reflection_pass
from .summarizers import SummarizerConfig
from .summarizers import summarize_texts as summarize_via_llm

LOGGER = logging.getLogger(__name__)



def _build_auth_dependency(auth_settings: AuthSettings):
    if not auth_settings.enabled or not auth_settings.api_keys:
        async def _noop() -> None:
            return None

        return _noop

    header_name = auth_settings.header_name or "X-API-Key"
    api_key_header = APIKeyHeader(name=header_name, auto_error=False)

    async def verify(api_key: str = Security(api_key_header)) -> None:
        if not api_key or api_key not in auth_settings.api_keys:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return verify

def create_app(settings: HippocampusSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings)

    admin_users_env = os.getenv("SAM_ADMIN_USERS", "")
    admin_users = {u.strip() for u in admin_users_env.split(",") if u.strip()}

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
    summarizer_config = SummarizerConfig(
        enabled=settings.summarizer.enabled,
        provider=settings.summarizer.provider,
        model=settings.summarizer.model,
        base_url=settings.summarizer.base_url,
        api_key=settings.summarizer.api_key,
        max_tokens=settings.summarizer.max_tokens,
    )
    agno_agent = build_agno_agent(adapter, summarizer_config, settings.agno)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.state.mem0_adapter = adapter
    application.state.agno_agent = agno_agent
    application.state.settings = settings
    application.state.sam_bias_note = compute_bias_note(
        enabled=settings.sam_astrology.enabled,
        birth=BirthInfo(
            timestamp=settings.sam_birth.timestamp,
            timezone=settings.sam_birth.timezone,
            location_name=settings.sam_birth.location_name,
            latitude=settings.sam_birth.latitude,
            longitude=settings.sam_birth.longitude,
        ),
        cache_path=Path(settings.sam_astrology.cache_path),
        engine=settings.sam_astrology.engine,
        signals_enabled=settings.sam_astrology.signals_enabled,
    )
    auth_dependency = _build_auth_dependency(settings.auth)

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.post("/memories", response_model=MemoryCreateResponse)
    async def create_memory(
        experience: ExperienceCreate,
        adapter: Mem0Adapter = Depends(get_adapter),
        _: None = Depends(auth_dependency),
    ) -> MemoryCreateResponse:
        record = adapter.add_experience(experience)
        return MemoryCreateResponse(memory=record)

    @application.delete("/memories/{memory_id}", response_model=MemoryDeleteResponse)
    async def delete_memory(
        memory_id: str,
        adapter: Mem0Adapter = Depends(get_adapter),
        _: None = Depends(auth_dependency),
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
        _: None = Depends(auth_dependency),
    ) -> MemoryQueryResponse:
        records = adapter.query_memories(user_id=user_id, query=query, limit=limit)
        return MemoryQueryResponse(memories=records)

    @application.post("/summaries", response_model=SummaryResponse)
    async def summarize(
        payload: SummarizeRequest,
        adapter: Mem0Adapter = Depends(get_adapter),
        _: None = Depends(auth_dependency),
    ) -> SummaryResponse:
        if summarizer_config.enabled:
            summary = summarize_via_llm(payload.texts, summarizer_config)
        else:
            summary = adapter.summarize_texts(payload.texts)
        if not summary:
            raise HTTPException(status_code=400, detail="No texts provided to summarize")
        return SummaryResponse(summary=summary)

    @application.post("/matrix/respond", response_model=MatrixRelayResponse)
    async def matrix_respond(
        payload: MatrixRelayRequest,
        request: Request,
        adapter: Mem0Adapter = Depends(get_adapter),
        _: None = Depends(auth_dependency),
    ) -> MatrixRelayResponse:
        agno_agent = getattr(request.app.state, "agno_agent", None)
        bias_note = getattr(request.app.state, "sam_bias_note", "")

        router = BotRouter(
            settings=settings,
            adapter=adapter,
            agno_agent=agno_agent,
            summarizer_config=summarizer_config,
            sam_bias_note=bias_note,
        )

        reply = router.generate_response(
            sender=payload.sender,
            body=payload.body,
            context=payload.context,
            room_id=payload.room_id,
        )

        if not reply:
            reply = "I'm having trouble thinking right now."

        reflection = reflection_pass(
            adapter=adapter,
            user_id=payload.sender,
            user_message=payload.body,
            assistant_reply=reply,
        )
        if reflection:
            reply = f"{reply}\n\n{reflection}"

        if payload.sender in admin_users:
            route_meta = last_route_info()
            if route_meta:
                reply = f"{reply}\n\n(model: {route_meta.get('alias','?')} reason: {route_meta.get('reason','?')})"

        return MatrixRelayResponse(reply=reply)

    @application.get("/doctor")
    async def doctor() -> dict:
        from sacred_brain.doctor import check_litellm

        litellm_status = check_litellm()
        return {"litellm": litellm_status}

    return application


def get_adapter(request: Request) -> Mem0Adapter:
    adapter = getattr(request.app.state, "mem0_adapter", None)
    if not adapter:
        raise RuntimeError("Mem0 adapter has not been initialised")
    return adapter


app = create_app()
