#!/usr/bin/env python3
"""Mention-triggered Matrix bot that relays context to Sacred Brain."""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import textwrap
import time
import urllib.parse
from pathlib import Path

import httpx
from nio import (
    AsyncClient,
    DownloadError,
    InviteMemberEvent,
    LoginResponse,
    MatrixInvitedRoom,
    MatrixRoom,
    RoomMessageAudio,
    RoomMessageText,
)

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("matrix-mention-bot")
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("nio").setLevel(logging.WARNING)

MATRIX_HOMESERVER = os.getenv("MATRIX_HOMESERVER", "https://matrix.ryer.org")
MATRIX_USER = os.getenv("MATRIX_USER")
MATRIX_PASSWORD = os.getenv("MATRIX_PASSWORD")
MATRIX_ACCESS_TOKEN = os.getenv("MATRIX_ACCESS_TOKEN")
SACRED_BRAIN_URL = os.getenv("SACRED_BRAIN_URL", "http://127.0.0.1:8000/matrix/respond")
SACRED_BRAIN_API_KEY = os.getenv("SACRED_BRAIN_API_KEY")
SACRED_BRAIN_TIMEOUT = float(os.getenv("SACRED_BRAIN_TIMEOUT", "120"))
MENTION_NAME = os.getenv("MATRIX_MENTION", "@sacredbrain")
AUTOJOIN_ALLOWLIST_SENDERS = [
    s.strip() for s in os.getenv("MATRIX_AUTOJOIN_ALLOWLIST_SENDERS", "").split(",") if s.strip()
]
ALLOW_ROOMS = [r.strip() for r in os.getenv("MATRIX_ALLOW_ROOMS", "").split(",") if r.strip()]
AUTO_REPLY_ROOMS = [r.strip() for r in os.getenv("MATRIX_AUTO_REPLY_ROOMS", "").split(",") if r.strip()]
AUTO_REMEMBER_ENABLED = os.getenv("AUTO_REMEMBER_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
AUTO_REMEMBER_MIN_WORDS = int(os.getenv("AUTO_REMEMBER_MIN_WORDS", "4"))
AUTO_REMEMBER_KEYWORDS = [kw.strip() for kw in os.getenv("AUTO_REMEMBER_KEYWORDS", "remember,note,keep,save,log").split(",") if kw.strip()]
AUTO_REMEMBER_EXCLUDE_RE = re.compile(os.getenv("AUTO_REMEMBER_EXCLUDE_RE", r"(https?://|\\b\\d{4,5}\\b|api[_-]?key|token)"), re.IGNORECASE)
AUTO_REMEMBER_LLM_ENABLED = os.getenv("AUTO_REMEMBER_LLM_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
AUTO_REMEMBER_LLM_BASE_URL = os.getenv("AUTO_REMEMBER_LLM_BASE_URL", "http://127.0.0.1:4000")
AUTO_REMEMBER_LLM_MODEL = os.getenv("AUTO_REMEMBER_LLM_MODEL", "gpt-4o-mini")
AUTO_REMEMBER_LLM_TIMEOUT = float(os.getenv("AUTO_REMEMBER_LLM_TIMEOUT", "4.0"))
AUTO_TUNE_PATH = Path(os.getenv("AUTO_TUNE_PATH", "var/auto_memory_tuning.json"))

BAIBOT_TTS_ENABLED = os.getenv("BAIBOT_TTS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
EDGE_TTS_URL = os.getenv("EDGE_TTS_URL", "http://127.0.0.1:5050/v1/audio/speech")
BAIBOT_TTS_URL = os.getenv("BAIBOT_TTS_URL", "http://127.0.0.1:4000/v1/audio/speech")
BAIBOT_TTS_MODEL = os.getenv("BAIBOT_TTS_MODEL", "gpt-4o-mini-tts")
BAIBOT_TTS_VOICE = os.getenv("BAIBOT_TTS_VOICE", "shimmer")
BAIBOT_TTS_FORMAT = os.getenv("BAIBOT_TTS_FORMAT", "opus")
BAIBOT_API_KEY = os.getenv("BAIBOT_API_KEY", "")

PERSONA_VOICE_MAP = {
    "sam": "en-US-AndrewNeural",
    "zara": "en-US-AvaNeural",
    "aria": "en-US-AriaNeural",
    "paige": "en-GB-SoniaNeural",
}


STT_ENABLED = os.getenv("BAIBOT_STT_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
STT_URL = os.getenv("BAIBOT_STT_URL", "http://127.0.0.1:4000/v1/audio/transcriptions")
STT_MODEL = os.getenv("BAIBOT_STT_MODEL", "whisper-1")
STT_API_KEY = os.getenv("BAIBOT_STT_API_KEY", "")
STT_TIMEOUT = float(os.getenv("BAIBOT_STT_TIMEOUT", "20.0"))

if not MATRIX_USER or not (MATRIX_PASSWORD or MATRIX_ACCESS_TOKEN):
    raise RuntimeError("Set MATRIX_USER and MATRIX_PASSWORD or MATRIX_ACCESS_TOKEN")


def _clean_reply(text: str) -> str:
    if not text: return ""
    # Strip <think> blocks
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    return text

async def main() -> None:
    client = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER)
    recent_room_handled: dict[str, float] = {}
    if MATRIX_ACCESS_TOKEN:
        client.access_token = MATRIX_ACCESS_TOKEN
        client.user_id = MATRIX_USER
    else:
        resp = await client.login(MATRIX_PASSWORD)
        if isinstance(resp, LoginResponse):
            print("Logged in")
        else:
            raise RuntimeError(f"Login failed: {resp}")

    async def message_cb(room: MatrixRoom, event: RoomMessageText) -> None:
        if event.sender == MATRIX_USER:
            return
        members = getattr(room, "members", None)
        users = getattr(room, "users", None)
        member_count = len(members) if members is not None else (len(users) if users is not None else 0)
        is_dm = member_count == 0 or member_count <= 2
        # Room allowlist: allow DMs always; allow listed rooms; ignore everything else
        if ALLOW_ROOMS and (not is_dm) and room.room_id not in ALLOW_ROOMS:
            return
        intent_hit = _should_auto_remember(event.body.strip().lower()) if AUTO_REMEMBER_ENABLED else False
        recent_window = 300  # seconds
        last_handled_ts = recent_room_handled.get(room.room_id, 0)
        recent_session = (time.time() - last_handled_ts) < recent_window if last_handled_ts else False
        mention_hit = MENTION_NAME.lower() in event.body.lower()
        auto_reply_hit = room.room_id in AUTO_REPLY_ROOMS
        should_handle = is_dm or mention_hit or auto_reply_hit
        LOGGER.info(
            "event: room=%s sender=%s is_dm=%s mention_hit=%s intent=%s recent=%s",
            room.room_id,
            event.sender,
            is_dm,
            MENTION_NAME in event.body,
            intent_hit,
            recent_session,
        )
        body_lower = event.body.strip()
        # Inline remember/recall commands to Hippocampus
        if body_lower.startswith("!remember "):
            text = event.body.split(" ", 1)[1].strip()
            ack = await store_memory(event.sender, text, room.room_id)
            await client.room_send(
                room_id=room.room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": ack},
            )
            return
        if body_lower.startswith("!recall"):
            query = event.body.split(" ", 1)[1].strip() if " " in event.body else "*"
            reply = await recall_memory(event.sender, query)
            await client.room_send(
                room_id=room.room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": _clean_reply(reply)},
            )
            return

        if not should_handle:
            return

        # Auto-log handled messages to memory when heuristics pass
        if AUTO_REMEMBER_ENABLED and not body_lower.startswith("!recall") and _should_auto_remember(body_lower):
            asyncio.create_task(store_memory(event.sender, event.body, room.room_id, auto=True))

        # Determine Persona
        active_persona = None
        defaults_raw = os.getenv("MATRIX_ROOM_DEFAULTS", "")
        for pair in defaults_raw.split(","):
            if "=" in pair:
                rid, p = pair.split("=", 1)
                if rid.strip() == room.room_id:
                    active_persona = p.strip()
                    break
        try:
            context = gather_context(room)
            reply = await call_sacred_brain(room.room_id, event, context, persona=active_persona)
        except Exception as exc:
            LOGGER.warning("call_sacred_brain failed: %r", exc)
            reply = None
        if reply:
            try:
                # Clean internal thought blocks
                reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL).strip()
                if not reply:
                    return
                await client.room_send(
                    room_id=room.room_id,
                    message_type="m.room.message",
                    content={"msgtype": "m.text", "body": _clean_reply(reply)},
                )
                if BAIBOT_TTS_ENABLED:
                    asyncio.create_task(send_tts(reply, room.room_id, client, persona=active_persona))
            except Exception as exc:
                LOGGER.warning("room_send failed: %s", exc)
            recent_room_handled[room.room_id] = time.time()

    async def invite_cb(room: MatrixInvitedRoom, event: InviteMemberEvent) -> None:
        # Auto-join disabled (temporary) to avoid rate limiting.
        LOGGER.info("invite: autojoin disabled; ignoring room=%s from=%s", room.room_id, event.sender)
        return

    client.add_event_callback(invite_cb, InviteMemberEvent)
    client.add_event_callback(message_cb, RoomMessageText)
    client.add_event_callback(lambda room, event: asyncio.create_task(audio_cb(room, event, client)), RoomMessageAudio)

    await client.sync_forever(timeout=30000, full_state=True)

def gather_context(room: MatrixRoom, limit: int = 20) -> list[str]:
    timeline = getattr(room, "timeline", []) or []
    events = timeline[-limit:]
    return [getattr(ev, 'body', '') for ev in events if isinstance(ev, RoomMessageText)]


async def call_sacred_brain(room_id: str, event: RoomMessageText, context: list[str], persona: str = None) -> str | None:
    payload = {"room_id": room_id, "sender": event.sender, "body": event.body, "context": context}
    if persona:
        payload["persona"] = persona
    headers = {"Content-Type": "application/json"}
    if SACRED_BRAIN_API_KEY:
        headers["X-API-Key"] = SACRED_BRAIN_API_KEY
    async with httpx.AsyncClient(timeout=SACRED_BRAIN_TIMEOUT) as client:
        resp = await client.post(SACRED_BRAIN_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data.get("reply")

    headers = {"Content-Type": "application/json"}
    if SACRED_BRAIN_API_KEY:
        headers["X-API-Key"] = SACRED_BRAIN_API_KEY
    async with httpx.AsyncClient(timeout=SACRED_BRAIN_TIMEOUT) as client:
        resp = await client.post(SACRED_BRAIN_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data.get("reply")



def _should_auto_remember(body_lower: str) -> bool:
    tune = _load_tuning()
    min_words = tune.get("min_words", AUTO_REMEMBER_MIN_WORDS)
    llm_strict = tune.get("llm_strict", False)
    llm_enabled = tune.get("llm_enabled", AUTO_REMEMBER_LLM_ENABLED)

    if len(body_lower.split()) < min_words:
        return False
    if AUTO_REMEMBER_EXCLUDE_RE.search(body_lower):
        return False
    if not any(kw in body_lower for kw in AUTO_REMEMBER_KEYWORDS):
        return False
    if llm_enabled:
        return _llm_allow(body_lower, strict=llm_strict)
    return True


def _llm_allow(body_lower: str, strict: bool = False) -> bool:
    prompt = textwrap.dedent(
        f"""
        Decide if this message should be stored as a memory.
        Reply ONLY with YES or NO.
        Message: \"{body_lower}\"
        """
    ).strip()
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": AUTO_REMEMBER_LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a filter deciding whether to store user text as memory."},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        resp = httpx.post(
            f"{AUTO_REMEMBER_LLM_BASE_URL}/v1/chat/completions",
            json=payload,
            timeout=AUTO_REMEMBER_LLM_TIMEOUT,
        )
        resp.raise_for_status()
        content = (
            resp.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
            .upper()
        )
        if content.startswith("Y"):
            return True
        if not strict and content.startswith("MAYBE"):
            return True
        return False
    except Exception:
        return False


_TUNE_CACHE = {"loaded_at": 0.0, "data": {}}


def _load_tuning() -> dict:
    # Reload every 30s max
    import time

    now = time.time()
    if _TUNE_CACHE["loaded_at"] and now - _TUNE_CACHE["loaded_at"] < 30:
        return _TUNE_CACHE["data"]
    if not AUTO_TUNE_PATH.exists():
        _TUNE_CACHE["loaded_at"] = now
        _TUNE_CACHE["data"] = {}
        return _TUNE_CACHE["data"]
    try:
        data = json.loads(AUTO_TUNE_PATH.read_text())
        if isinstance(data, dict):
            _TUNE_CACHE["data"] = data
    except Exception:
        _TUNE_CACHE["data"] = {}
    _TUNE_CACHE["loaded_at"] = now
    return _TUNE_CACHE["data"]

async def send_tts(text: str, room_id: str, client: AsyncClient, persona: str = None) -> None:
    """
    Render reply to speech via TTS API and post as m.audio.
    Runs best-effort; failures are logged but not surfaced to the room.
    """
    try:
        headers = {"Content-Type": "application/json"}
        if BAIBOT_API_KEY:
            headers["Authorization"] = f"Bearer {BAIBOT_API_KEY}"
            headers["X-API-Key"] = BAIBOT_API_KEY
        async with httpx.AsyncClient(timeout=20.0) as http:
            voice = BAIBOT_TTS_VOICE
            if persona and persona.lower() in PERSONA_VOICE_MAP:
                voice = PERSONA_VOICE_MAP[persona.lower()]

            # Route to Edge TTS when using Neural voices
            target_url = BAIBOT_TTS_URL
            payload = {
                "model": BAIBOT_TTS_MODEL,
                "input": text,
                "voice": voice,
                "response_format": BAIBOT_TTS_FORMAT,
            }
            is_edge = "Neural" in str(voice)
            if is_edge:
                target_url = EDGE_TTS_URL
                payload = {"input": text, "voice": voice}

            resp = await http.post(target_url, headers=headers, json=payload)
            resp.raise_for_status()
            audio_bytes = resp.content
        if not audio_bytes:
            return
        # Matrix requires upload to get an mxc URI.
        buf = io.BytesIO(audio_bytes)
        content_type = "audio/mpeg" if ("Neural" in str(voice) or BAIBOT_TTS_FORMAT == "mp3") else f"audio/{BAIBOT_TTS_FORMAT}"
        filename = "sam-tts.mp3" if ("Neural" in str(voice)) else f"sam-tts.{BAIBOT_TTS_FORMAT}"
        upload_resp = await client.upload(
            buf,
            content_type=content_type,
            filename=filename,
        )
        if not hasattr(upload_resp, "content_uri"):
            if isinstance(upload_resp, (list, tuple)) and upload_resp:
                for candidate in upload_resp:
                    if hasattr(candidate, "content_uri"):
                        upload_resp = candidate
                        break
        mxc_url = getattr(upload_resp, "content_uri", None) or getattr(upload_resp, "uri", None)
        if not mxc_url:
            raise RuntimeError("upload returned no mxc uri")
        content = {
            "msgtype": "m.audio",
            "body": "Sam (voice)",
            "url": mxc_url,
            "info": {
                "mimetype": "audio/mpeg" if ("Neural" in str(voice) or BAIBOT_TTS_FORMAT == "mp3") else f"audio/{BAIBOT_TTS_FORMAT}",
                "size": len(audio_bytes),
            },
        }
        await client.room_send(room_id=room_id, message_type="m.room.message", content=content)
    except Exception as exc:
        LOGGER.warning("send_tts failed: %s", exc)

async def audio_cb(room: MatrixRoom, event: RoomMessageAudio, client: AsyncClient) -> None:
    if event.sender == MATRIX_USER or not STT_ENABLED:
        return
    try:
        if not event.url:
            return
        audio_bytes = await _fetch_media_bytes(client, event.url)
        if not audio_bytes:
            return
        mimetype = getattr(event, "info", {}).get("mimetype") if getattr(event, "info", None) else "audio/ogg"
        if mimetype and "opus" in mimetype:
            mimetype = "audio/ogg"
        filename = "audio.ogg" if mimetype and "ogg" in mimetype else "audio.wav"
        headers = {}
        if STT_API_KEY:
            headers["Authorization"] = f"Bearer {STT_API_KEY}"
        files = {"file": (filename, audio_bytes, mimetype or "application/octet-stream")}
        data = {"model": STT_MODEL}
        async with httpx.AsyncClient(timeout=STT_TIMEOUT) as http:
            resp = await http.post(STT_URL, headers=headers, data=data, files=files)
            resp.raise_for_status()
            result = resp.json()
        transcript = result.get("text") or result.get("transcription") or ""
        if not transcript:
            return
        await client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": f"(transcript) {transcript}"},
        )
    except Exception as exc:
        LOGGER.warning("audio_cb (stt) failed: %s", exc)


async def _fetch_media_bytes(client: AsyncClient, mxc_url: str) -> bytes | None:
    """
    Try nio download first; fall back to direct HTTP with access token if needed.
    """
    try:
        download = await client.download(mxc_url)
        if isinstance(download, DownloadError):
            LOGGER.warning("audio_cb download error for %s: %s", mxc_url, download.message)
        else:
            body = getattr(download, "body", None)
            if body:
                return body
    except Exception as exc:
        LOGGER.warning("audio_cb download exception for %s: %s", mxc_url, exc)

    # Fallback via raw HTTP (try v3 and r0 with allow_remote)
    try:
        parsed = urllib.parse.urlparse(mxc_url)
        if parsed.scheme != "mxc" or not parsed.netloc or not parsed.path:
            return None
        server = parsed.netloc
        media_id = parsed.path.lstrip("/")
        token = getattr(client, "access_token", None)
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        candidates = [
            f"{MATRIX_HOMESERVER}/_matrix/media/v3/download/{server}/{media_id}?allow_remote=true",
            f"{MATRIX_HOMESERVER}/_matrix/media/r0/download/{server}/{media_id}?allow_remote=true",
        ]
        with httpx.Client(timeout=10.0, verify=True) as http:
            for url in candidates:
                resp = http.get(url, headers=headers)
                if resp.status_code == 200 and resp.content:
                    return resp.content
                LOGGER.warning("audio_cb http fallback failed %s status=%s", url, resp.status_code)
    except Exception as exc:
        LOGGER.warning("audio_cb http fallback exception for %s: %s", mxc_url, exc)
    return None


async def store_memory(user_id: str, text: str, room_id: str, auto: bool = False) -> str:
    url = SACRED_BRAIN_URL.rsplit("/matrix/respond", 1)[0].rstrip("/") + "/memories"
    headers = {"Content-Type": "application/json"}
    if SACRED_BRAIN_API_KEY:
        headers["X-API-Key"] = SACRED_BRAIN_API_KEY
    metadata = {"room_id": room_id, "via": "matrix-bot"}
    if auto:
        metadata["auto"] = True
        metadata["salience"] = "low"
        metadata.setdefault("relevance", "keep")
    payload = {"user_id": user_id, "text": text, "metadata": metadata}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            LOGGER.info(
                "memory stored user=%s room=%s auto=%s status=%s",
                user_id,
                room_id,
                auto,
                resp.status_code,
            )
            return "Stored."
        except Exception as exc:
            LOGGER.warning("store_memory failed: %s", exc)
            return "Error storing."


async def recall_memory(user_id: str, query: str) -> str:
    url = SACRED_BRAIN_URL.rsplit("/matrix/respond", 1)[0].rstrip("/") + f"/memories/{user_id}"
    headers = {}
    if SACRED_BRAIN_API_KEY:
        headers["X-API-Key"] = SACRED_BRAIN_API_KEY
    params = {"query": query, "limit": 5}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            memories = data.get("memories", [])
            if not memories:
                return "Nothing found."
            lines = []
            for mem in memories[:5]:
                txt = mem.get("text", "")
                lines.append(f"- {txt}")
            return "Recap:\n" + "\n".join(lines)
        except Exception as exc:
            LOGGER.warning("recall_memory failed: %s", exc)
            return "Error recalling."

if __name__ == "__main__":
    asyncio.run(main())
