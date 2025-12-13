"""FastAPI app wiring for the hippocampus service."""
from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from .config import AuthSettings, SummarizerSettings, HippocampusSettings, load_settings
from .logging_config import configure_logging
from .agno_integration import build_agno_agent
from .mem0_adapter import Mem0Adapter
from .reflection import reflection_pass
from .summarizers import SummarizerConfig, summarize_texts as summarize_via_llm
from sacred_brain.sam_pipeline import sam_generate_reply
from sacred_brain.prompts import sam_system
from .models import (
    ExperienceCreate,
    HealthResponse,
    MatrixRelayRequest,
    MatrixRelayResponse,
    MemoryCreateResponse,
    MemoryDeleteResponse,
    MemoryQueryResponse,
    SummaryResponse,
    SummarizeRequest,
)

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
        texts = list(payload.context) + [f"{payload.sender}: {payload.body}"]

        if settings.sam.enabled:
            mems = adapter.query_memories(user_id=payload.sender, query=payload.body, limit=settings.sam.memory_candidates_max)
            reply = sam_generate_reply(payload.body, mems, sam_system.SYSTEM_PROMPT)
        elif settings.agno.enabled and agno_agent:
            prompt = _format_matrix_prompt(payload.sender, payload.body, payload.context)
            try:
                run = agno_agent.run(prompt, user_id=payload.sender, session_id=payload.room_id)
                content = getattr(run, "content", None)
                reply = content if isinstance(content, str) else getattr(run, "get_content_as_string", lambda: "")()
            except Exception as exc:  # pragma: no cover - defensive
                # Fall back to the summarizer if the agent fails.
                LOGGER.warning("Agno agent failed; falling back to summarizer: %s", exc, exc_info=True)
                reply = None
        else:
            reply = None

        if not reply:
            reply = (
                summarize_via_llm(texts, summarizer_config)
                if summarizer_config.enabled
                else adapter.summarize_texts(texts)
            )
        if not reply:
            reply = "I need more context before I can help."

        reflection = reflection_pass(
            adapter=adapter,
            user_id=payload.sender,
            user_message=payload.body,
            assistant_reply=reply,
        )
        if reflection:
            reply = f"{reply}\n\n{reflection}"

        return MatrixRelayResponse(reply=reply)

    return application


@app.get("/doctor")
async def doctor() -> dict:
    from sacred_brain.doctor import check_litellm

    litellm_status = check_litellm()
    return {
        "litellm": litellm_status,
    }


def get_adapter(request: Request) -> Mem0Adapter:
    adapter = getattr(request.app.state, "mem0_adapter", None)
    if not adapter:
        raise RuntimeError("Mem0 adapter has not been initialised")
    return adapter


def _format_matrix_prompt(sender: str, body: str, context: list[str]) -> str:
    context_lines = "\n".join(f"- {line}" for line in context) if context else "No prior context."
    return (
        "You are responding to a Matrix mention. "
        "Use the tools to fetch or store memories for this sender as needed. "
        f"Sender: {sender}\n"
        f"Message: {body}\n"
        f"Context:\n{context_lines}"
    )


app = create_app()
