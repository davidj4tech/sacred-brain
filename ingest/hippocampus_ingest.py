"""Generic ingestion service for logging events into Hippocampus."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

HIPPO_BASE_URL = os.environ.get("HIPPOCAMPUS_URL", "http://localhost:54321")
HIPPO_API_KEY = os.environ.get("HIPPOCAMPUS_API_KEY")

app = FastAPI(title="Hippocampus Ingestion", version="0.1.0")


class IngestEvent(BaseModel):
    source: str
    user_id: str
    text: str
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = {}


class ChatEvent(BaseModel):
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    user_id: Optional[str] = None
    sender: Optional[str] = None
    role: Optional[str] = None  # "user" | "assistant"
    content: str
    metadata: Dict[str, Any] = {}


def _headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if HIPPO_API_KEY:
        headers["X-API-Key"] = HIPPO_API_KEY
    return headers


async def _post_memory(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{HIPPO_BASE_URL}/memories", json=payload, headers=_headers())
            resp.raise_for_status()
            return {"logged": True, "status": resp.status_code}
    except Exception as exc:  # pragma: no cover - network path
        raise HTTPException(status_code=502, detail=f"Failed to log to Hippocampus: {exc}")


@app.post("/ingest")
async def ingest(event: IngestEvent) -> Dict[str, Any]:
    payload = {
        "user_id": event.user_id,
        "text": event.text,
        "metadata": {
            "source": event.source,
            "timestamp": event.timestamp,
            **(event.metadata or {}),
        },
    }
    return await _post_memory(payload)


@app.post("/webhook")
async def webhook(event: ChatEvent, x_open_webui_user: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not event.content:
        raise HTTPException(status_code=400, detail="Missing content")

    user_id = (
        event.user_id
        or x_open_webui_user
        or event.sender
        or "openwebui"
    )

    if (event.role or "").lower() == "assistant":
        return {"logged": False, "reason": "assistant_message"}

    payload = {
        "user_id": user_id,
        "text": event.content,
        "metadata": {
            "conversation_id": event.conversation_id,
            "message_id": event.message_id,
            "sender": event.sender,
            "role": event.role,
            **(event.metadata or {}),
        },
    }
    return await _post_memory(payload)


# Compatibility shim (old import path)
hippocampus_webhook_app = app

__all__ = ["app", "ingest", "webhook", "hippocampus_webhook_app"]
