"""Maubot plugin that relays mentions to Sacred Brain."""
from __future__ import annotations

from typing import List

import httpx
from maubot import MessageEvent, Plugin
from maubot.handlers import event
from mautrix.types import EventType, MessageType
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        for key in (
            "mention",
            "allow_rooms",
            "persona",
            "context_limit",
            "sacred_brain_url",
            "api_key",
            "timeout_seconds",
        ):
            helper.copy(key)


class SacredBrainMentionBot(Plugin):
    async def start(self) -> None:
        # NOTE: maubot config proxy was unreliable in this environment, so we
        # keep a local config dict with the needed values.
        self._cfg = {
            "mention": "@sacredbrain",
            "allow_rooms": ["!xVOaRwGDMyUyyUKmcn:ryer.org"],
            "persona": None,
            "context_limit": 20,
            "sacred_brain_url": "http://127.0.0.1:8000/matrix/respond",
            "api_key": "hippo_local_a58b583f7a844f0eb3bc02e58d56f5bd",
            "timeout_seconds": 30,
        }

    @event.on(EventType.ROOM_MESSAGE)
    async def handle_message(self, evt: MessageEvent) -> None:
        if evt.sender == self.client.mxid:
            return
        if evt.content.msgtype != MessageType.TEXT:
            return

        body = evt.content.body or ""
        mention = (self._get_cfg("mention") or "").lower()
        if mention and mention not in body.lower():
            return

        allow_rooms = self._get_cfg("allow_rooms") or []
        if allow_rooms and evt.room_id not in allow_rooms:
            return

        context = await self._gather_context(evt)
        payload = {
            "room_id": evt.room_id,
            "sender": evt.sender,
            "body": body,
            "context": context,
        }
        persona = self.config.get("persona")
        if persona:
            payload["persona"] = persona

        reply = await self._call_sacred_brain(payload)
        if reply:
            await evt.reply(reply)

    async def _gather_context(self, evt: MessageEvent) -> List[str]:
        """Try to include recent text messages; fall back to just the triggering body."""
        limit = max(int(self._get_cfg("context_limit") or 0), 0)
        messages: List[str] = []
        if evt.content.body:
            messages.append(evt.content.body)
        if limit <= 1:
            return messages

        try:
            history = await evt.room.get_messages(limit=limit - 1, direction="b")
            for msg in history:
                if (
                    msg.type == EventType.ROOM_MESSAGE
                    and getattr(msg.content, "msgtype", None) == MessageType.TEXT
                ):
                    body = getattr(msg.content, "body", None)
                    if body:
                        messages.append(body)
        except Exception as exc:  # pragma: no cover - defensive for maubot/mautrix API changes
            self.log.warning("Failed to gather context: %s", exc)

        return messages[:limit] if limit else messages

    async def _call_sacred_brain(self, payload: dict) -> str | None:
        url = self._get_cfg("sacred_brain_url")
        headers = {"Content-Type": "application/json"}
        api_key = self._get_cfg("api_key")
        if api_key:
            headers["X-API-Key"] = api_key
        timeout = float(self._get_cfg("timeout_seconds") or 30)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data.get("reply")
        except Exception as exc:  # pragma: no cover - network and remote errors
            self.log.warning("Sacred Brain request failed: %s", exc)
            return None

    def _get_cfg(self, key: str):
        return self._cfg.get(key)
