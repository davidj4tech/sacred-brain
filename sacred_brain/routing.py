from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Tuple

ROUTER_KEYWORDS = {
    "vision": ["image", "picture", "photo", "see attachment"],
    "creative": ["story", "poem", "haiku", "lyrics"],
    "code": ["```", "stack trace", "exception", "error", "traceback", "function", "class", "python", "javascript"],
}


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
    if any(k in msg for k in ROUTER_KEYWORDS["vision"]):
        return RouteDecision(alias="sam-vision", reason="vision_keyword")
    if any(k in msg for k in ROUTER_KEYWORDS["creative"]):
        return RouteDecision(alias="sam-creative", reason="creative_keyword")
    if any(k in msg for k in ROUTER_KEYWORDS["code"]):
        return RouteDecision(alias="sam-code", reason="code_keyword")
    return RouteDecision(alias="sam-fast", reason="default")


def escalate_route(previous_alias: str) -> str:
    if previous_alias in {"sam-fast", "sam-code"}:
        return "sam-deep"
    return previous_alias


__all__ = ["RouteDecision", "determine_route", "detect_error_loop", "escalate_route"]
