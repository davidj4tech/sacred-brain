"""Summarization helpers backed by Litellm/Ollama."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

try:  # pragma: no cover - optional dependency
    import litellm
except ImportError:  # pragma: no cover
    litellm = None  # type: ignore

LOGGER = logging.getLogger(__name__)


@dataclass
class SummarizerConfig:
    enabled: bool
    provider: str
    model: str
    base_url: str | None
    api_key: str | None
    max_tokens: int = 512


def summarize_texts(texts: Iterable[str], config: SummarizerConfig) -> str:
    """Summarize texts via litellm when enabled, else fall back to truncation."""
    cleaned = [text.strip() for text in texts if text and text.strip()]
    if not cleaned:
        return ""

    if not config.enabled:
        return _fallback_summary(cleaned)

    if litellm is None:
        LOGGER.warning("litellm not installed; falling back to naive summary")
        return _fallback_summary(cleaned)

    prompt = "Summarize the following notes into a concise paragraph:\n" + "\n".join(f"- {line}" for line in cleaned)
    kwargs = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": config.max_tokens,
    }
    if config.base_url:
        kwargs["base_url"] = config.base_url
    if config.api_key:
        kwargs["api_key"] = config.api_key

    try:
        response = litellm.completion(**kwargs)
        choice = response.choices[0]
        content = choice.get("message", {}).get("content") if isinstance(choice, dict) else choice.message["content"]
        if not content:
            raise ValueError("LLM returned empty content")
        return str(content).strip()
    except Exception as exc:  # pragma: no cover - external dependency
        LOGGER.warning("Summarizer failed via litellm; falling back: %s", exc, exc_info=True)
        return _fallback_summary(cleaned)


def _fallback_summary(texts: list[str]) -> str:
    summary = " ".join(texts)
    return summary if len(summary) <= 480 else summary[:477] + "..."
