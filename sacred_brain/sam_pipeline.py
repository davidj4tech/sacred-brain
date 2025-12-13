from __future__ import annotations

import os
from typing import Iterable, List

from sacred_brain.llm_client import LLMClient, MemoryItem, load_llm_client_from_env


def _build_memory_items(memories: Iterable[dict], max_items: int) -> List[MemoryItem]:
    items: List[MemoryItem] = []
    for mem in memories:
        text = mem.get("text") or mem.get("memory") or ""
        meta = mem.get("metadata") or {}
        kind = (meta.get("kind") or "").lower()
        if kind not in {"thread", "preference"} and not meta.get("sticky"):
            continue
        # simple summary/tagline
        summary = text
        if len(summary.split()) > 30:
            summary = " ".join(summary.split()[:30]) + "…"
        items.append(MemoryItem(title=meta.get("title") or kind or "memory", summary=summary, last_seen=None))
        if len(items) >= max_items:
            break
    return items


def sam_generate_reply(user_msg: str, memories: Iterable[dict], system_prompt: str) -> str:
    llm_client = load_llm_client_from_env()
    max_context = int(os.environ.get("SAM_MEMORY_CONTEXT_MAX", "3"))
    if not llm_client.enabled:
        return "LLM is not attached yet. I can show stored memories and threads."
    mem_items = _build_memory_items(memories, max_context)
    reply = llm_client.generate_reply(
        user_msg=user_msg,
        memory_context=mem_items,
        system_prompt=system_prompt,
    )
    if not reply:
        return "LLM is not attached yet. I can show stored memories and threads."
    return reply


__all__ = ["sam_generate_reply"]
