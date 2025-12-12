"""Maubot plugin that forwards Matrix messages to the ingest service."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

import aiohttp
from maubot import MessageEvent, Plugin
from maubot.handlers import event
from mautrix.types import EventType, MessageType, RoomID


class Deduper:
    """Simple TTL + size-limited cache of event_ids to prevent duplicates."""

    def __init__(self, ttl_seconds: int, max_size: int) -> None:
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._cache: OrderedDict[str, float] = OrderedDict()
        self._lock = asyncio.Lock()

    async def seen(self, event_id: str) -> bool:
        now = time.time()
        async with self._lock:
            # drop expired
            expired = [k for k, ts in self._cache.items() if now - ts > self.ttl]
            for k in expired:
                self._cache.pop(k, None)
            if event_id in self._cache:
                return True
            self._cache[event_id] = now
            # prune size
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)
        return False


class IngestPlugin(Plugin):
    async def start(self) -> None:
        settings = _load_settings(self.config)
        self.settings = settings
        self.client_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2))
        self.deduper = Deduper(
            ttl_seconds=settings["cache_ttl_seconds"],
            max_size=settings["cache_max_size"],
        )
        await super().start()

    async def stop(self) -> None:
        await super().stop()
        await self.client_session.close()

    @classmethod
    def get_config_class(cls):
        # The plugin works without a config class; settings are loaded manually in start().
        return None

    @event.on(EventType.ROOM_MESSAGE)
    async def message_handler(self, evt: MessageEvent) -> None:
        if evt.sender == self.client.mxid:
            return
        if evt.content.msgtype != MessageType.TEXT:
            return
        if self.settings["rooms_allowlist"] and evt.room_id not in self.settings["rooms_allowlist"]:
            return
        if await self.deduper.seen(evt.event_id):
            return

        body = evt.content.body.strip()

        # Command: !remember <text>
        if body.startswith("!remember"):
            remember_text = body[len("!remember") :].strip()
            if remember_text:
                await self._handle_remember(evt, remember_text)
            else:
                await evt.reply("Usage: !remember <text>")
            return

        # Command: !recall <query>
        if body.startswith("!recall"):
            query_text = body[len("!recall") :].strip()
            if query_text:
                await self._handle_recall(evt, query_text)
            else:
                await evt.reply("Usage: !recall <query>")
            return

        payload = {
            "source": "matrix",
            "user_id": evt.sender,
            "text": evt.content.body,
            "metadata": _build_metadata(evt),
        }

        headers = {}
        if self.settings["api_key"]:
            headers["X-API-Key"] = self.settings["api_key"]

        try:
            async with self.client_session.post(
                self.settings["ingest_url"], json=payload, headers=headers
            ) as resp:
                if resp.status == 200 and self.settings["react_success"]:
                    await evt.react("✅")
                if resp.status >= 400:
                    self.log.warning("Ingest failed (%s): %s", resp.status, await resp.text())
        except asyncio.TimeoutError:
            self.log.warning("Ingest timed out for event %s", evt.event_id)
        except Exception as exc:  # pragma: no cover - defensive
            self.log.exception("Ingest error for event %s: %s", evt.event_id, exc)

    async def _handle_remember(self, evt: MessageEvent, text: str) -> None:
        payload = {
            "source": "matrix",
            "user_id": evt.sender,
            "text": text,
            "kind": "semantic",
            "scope": {"kind": "room", "id": str(evt.room_id)},
            "metadata": {"reason": "explicit", **_build_metadata(evt)},
        }
        try:
            async with self.client_session.post(
                f"{self.settings['governor_url'].rstrip('/')}/remember",
                json=payload,
            ) as resp:
                if resp.status == 200:
                    await evt.reply("Stored.")
                else:
                    self.log.warning("Remember failed (%s): %s", resp.status, await resp.text())
                    await evt.reply("Failed to store.")
        except asyncio.TimeoutError:
            await evt.reply("Governor timeout.")
        except Exception as exc:  # pragma: no cover - defensive
            self.log.exception("Governor remember error: %s", exc)
            await evt.reply("Error storing.")

    async def _handle_recall(self, evt: MessageEvent, query: str) -> None:
        payload = {
            "user_id": evt.sender,
            "query": query,
            "k": self.settings["recall_top_k"],
            "filters": {"kinds": ["semantic", "procedural"], "scope": {"kind": "room", "id": str(evt.room_id)}},
        }
        try:
            async with self.client_session.post(
                f"{self.settings['governor_url'].rstrip('/')}/recall",
                json=payload,
            ) as resp:
                if resp.status != 200:
                    self.log.warning("Recall failed (%s): %s", resp.status, await resp.text())
                    await evt.reply("Recall failed.")
                    return
                data = await resp.json()
                results = data.get("results", [])
                if not results:
                    await evt.reply("No memories found.")
                    return
                lines = []
                for item in results[: self.settings["recall_top_k"]]:
                    txt = item.get("text", "")
                    kind = item.get("kind") or ""
                    lines.append(f"- {txt} ({kind})" if kind else f"- {txt}")
                await evt.reply("\n".join(lines))
        except asyncio.TimeoutError:
            await evt.reply("Governor timeout.")
        except Exception as exc:  # pragma: no cover - defensive
            self.log.exception("Governor recall error: %s", exc)
            await evt.reply("Error recalling.")


def _build_metadata(evt: MessageEvent) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "room_id": str(evt.room_id),
        "event_id": evt.event_id,
        "timestamp": getattr(evt, "timestamp", None),
    }
    displayname = getattr(evt, "sender_profile", None)
    if displayname:
        meta["displayname"] = getattr(displayname, "displayname", None)
    return meta


def _load_settings(config_obj: Any) -> Dict[str, Any]:
    defaults = {
        "ingest_url": "http://127.0.0.1:54322/ingest",
        "api_key": "",
        "rooms_allowlist": set(),
        "react_success": False,
        "log_level": "INFO",
        "cache_ttl_seconds": 300,
        "cache_max_size": 1024,
    }
    if not config_obj:
        return defaults
    try:
        raw = config_obj._load_proxy() or {}
    except Exception:
        raw = {}
    settings = dict(defaults)
    # handle room list
    rooms = raw.get("rooms_allowlist") or []
    settings["rooms_allowlist"] = set(rooms)
    for key in ("ingest_url", "api_key", "react_success", "log_level"):
        if key in raw:
            settings[key] = raw[key]
    for key in ("cache_ttl_seconds", "cache_max_size"):
        if key in raw:
            try:
                settings[key] = int(raw[key])
            except Exception:
                pass
    return settings
