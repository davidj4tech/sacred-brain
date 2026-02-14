"""Optional Agno agent wrapper around the Mem0 adapter."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from .config import AgnoSettings
from .mem0_adapter import Mem0Adapter
from .models import ExperienceCreate, MemoryRecord
from .summarizers import SummarizerConfig, summarize_texts

LOGGER = logging.getLogger(__name__)


def build_agno_agent(
    adapter: Mem0Adapter,
    summarizer_config: SummarizerConfig,
    settings: AgnoSettings,
) -> Any | None:
    """Create an Agno Agent that exposes Mem0 operations as tools."""
    if not settings.enabled:
        return None

    try:
        from agno.agent import Agent
        from agno.tools import tool
    except ImportError:
        LOGGER.info("Agno not installed; skipping agent creation")
        return None

    model = _build_model(settings)
    if model is None:
        LOGGER.info("Agno model could not be initialised; skipping agent")
        return None

    system_instructions = settings.system_prompt or (
        "You are the Sacred Brain hippocampus agent. "
        "You store and retrieve concise memories for a given user_id, "
        "and you respond tersely with the most helpful snippet."
    )

    @tool(name="store_memory", description="Store a memory for a user with optional metadata.")
    def store_memory(user_id: str, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        experience = ExperienceCreate(user_id=user_id, text=text, metadata=metadata or {})
        record = adapter.add_experience(experience)
        return _record_to_dict(record)

    @tool(name="search_memories", description="Search existing memories for a user.")
    def search_memories(user_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        results = adapter.query_memories(user_id=user_id, query=query, limit=limit)
        return [_record_to_dict(item) for item in results]

    @tool(name="summarize_context", description="Summarize a list of context snippets.")
    def summarize_context(snippets: Iterable[str]) -> str:
        return summarize_texts(snippets, summarizer_config)

    tools = [store_memory, search_memories, summarize_context]

    return Agent(
        name="SacredBrainAgent",
        model=model,
        tools=tools,
        instructions=system_instructions,
        search_knowledge=False,
        add_history_to_context=False,
        add_dependencies_to_context=False,
    )


def _build_model(settings: AgnoSettings) -> Any | None:
    """Select an Agno model provider based on the configured model string."""
    provider, _, model_name = (settings.model or "").partition(":")
    provider = provider or "openai"
    model_name = model_name or "gpt-4o-mini"

    try:
        if provider == "openai":
            from agno.models.openai import OpenAIChat

            return OpenAIChat(id=model_name, api_key=settings.api_key, base_url=settings.base_url)
        if provider == "ollama":
            from agno.models.ollama import Ollama

            kwargs = {"id": model_name}
            if settings.base_url:
                kwargs["host"] = settings.base_url
            return Ollama(**kwargs)
        if provider == "litellm":
            from agno.models.litellm import LiteLLM

            kwargs = {"model": model_name}
            if settings.base_url:
                kwargs["base_url"] = settings.base_url
            if settings.api_key:
                kwargs["api_key"] = settings.api_key
            return LiteLLM(**kwargs)
    except ImportError as exc:
        LOGGER.warning("Agno provider %s missing dependency: %s", provider, exc)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Failed to initialise Agno model provider %s: %s", provider, exc, exc_info=True)
    return None


def _record_to_dict(record: MemoryRecord | dict[str, Any]) -> dict[str, Any]:
    if isinstance(record, MemoryRecord):
        return record.model_dump()
    if isinstance(record, dict):
        return record
    return {"id": str(record)}


__all__ = ["build_agno_agent"]
