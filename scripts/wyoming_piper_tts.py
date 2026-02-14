#!/usr/bin/env python3
"""Generate speech audio via Wyoming Piper.

Requires: pip install wyoming

Writes a proper WAV file using the AudioStart metadata (rate/width/channels).

Example:
  /home/ryer/clawd/.venv/bin/python scripts/wyoming_piper_tts.py \
    --host 127.0.0.1 --port 10200 \
    --text "Hi, I'm Sam" \
    --out /tmp/sam.wav
"""

from __future__ import annotations

import argparse
import asyncio
import wave
from pathlib import Path

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.tts import Synthesize


async def synthesize(host: str, port: int, text: str, out_path: Path, voice: str | None = None) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async with AsyncTcpClient(host, port) as client:
        await client.write_event(Synthesize(text=text, voice=voice).event())

        audio_bytes = bytearray()
        start: AudioStart | None = None

        while True:
            event = await client.read_event()
            if event is None:
                break

            if AudioStart.is_type(event.type):
                start = AudioStart.from_event(event)
                continue

            if AudioChunk.is_type(event.type):
                chunk = AudioChunk.from_event(event)
                audio_bytes.extend(chunk.audio)
                continue

            if AudioStop.is_type(event.type):
                break

        if not start:
            raise RuntimeError("Did not receive AudioStart from Wyoming server")

        # Write WAV
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(int(start.channels))
            wf.setsampwidth(int(start.width))
            wf.setframerate(int(start.rate))
            wf.writeframes(bytes(audio_bytes))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=10200)
    ap.add_argument("--text", required=True)
    ap.add_argument("--voice", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    asyncio.run(synthesize(args.host, args.port, args.text, Path(args.out), voice=args.voice))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
