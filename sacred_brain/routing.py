from __future__ import annotations

import os
from dataclasses import dataclass

ROUTER_KEYWORDS = {
    "vision": ["image", "picture", "photo", "see attachment"],
    "creative": ["story", "poem", "haiku", "lyrics"],
    "code": ["```", "stack trace", "exception", "error", "traceback", "function", "class", "python", "javascript"],
}

DEFAULT_ALIAS = os.getenv("SAM_DEFAULT_ALIAS", "sam-fast")
FALLBACK_ALIAS = "sam-fast"


@dataclass
class RouteDecision:
    alias: str
    reason: str


def detect_error_loop(user_msg: str) -> bool:
    msg = user_msg.lower()
    return any(kw in msg for kw in ["didn't work", "didnt work", "doesn't work", "does not work", "failed", "error again"])


def determine_route(user_msg: str) -> RouteDecision:
    msg = user_msg.lower()
    if detect_error_loop(msg):
        return RouteDecision(alias="sam-deep", reason="error_escalation")
    # If local-only mode is desired, force sam-local
    if msg.startswith("!local") or "local model" in msg:
        return RouteDecision(alias="sam-local", reason="forced_local")
    if any(k in msg for k in ROUTER_KEYWORDS["vision"]):
        return RouteDecision(alias="sam-vision", reason="vision_keyword")
    if any(k in msg for k in ROUTER_KEYWORDS["creative"]):
        return RouteDecision(alias="sam-creative", reason="creative_keyword")
    if any(k in msg for k in ROUTER_KEYWORDS["code"]):
        return RouteDecision(alias="sam-code", reason="code_keyword")
    return RouteDecision(alias=DEFAULT_ALIAS, reason="default")


def escalate_route(previous_alias: str) -> str:
    if previous_alias in {"sam-fast", "sam-code"}:
        return "sam-deep"
    return previous_alias


__all__ = ["RouteDecision", "determine_route", "detect_error_loop", "escalate_route"]
