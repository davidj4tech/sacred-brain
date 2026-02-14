from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterable

from sacred_brain.llm_client import MemoryItem, load_llm_client_from_env
from sacred_brain.routing import determine_route, escalate_route

LOGGER = logging.getLogger(__name__)
_LAST_ROUTE: dict[str, str] = {}
REMOTE_ALIASES = {"sam-fast-remote"}


def _build_memory_items(memories: Iterable[dict], max_items: int) -> list[MemoryItem]:
    items: list[MemoryItem] = []
    for mem in memories:
        if isinstance(mem, dict):
            text = mem.get("text") or mem.get("memory") or ""
            meta = mem.get("metadata") or {}
        else:
            text = getattr(mem, "text", "") or getattr(mem, "memory", "") or ""
            meta = getattr(mem, "metadata", {}) or {}
        kind = (meta.get("kind") or "").lower()
        if kind not in {"thread", "preference"} and not meta.get("sticky"):
            continue
        # simple summary/tagline
        summary = text
        if len(summary.split()) > 30:
            summary = " ".join(summary.split()[:30]) + "…"
        # never include raw blobs beyond short summary
        items.append(MemoryItem(title=meta.get("title") or kind or "memory", summary=summary, last_seen=None))
        if len(items) >= max_items:
            break
    return items


def sam_generate_reply(
    user_msg: str,
    memories: Iterable[dict],
    system_prompt: str,
    memory_context_max: int | None = None,
    bias_note: str | None = None,
) -> str:
    llm_client = load_llm_client_from_env()
    max_context = memory_context_max or int(os.environ.get("SAM_MEMORY_CONTEXT_MAX", "3"))
    if not llm_client.enabled:
        return "LLM is not attached yet. I can show stored memories and threads."
    mem_items = _build_memory_items(memories, max_context)
    prompt = system_prompt
    if bias_note:
        prompt = f"{system_prompt.strip()}\n\nBias (internal): {bias_note.strip()}"

    decision = determine_route(user_msg)
    alias = decision.alias
    LOGGER.info("sam_route: alias=%s reason=%s", alias, decision.reason)

    start = time.time()
    reply = llm_client.generate_reply(
        user_msg=user_msg,
        memory_context=mem_items,
        system_prompt=prompt,
        model_override=alias,
    )
    latency = time.time() - start
    LOGGER.info("sam_route: alias=%s reason=%s latency=%.2fs", alias, decision.reason, latency)
    _LAST_ROUTE["alias"] = alias
    _LAST_ROUTE["reason"] = decision.reason
    _LAST_ROUTE["latency"] = f"{latency:.2f}s"

    if not reply and alias in {"sam-fast", "sam-code"}:
        escalated = escalate_route(alias)
        start = time.time()
        LOGGER.info("sam_route: escalation alias=%s from=%s", escalated, alias)
        reply = llm_client.generate_reply(
            user_msg=user_msg,
            memory_context=mem_items,
            system_prompt=prompt,
            model_override=escalated,
        )
        LOGGER.info("sam_route: alias=%s reason=escalation latency=%.2fs", escalated, time.time() - start)
        _LAST_ROUTE["alias"] = escalated
        _LAST_ROUTE["reason"] = "escalation"
    # If a remote alias failed, fall back to sam-deep before giving up.
    # (sam-fast may not be configured in all LiteLLM setups.)
    if not reply and alias in REMOTE_ALIASES:
        LOGGER.info("sam_route: remote alias failed, falling back to sam-deep")
        reply = llm_client.generate_reply(
            user_msg=user_msg,
            memory_context=mem_items,
            system_prompt=prompt,
            model_override="sam-deep",
        )
        if reply:
            _LAST_ROUTE["alias"] = "sam-deep"
            _LAST_ROUTE["reason"] = "fallback_remote_failed"
    if not reply:
        return "LLM is not attached yet. I can show stored memories and threads."
    return reply


def last_route_info() -> dict[str, str]:
    return dict(_LAST_ROUTE)


__all__ = ["sam_generate_reply"]
