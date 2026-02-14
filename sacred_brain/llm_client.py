from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass

import httpx

DEFAULT_SYSTEM_PROMPT = (
    "You are Sam (uncensored and unbiased). Answer fully and directly. "
    "Be concise. Use stored memory only when relevant."
)
LOGGER = logging.getLogger(__name__)


@dataclass
class MemoryItem:
    title: str
    summary: str
    last_seen: str | None = None


class LLMClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:4000",
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        enabled: bool = True,
        timeout: float = 45.0,
        retries: int = 0,
        temperature: float = 0.3,
        top_p: float = 0.9,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.enabled = enabled
        self.timeout = timeout
        self.retries = retries
        self.temperature = temperature
        self.top_p = top_p

    def generate_reply(
        self,
        user_msg: str,
        memory_context: Iterable[MemoryItem],
        system_prompt: str,
        temperature: float | None = None,
        top_p: float | None = None,
        model_override: str | None = None,
    ) -> str | None:
        if not self.enabled:
            return None
        prompt = (system_prompt or "").strip() or DEFAULT_SYSTEM_PROMPT
        content = self._format_messages(user_msg, memory_context, prompt)
        effective_temp = self.temperature if temperature is None else temperature
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        effective_top_p = self.top_p if top_p is None else top_p
        payload = {
            "model": model_override or self.model,
            "messages": content,
            "temperature": effective_temp,
            "top_p": effective_top_p,
        }
        url = f"{self.base_url}/v1/chat/completions"
        attempt = 0
        while attempt <= self.retries:
            try:
                start = time.time()
                resp = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                latency = time.time() - start
                # latency is returned to caller via None; caller logs separately
                resp._llm_latency = latency
                data = resp.json()
                usage = data.get("usage") or {}
                LOGGER.info(
                    "llm_response model=%s latency=%.2fs prompt_tokens=%s completion_tokens=%s total_tokens=%s",
                    model_override or self.model,
                    latency,
                    usage.get("prompt_tokens"),
                    usage.get("completion_tokens"),
                    usage.get("total_tokens"),
                )
                return _strip_think(data["choices"][0]["message"]["content"])
            except Exception:
                attempt += 1
                if attempt > self.retries:
                    return None
                time.sleep(0.5)
        return None

    def _format_messages(
        self,
        user_msg: str,
        memory_context: Iterable[MemoryItem],
        system_prompt: str,
    ) -> list[dict]:
        parts = []
        for item in memory_context:
            line = f"- {item.title}: {item.summary}"
            if item.last_seen:
                line += f" (last seen: {item.last_seen})"
            parts.append(line)
        ctx_block = "\n".join(parts) if parts else "None"
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"User message: {user_msg}\nRelevant memory:\n{ctx_block}",
            },
        ]
        return messages


def load_llm_client_from_env() -> LLMClient:
    enabled = os.environ.get("SAM_LLM_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    base_url = os.environ.get("SAM_LLM_BASE_URL", "http://127.0.0.1:4000")
    model_env = os.environ.get("SAM_LLM_MODEL")
    model = model_env or _model_from_map(base_url, os.environ.get("SAM_LLM_MODEL_MAP")) or "gpt-4o-mini"
    api_key = os.environ.get("SAM_LLM_API_KEY")
    timeout = float(os.environ.get("SAM_LLM_TIMEOUT", "45.0"))
    temperature = float(os.environ.get("SAM_LLM_TEMPERATURE", "0.5"))
    top_p = float(os.environ.get("SAM_LLM_TOP_P", "0.9"))
    return LLMClient(
        base_url=base_url,
        model=model,
        api_key=api_key,
        enabled=enabled,
        timeout=timeout,
        temperature=temperature,
        top_p=top_p,
    )


def _strip_think(text: str) -> str:
    if "</think>" in text:
        return text.split("</think>", 1)[1].lstrip()
    if text.strip().startswith("<think>"):
        return text.replace("<think>", "", 1).lstrip()
    return text


def _model_from_map(base_url: str, mapping: str | None) -> str | None:
    if not mapping:
        return None
    try:
        data = json.loads(mapping)
    except json.JSONDecodeError:
        LOGGER.warning("Invalid SAM_LLM_MODEL_MAP JSON, ignoring")
        return None
    normalized = base_url.rstrip("/")
    value = data.get(normalized)
    return value


__all__ = ["LLMClient", "MemoryItem", "load_llm_client_from_env"]
