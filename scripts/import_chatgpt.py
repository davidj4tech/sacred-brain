#!/usr/bin/env python3
"""Import ChatGPT export (conversations.json) into Sacred Brain Hippocampus.

Strategy:
- For each conversation, build a compact transcript (limited turns).
- Ask LiteLLM (via local gateway) to extract high-signal memories as JSON.
- Store each extracted memory as a Hippocampus experience with metadata linking back.

This keeps the raw transcript on disk, and stores only distilled facts/preferences/decisions.

Usage:
  /opt/sacred-brain/.venv/bin/python scripts/import_chatgpt_to_hippocampus.py \
    --export /home/ryer/clawd/imports/chatgpt/export-20260128 \
    --user david \
    --limit 816 \
    --dry-run

Then run without --dry-run.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx


def iter_messages(conv: dict) -> list[dict]:
    mapping = conv.get("mapping") or {}
    msgs: list[dict] = []
    for node in mapping.values():
        msg = node.get("message")
        if not msg:
            continue
        content = msg.get("content") or {}
        parts = content.get("parts") or []
        text = "\n".join(p for p in parts if isinstance(p, str)).strip()
        if not text:
            continue
        role = (msg.get("author") or {}).get("role") or "unknown"
        create_time = msg.get("create_time") or conv.get("create_time")
        msgs.append({"role": role, "text": text, "create_time": create_time})

    # Sort by create_time when present.
    msgs.sort(key=lambda m: (m.get("create_time") is None, m.get("create_time") or 0))
    return msgs


def build_compact_transcript(conv: dict, max_head: int = 12, max_tail: int = 18, max_chars: int = 14000) -> str:
    msgs = iter_messages(conv)
    head = msgs[:max_head]
    tail = msgs[-max_tail:] if len(msgs) > max_head else []

    lines: list[str] = []
    if head:
        lines.append("# Transcript (head)")
        for m in head:
            lines.append(f"{m['role']}: {m['text']}")
    if tail:
        lines.append("\n# Transcript (tail)")
        for m in tail:
            lines.append(f"{m['role']}: {m['text']}")

    out = "\n".join(lines).strip()
    return out[:max_chars]


EXTRACT_PROMPT = """You are extracting durable personal memories from a ChatGPT conversation log.

Return ONLY valid JSON: an array of objects.
Each object must have:
- kind: one of ["preference","project","decision","fact","todo","identity","setup"]
- text: a single sentence memory, concise.
- confidence: number 0..1

Rules:
- Extract only high-signal, durable items (things likely to matter later).
- Avoid private secrets (tokens/passwords/keys). If present, do NOT include them.
- Avoid generic advice.
- If nothing durable, return an empty array [].
- Keep at most 5 items.
"""


def extract_memories(
    llm: httpx.Client,
    model: str,
    title: str,
    transcript: str,
) -> list[dict[str, Any]]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": EXTRACT_PROMPT},
            {
                "role": "user",
                "content": f"Title: {title}\n\n{transcript}",
            },
        ],
        "temperature": 0.2,
    }
    r = llm.post("/v1/chat/completions", json=payload)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    # Sometimes models wrap JSON in fences; strip.
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        # remove leading language tag if any
        if "\n" in content:
            content = content.split("\n", 1)[1]
    content = content.strip()
    if not content:
        return []
    data = json.loads(content)
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        kind = str(item.get("kind") or "").strip().lower()
        conf = float(item.get("confidence") or 0)
        if not text or kind not in {"preference", "project", "decision", "fact", "todo", "identity", "setup"}:
            continue
        # extra guard: skip obvious secrets
        lowered = text.lower()
        if any(tok in lowered for tok in ["api key", "access token", "password", "secret", "bearer "]):
            continue
        out.append({"kind": kind, "text": text, "confidence": conf})
    return out[:5]


def store_memory(
    hippo: httpx.Client,
    user_id: str,
    text: str,
    metadata: dict[str, Any],
) -> dict:
    payload = {"user_id": user_id, "text": text, "metadata": metadata}
    r = hippo.post("/memories", json=payload)
    r.raise_for_status()
    return r.json()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", required=True, help="Path to extracted export folder containing conversations.json")
    ap.add_argument("--user", default="david", help="Hippocampus user_id to store under")
    ap.add_argument("--limit", type=int, default=0, help="Max conversations to process (0 = all)")
    ap.add_argument("--offset", type=int, default=0, help="Start index")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--llm-url", default="http://127.0.0.1:4000")
    ap.add_argument("--llm-model", default="gpt-4o-mini")
    ap.add_argument("--hippo-url", default="http://127.0.0.1:54321")
    ap.add_argument("--hippo-key", default="")
    ap.add_argument("--sleep", type=float, default=0.25)
    args = ap.parse_args()

    export_dir = Path(args.export)
    conv_path = export_dir / "conversations.json"
    conv = json.loads(conv_path.read_text("utf-8"))

    start = args.offset
    end = len(conv) if args.limit <= 0 else min(len(conv), start + args.limit)

    llm_headers = {"Content-Type": "application/json"}
    hippo_headers = {"Content-Type": "application/json"}
    if args.hippo_key:
        hippo_headers["X-API-Key"] = args.hippo_key

    llm = httpx.Client(base_url=args.llm_url, headers=llm_headers, timeout=60)
    hippo = httpx.Client(base_url=args.hippo_url, headers=hippo_headers, timeout=60)

    stored = 0
    for i in range(start, end):
        c = conv[i]
        title = c.get("title") or "(untitled)"
        conv_id = c.get("conversation_id")
        create_time = c.get("create_time")
        update_time = c.get("update_time")

        transcript = build_compact_transcript(c)
        if not transcript:
            continue

        try:
            memories = extract_memories(llm, args.llm_model, title, transcript)
        except Exception as exc:
            print(f"[{i}] extract failed: {title}: {exc}")
            continue

        if not memories:
            continue

        for m in memories:
            meta = {
                "source": "chatgpt-export",
                "conversation_id": conv_id,
                "title": title,
                "create_time": create_time,
                "update_time": update_time,
                "kind": m["kind"],
                "confidence": m["confidence"],
            }
            if args.dry_run:
                print(f"[{i}] {m['kind']} ({m['confidence']:.2f}): {m['text']}")
                continue
            try:
                store_memory(hippo, args.user, m["text"], meta)
                stored += 1
            except Exception as exc:
                print(f"[{i}] store failed: {exc}")
                continue

        if args.sleep:
            time.sleep(args.sleep)

    print(f"done. stored={stored} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
