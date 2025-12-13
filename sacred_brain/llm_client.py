from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

import httpx


@dataclass
class MemoryItem:
    title: str
    summary: str
    last_seen: Optional[str] = None


class LLMClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:4000",
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        enabled: bool = True,
        timeout: float = 20.0,
        retries: int = 1,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.enabled = enabled
        self.timeout = timeout
        self.retries = retries

    def generate_reply(
        self,
        user_msg: str,
        memory_context: Iterable[MemoryItem],
        system_prompt: str,
        temperature: float = 0.3,
    ) -> Optional[str]:
        if not self.enabled:
            return None
        content = self._format_messages(user_msg, memory_context, system_prompt)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": content,
            "temperature": temperature,
        }
        url = f"{self.base_url}/v1/chat/completions"
        attempt = 0
        while attempt <= self.retries:
            try:
                resp = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
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
    ) -> List[dict]:
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
    model = os.environ.get("SAM_LLM_MODEL", "gpt-4o-mini")
    api_key = os.environ.get("SAM_LLM_API_KEY")
    return LLMClient(
        base_url=base_url,
        model=model,
        api_key=api_key,
        enabled=enabled,
    )


__all__ = ["LLMClient", "MemoryItem", "load_llm_client_from_env"]
