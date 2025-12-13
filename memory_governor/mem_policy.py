from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

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


def classify_observation(event: ObserveRequest) -> Tuple[float, str]:
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
    events: List[Dict[str, Any]],
    mode: str = "all",
) -> Dict[str, List[Dict[str, Any]]]:
    """Produce simple extractions for episodic/semantic/procedural."""
    episodic: List[Dict[str, Any]] = []
    semantic: List[Dict[str, Any]] = []
    procedural: List[Dict[str, Any]] = []

    for evt in events:
        text = evt.get("text", "")
        provenance = {
            "source": evt.get("source"),
            "event_id": evt.get("event_id"),
            "scope_id": evt.get("scope_id"),
            "scope_kind": evt.get("scope_kind"),
            "timestamp": evt.get("timestamp"),
        }
        lower = text.lower()

        if mode in ("all", "episodic"):
            episodic.append(
                {
                    "text": text,
                    "kind": "episodic",
                    "confidence": 0.5,
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
                        "provenance": provenance,
                    }
                )

    return {
        "episodic": episodic,
        "semantic": semantic,
        "procedural": procedural,
    }
