"""Maubot plugin that relays mentions to Sacred Brain with optional TTS/STT."""
from __future__ import annotations

import asyncio
import httpx
from maubot.handlers import event
from mautrix.crypto.attachments import decrypt_attachment, encrypt_attachment
from mautrix.types import (
    AudioInfo,
    EncryptedFile,
    EventType,
    MediaMessageEventContent,
    MessageType,
    PaginationDirection,
)
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper

from maubot import MessageEvent, Plugin


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        for key in (
            "mention",
            "allow_rooms",
            "persona",
            "context_limit",
            "autojoin_enabled",
            "autojoin_allow_rooms",
            "autojoin_allow_senders",
            "sacred_brain_url",
            "api_key",
            "timeout_seconds",
            "tts_enabled",
            "tts_url",
            "tts_model",
            "tts_voice",
            "tts_format",
            "tts_api_key",
            "tts_timeout_seconds",
            "tts_auto_max_words",
            "stt_enabled",
            "stt_url",
            "stt_model",
            "stt_api_key",
            "stt_timeout_seconds",
        ):
            helper.copy(key)


class SacredBrainMentionBot(Plugin):
    async def start(self) -> None:
        # NOTE: maubot config proxy was unreliable in this environment, so we
        # keep a local config dict with the needed values.
        self._cfg = {
            # Trigger word for group rooms (case-insensitive substring match).
            # Keep it short and natural for voice: e.g. "Sam".
            "mention": "sam",
            "allow_rooms": [],
            "persona": None,
            # Smaller context reduces latency (important for TTS responsiveness).
            "context_limit": 8,
            "autojoin_enabled": True,
            "autojoin_allow_rooms": [],
            "autojoin_allow_senders": [],
            # Hippocampus service (Matrix responder) default port is 54321.
            "sacred_brain_url": "http://172.17.0.1:54321/matrix/respond",
            "api_key": "hippo_local_a58b583f7a844f0eb3bc02e58d56f5bd",
            # LLM calls can be slow; don't fail fast.
            "timeout_seconds": 180,
            "tts_enabled": True,
            "tts_url": "http://172.17.0.1:4000/v1/audio/speech",
            "tts_model": "gpt-4o-mini-tts",
            "tts_voice": "shimmer",
            "tts_format": "mp3",
            "tts_api_key": "",
            "tts_timeout_seconds": 60,
            # Auto-TTS for short replies
            "tts_auto_max_words": 20,
            "stt_enabled": True,
            "stt_url": "http://172.17.0.1:4000/v1/audio/transcriptions",
            "stt_model": "whisper-1",
            "stt_api_key": "",
            "stt_timeout_seconds": 20,
        }
        self._room_dm_cache: dict[str, bool] = {}
        self._room_encrypt_cache: dict[str, bool] = {}

    @event.on(EventType.ROOM_MEMBER)
    async def handle_invite(self, evt) -> None:
        if not self._get_cfg("autojoin_enabled"):
            return
        membership = getattr(getattr(evt, "content", None), "membership", None)
        if membership != "invite":
            return
        target = getattr(evt, "state_key", None)
        if target and target != self.client.mxid:
            return

        allow_rooms = self._get_cfg("autojoin_allow_rooms") or []
        if allow_rooms and evt.room_id not in allow_rooms:
            self.log.info("Skipping invite for %s (room not allowlisted)", evt.room_id)
            return
        allow_senders = self._get_cfg("autojoin_allow_senders") or []
        sender = getattr(evt, "sender", None)
        if allow_senders and sender not in allow_senders:
            self.log.info("Skipping invite for %s from %s (sender not allowlisted)", evt.room_id, sender)
            return

        try:
            await self.client.join_room(evt.room_id)
            self.log.info("Auto-joined room %s from invite by %s", evt.room_id, sender)
        except Exception as exc:  # pragma: no cover - network and API errors
            self.log.warning("Auto-join failed for %s: %s", evt.room_id, exc)

    @event.on(EventType.ROOM_MESSAGE)
    async def handle_message(self, evt: MessageEvent) -> None:
        if evt.sender == self.client.mxid:
            return

        if evt.content.msgtype == MessageType.AUDIO:
            await self._handle_audio(evt)
            return
        if evt.content.msgtype != MessageType.TEXT:
            return

        body = evt.content.body or ""
        mention = (self._get_cfg("mention") or "").lower()
        if mention and mention not in body.lower():
            if not await self._is_direct_room(evt.room_id):
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
        persona = self._get_cfg("persona")
        if persona:
            payload["persona"] = persona

        reply = await self._call_sacred_brain(payload)
        if reply:
            await evt.reply(reply)
            if self._get_cfg("tts_enabled") and self._should_tts(body, reply):
                asyncio.create_task(self._send_tts(evt.room_id, reply))

    async def _handle_audio(self, evt: MessageEvent) -> None:
        if not self._get_cfg("stt_enabled"):
            return
        allow_rooms = self._get_cfg("allow_rooms") or []
        if allow_rooms and evt.room_id not in allow_rooms:
            return
        if not getattr(evt.content, "url", None) and not getattr(evt.content, "file", None):
            return
        try:
            audio_bytes = await self._download_audio(evt)
            if not audio_bytes:
                return
            transcript = await self._call_stt(audio_bytes)
            if transcript:
                await self.client.send_message_event(
                    evt.room_id,
                    EventType.ROOM_MESSAGE,
                    {
                        "msgtype": "m.text",
                        "body": f"(transcript) {transcript}",
                    },
                )
        except Exception as exc:  # pragma: no cover - defensive for API changes
            self.log.warning("STT handling failed: %s", exc)

    async def _gather_context(self, evt: MessageEvent) -> list[str]:
        """Try to include recent text messages; fall back to just the triggering body."""
        limit = max(int(self._get_cfg("context_limit") or 0), 0)
        messages: list[str] = []
        if evt.content.body:
            messages.append(evt.content.body)
        if limit <= 1:
            return messages

        try:
            history = await self.client.get_messages(
                evt.room_id, PaginationDirection.BACKWARD, limit=limit - 1
            )
            for msg in history.events:
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

    def _should_tts(self, user_body: str, reply: str) -> bool:
        """Mode B: auto-TTS for short replies, or when explicitly asked."""
        body = (user_body or "").lower()
        if any(tok in body for tok in ["voice:", "say:", "tts:", "speak:"]):
            return True
        # Auto for short replies
        max_words = int(self._get_cfg("tts_auto_max_words") or 20)
        return len((reply or "").split()) <= max_words

    async def _send_tts(self, room_id: str, text: str) -> None:
        try:
            audio_bytes = await self._call_tts(text)
            if not audio_bytes:
                return
            is_encrypted = await self._is_encrypted_room(room_id)
            content = await self._build_audio_content(audio_bytes, is_encrypted)
            if not content:
                self.log.warning("TTS content build failed for %s", room_id)
                return
            await self.client.send_message_event(room_id, EventType.ROOM_MESSAGE, content)
        except Exception as exc:  # pragma: no cover - defensive for API changes
            self.log.warning("TTS send failed for %s: %s", room_id, exc)

    async def _call_tts(self, text: str) -> bytes | None:
        headers = {"Content-Type": "application/json"}
        api_key = self._get_cfg("tts_api_key") or ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            headers["X-API-Key"] = api_key
        payload = {
            "model": self._get_cfg("tts_model"),
            "input": text,
            "voice": self._get_cfg("tts_voice"),
            "response_format": self._get_cfg("tts_format"),
        }
        timeout = float(self._get_cfg("tts_timeout_seconds") or 20)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(self._get_cfg("tts_url"), headers=headers, json=payload)
                resp.raise_for_status()
                return resp.content
        except Exception as exc:  # pragma: no cover - network and remote errors
            self.log.warning("TTS request failed: %s", exc)
            return None

    async def _call_stt(self, audio_bytes: bytes) -> str | None:
        headers = {}
        api_key = self._get_cfg("stt_api_key") or ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            headers["X-API-Key"] = api_key
        files = {"file": ("audio.ogg", audio_bytes, "audio/ogg")}
        data = {"model": self._get_cfg("stt_model")}
        timeout = float(self._get_cfg("stt_timeout_seconds") or 20)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(self._get_cfg("stt_url"), headers=headers, data=data, files=files)
                resp.raise_for_status()
                result = resp.json()
                return result.get("text") or result.get("transcription") or ""
        except Exception as exc:  # pragma: no cover - network and remote errors
            self.log.warning("STT request failed: %s", exc)
            return None

    async def _download_audio(self, evt: MessageEvent) -> bytes | None:
        file_info = getattr(evt.content, "file", None)
        if isinstance(file_info, EncryptedFile) and file_info.url:
            ciphertext = await self.client.download_media(file_info.url)
            sha256 = file_info.hashes.get("sha256") if file_info.hashes else None
            if not sha256:
                return None
            return decrypt_attachment(ciphertext, file_info.key.key, sha256, file_info.iv)
        url = getattr(evt.content, "url", None)
        if not url:
            return None
        return await self.client.download_media(url)

    async def _build_audio_content(
        self, audio_bytes: bytes, encrypted: bool
    ) -> MediaMessageEventContent | None:
        fmt = (self._get_cfg("tts_format") or "mp3").lower()
        mimetype = "audio/mpeg" if fmt == "mp3" else f"audio/{fmt}"
        filename = f"sam-tts.{fmt}"
        if encrypted:
            ciphertext, enc_file = encrypt_attachment(audio_bytes)
            mxc = await self.client.upload_media(
                ciphertext,
                mime_type="application/octet-stream",
                filename=filename,
                size=len(ciphertext),
            )
            enc_file.url = str(mxc)
            return MediaMessageEventContent(
                msgtype=MessageType.AUDIO,
                body="Sam (voice)",
                file=enc_file,
                info=AudioInfo(mimetype=mimetype, size=len(audio_bytes)),
            )
        mxc = await self.client.upload_media(
            audio_bytes,
            mime_type=mimetype,
            filename=filename,
            size=len(audio_bytes),
        )
        return MediaMessageEventContent(
            msgtype=MessageType.AUDIO,
            body="Sam (voice)",
            url=str(mxc),
            info=AudioInfo(mimetype=mimetype, size=len(audio_bytes)),
        )

    async def _is_direct_room(self, room_id: str) -> bool:
        cached = self._room_dm_cache.get(room_id)
        if cached is not None:
            return cached
        try:
            members = await self.client.get_joined_members(room_id)
            is_direct = len(members) <= 2
        except Exception as exc:  # pragma: no cover - defensive for API changes
            self.log.warning("Failed to check member count: %s", exc)
            is_direct = False
        self._room_dm_cache[room_id] = is_direct
        return is_direct

    async def _is_encrypted_room(self, room_id: str) -> bool:
        cached = self._room_encrypt_cache.get(room_id)
        if cached is not None:
            return cached
        try:
            await self.client.get_state_event(room_id, EventType.ROOM_ENCRYPTION)
            encrypted = True
        except Exception:
            encrypted = False
        self._room_encrypt_cache[room_id] = encrypted
        return encrypted

    def _get_cfg(self, key: str):
        try:
            value = self.config.get(key)
        except Exception:
            value = None
        if value is None:
            return self._cfg.get(key)
        return value
