from __future__ import annotations

import os
import re
from typing import Any

from memory_governor.schemas import ObserveRequest


def _keyword_score(text: str) -> float:
    text_l = text.lower()
    keywords = [
        "remember",
        "note",
        "important",
        "prefer",
        "always",
        "never",
        "please",
        "do not",
        "don't",
        "todo",
        "task",
        "tomorrow",
        "next week",
    ]
    hits = sum(1 for kw in keywords if kw in text_l)
    return min(1.0, 0.15 * hits)


def extract_tier_and_text(text: str, default_tier: str) -> tuple[str, str]:
    """Return (clean_text, tier).

    Tier rules:
    - If text starts with 'raw:' or 'private:' -> tier=raw
    - If text starts with 'safe:' -> tier=safe
    - Otherwise -> default_tier

    Prefix is stripped from stored text.
    """

    t = text.strip()
    low = t.lower()

    for prefix, tier in (
        ("raw:", "raw"),
        ("private:", "raw"),
        ("safe:", "safe"),
    ):
        if low.startswith(prefix):
            return t[len(prefix) :].lstrip(), tier

    return t, default_tier


def default_tier_for_event(event: ObserveRequest) -> str:
    """Compute default tier for an event based on scope (e.g., raw-by-default rooms)."""

    # Raw-by-default room allowlist
    raw_rooms = {
        r.strip()
        for r in (os.environ.get("MG_RAW_ROOM_IDS", "") or "").split(",")
        if r.strip()
    }

    try:
        if event.scope.kind == "room" and event.scope.id in raw_rooms:
            return "raw"
    except Exception:
        pass

    return "safe"


LOW_SALIENCE_SOURCES: dict[str, float] = {
    # PreCompact / session-tail dumps are long and keyword-dense by nature.
    # Cap so they flood working memory as context, not as candidates.
    "claude-code:precompact": 0.35,
    "opencode:precompact": 0.35,
    "codex:precompact": 0.35,
}


def classify_observation(event: ObserveRequest) -> tuple[float, str]:
    """Return salience and decision kind."""

    text = event.text.strip()
    base = 0.1 + min(0.5, len(text) / 4000.0)
    base += _keyword_score(text)

    # Boost for explicit markers or commands
    if text.lower().startswith(("!remember", "!recall")) or event.metadata.get("reason") == "explicit":
        base = max(base, 0.9)

    # Preferential/commitment phrases boost
    if re.search(r"\b(always|never|prefer|i will|i'll|please remember)\b", text, re.IGNORECASE):
        base = max(base, 0.6)

    salience = min(1.0, base)
    cap = LOW_SALIENCE_SOURCES.get(event.source)
    if cap is not None:
        salience = min(salience, cap)
    if salience < 0.2:
        kind = "ignore"
    elif salience < 0.4:
        kind = "working"
    else:
        kind = "candidate"
    return salience, kind


def canonicalize_memory(text: str) -> str:
    # Strip whitespace, collapse spaces, keep short factual statement.
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:500]


def consolidate_events(
    events: list[dict[str, Any]],
    mode: str = "all",
) -> dict[str, list[dict[str, Any]]]:
    """Produce simple extractions for episodic/semantic/procedural."""

    episodic: list[dict[str, Any]] = []
    semantic: list[dict[str, Any]] = []
    procedural: list[dict[str, Any]] = []

    for evt in events:
        text = evt.get("text", "")
        meta = evt.get("metadata") or {}
        tier = meta.get("tier") or "safe"

        provenance = {
            "source": evt.get("source"),
            "event_id": evt.get("event_id"),
            "scope_id": evt.get("scope_id"),
            "scope_kind": evt.get("scope_kind"),
            "timestamp": evt.get("timestamp"),
            "tier": tier,
        }
        lower = text.lower()

        if mode in ("all", "episodic"):
            episodic.append(
                {
                    "text": text,
                    "kind": "episodic",
                    "confidence": 0.5,
                    "tier": tier,
                    "provenance": provenance,
                }
            )
        if mode in ("all", "semantic"):
            if any(tok in lower for tok in ["prefer", "always", "never", "like", "please remember", "compose", "plugin"]):
                semantic.append(
                    {
                        "text": canonicalize_memory(text),
                        "kind": "semantic",
                        "confidence": 0.7 if any(tok in lower for tok in ["prefer", "always", "never"]) else 0.6,
                        "tier": tier,
                        "provenance": provenance,
                    }
                )
        if mode in ("all", "procedural"):
            if any(lower.startswith(tok) for tok in ("run", "use", "start", "stop", "runbook", "task", "todo")) or "runbook" in lower or "restart" in lower:
                procedural.append(
                    {
                        "text": canonicalize_memory(text),
                        "kind": "procedural",
                        "confidence": 0.65 if "runbook" in lower else 0.55,
                        "tier": tier,
                        "provenance": provenance,
                    }
                )

    return {
        "episodic": episodic,
        "semantic": semantic,
        "procedural": procedural,
    }
