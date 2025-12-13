from __future__ import annotations

import httpx


def check_litellm(base_url: str = "http://127.0.0.1:4000") -> dict:
    url = f"{base_url.rstrip('/')}/v1/models"
    try:
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return {"litellm": "ok", "models": [m.get("id") for m in data.get("data", [])]}
    except Exception as exc:
        return {"litellm": f"error: {exc}"}


__all__ = ["check_litellm"]
