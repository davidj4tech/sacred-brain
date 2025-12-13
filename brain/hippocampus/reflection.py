from __future__ import annotations

import re
from typing import Dict, List, Optional


SOFT_PREFIXES = [
    "Sam:",
]

SOFT_PHRASES = [
    "This connects to",
    "This feels like the same thread as",
    "Worth noticing",
    "This lines up with",
]

LOGISTICS_KEYWORDS = {"token", "secret", "password", "api key", "ip", "port", "localhost", "127.", "host.docker.internal"}


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"\w+", text.lower()) if t]


def _overlap_score(a: str, b: str) -> float:
    ta = set(_tokenize(a))
    tb = set(_tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(tb)


def reflection_pass(
    adapter,
    user_id: str,
    user_message: str,
    assistant_reply: str,
    max_candidates: int = 3,
) -> str:
    """
    Produce a short reflection sentence based on relevant memories.
    - Queries up to max_candidates memories.
    - Only kinds thread/preference (or sticky) are eligible.
    - Filters out sensitive/logistics unless present in the current message.
    """
    combined = f"{user_message} {assistant_reply}".strip()
    memories = adapter.query_memories(user_id=user_id, query=combined, limit=max_candidates) or []

    eligible: List[Dict] = []
    convo_lower = combined.lower()
    for mem in memories:
        meta = mem.get("metadata") or {}
        kind = (meta.get("kind") or "").lower()
        sticky = bool(meta.get("sticky", False))
        if kind not in {"thread", "preference"} and not sticky:
            continue
        text = mem.get("text") or mem.get("memory") or ""
        if not text:
            continue
        if meta.get("sensitive") and not _overlap_score(text, combined):
            continue
        if any(k in text.lower() for k in LOGISTICS_KEYWORDS) and not any(k in convo_lower for k in LOGISTICS_KEYWORDS):
            continue
        eligible.append(mem)

    if not eligible:
        return ""

    scored = []
    for mem in eligible:
        text = mem.get("text") or mem.get("memory") or ""
        score = _overlap_score(text, combined)
        scored.append((score, mem))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_mem = scored[0]
    if best_score < 0.05:
        return ""

    snippet = (best_mem.get("text") or best_mem.get("memory") or "").strip()
    words = snippet.split()
    if len(words) > 25:
        snippet = " ".join(words[:25]).rstrip(",.;") + "…"

    prefix = SOFT_PREFIXES[0]
    phrase = SOFT_PHRASES[0]
    return f"{prefix} {phrase} {snippet}"


__all__ = ["reflection_pass"]
