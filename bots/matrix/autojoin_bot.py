#!/usr/bin/env python3
"""Auto-accept Matrix room invites for the configured user."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Iterable, Set

from nio import AsyncClient, InviteEvent, JoinError, MatrixInvitedRoom


LOGGER = logging.getLogger("matrix-autojoin")

MATRIX_HOMESERVER = os.getenv("MATRIX_HOMESERVER", "https://matrix.ryer.org")
MATRIX_USER = os.getenv("MATRIX_USER")
MATRIX_PASSWORD = os.getenv("MATRIX_PASSWORD")
MATRIX_ACCESS_TOKEN = os.getenv("MATRIX_ACCESS_TOKEN")

ALLOW_SENDERS = os.getenv("MATRIX_AUTOJOIN_ALLOWLIST_SENDERS", "")
ALLOW_ROOMS = os.getenv("MATRIX_AUTOJOIN_ALLOWLIST_ROOMS", "")


def _parse_csv(value: str) -> Set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


async def main() -> None:
    if not MATRIX_USER:
        raise RuntimeError("Set MATRIX_USER for autojoin bot")

    allow_senders = _parse_csv(ALLOW_SENDERS)
    allow_rooms = _parse_csv(ALLOW_ROOMS)

    client = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER)
    if MATRIX_ACCESS_TOKEN:
        client.access_token = MATRIX_ACCESS_TOKEN
        client.user_id = MATRIX_USER
    else:
        if not MATRIX_PASSWORD:
            raise RuntimeError("Set MATRIX_PASSWORD or MATRIX_ACCESS_TOKEN for autojoin bot")
        resp = await client.login(MATRIX_PASSWORD)
        if resp and getattr(resp, "access_token", None):
            client.access_token = resp.access_token

    async def invite_cb(room: MatrixInvitedRoom, event: InviteEvent) -> None:
        sender = getattr(event, "sender", None)
        if allow_senders and sender not in allow_senders:
            LOGGER.info("Skipping invite room=%s sender=%s (not allowlisted)", room.room_id, sender)
            return
        if allow_rooms and room.room_id not in allow_rooms:
            LOGGER.info("Skipping invite room=%s sender=%s (room not allowlisted)", room.room_id, sender)
            return
        LOGGER.info("Accepting invite room=%s sender=%s", room.room_id, sender)
        resp = await client.join(room.room_id)
        if isinstance(resp, JoinError):
            LOGGER.error("Failed to join room=%s error=%s", room.room_id, resp.message)

    client.add_event_callback(invite_cb, InviteEvent)
    LOGGER.info("Autojoin bot connected as %s", MATRIX_USER)
    await client.sync_forever(timeout=30000, full_state=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main())
