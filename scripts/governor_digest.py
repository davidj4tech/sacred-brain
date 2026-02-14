#!/usr/bin/env python3
"""Generate a nightly memory digest from Memory Governor and append to markdown.

Pulls consolidated memories from the Governor /recall endpoint and writes
a human-readable markdown section into a date-stamped file.

Environment:
  MG_URL              Governor URL (default http://127.0.0.1:54323)
  MG_USER_ID          User ID to recall for (default "default")
  DIGEST_OUTPUT_DIR   Directory to write digest files (required)
  MG_SINCE_DAYS       Recall window in days (default 14)
  MG_TOP_K            Max items to recall (default 12)
  MG_INCLUDE_EPISODIC Include episodic memories (default 0)
  MG_INCLUDE_ARCHIVE  Include ChatGPT archive items (default 0)
  MG_TZ_OFFSET_HOURS  UTC offset for timestamps (default 0)

Usage:
  python3 governor_digest.py
  python3 governor_digest.py --dry-run
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path
from typing import Any

import requests

GOV_URL = os.environ.get("MG_URL", "http://127.0.0.1:54323").rstrip("/")
USER_ID = os.environ.get("MG_USER_ID", "default")
SINCE_DAYS = int(os.environ.get("MG_SINCE_DAYS", "14"))
K = int(os.environ.get("MG_TOP_K", "12"))
INCLUDE_EPISODIC = os.environ.get("MG_INCLUDE_EPISODIC", "0") == "1"
INCLUDE_ARCHIVE = os.environ.get("MG_INCLUDE_ARCHIVE", "0") == "1"
TZ_OFFSET = int(os.environ.get("MG_TZ_OFFSET_HOURS", "0"))

OUTPUT_DIR = os.environ.get("DIGEST_OUTPUT_DIR")


def recall(kinds: list[str]) -> list[dict[str, Any]]:
    payload = {
        "user_id": USER_ID,
        "query": "",
        "k": K,
        "filters": {
            "kinds": kinds,
            "since_days": SINCE_DAYS,
            "min_confidence": 0.2,
            "scope": {"kind": "user", "id": USER_ID},
        },
    }
    r = requests.post(f"{GOV_URL}/recall", json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data.get("results") or data.get("memories") or []


def format_items(items: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for it in items:
        text = (it.get("text") or "").strip().replace("\n", " ")
        if (not INCLUDE_ARCHIVE) and text.startswith("ChatGPT export:"):
            continue
        kind = it.get("kind") or (it.get("metadata") or {}).get("kind") or "memory"
        score = it.get("confidence") or it.get("score")
        if not text:
            continue
        if score is not None:
            try:
                score_s = f"{float(score):.2f}"
            except Exception:
                score_s = str(score)
            lines.append(f"- **{kind}** ({score_s}): {text}")
        else:
            lines.append(f"- **{kind}**: {text}")
    return "\n".join(lines)


def local_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=TZ_OFFSET)))


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    if not OUTPUT_DIR:
        print("Error: DIGEST_OUTPUT_DIR environment variable is required", file=sys.stderr)
        return 2

    kinds = ["semantic", "procedural"]
    if INCLUDE_EPISODIC:
        kinds.append("episodic")

    items = recall(kinds)

    now = local_now()
    day = now.date().isoformat()

    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{day}.md"

    header = f"\n\n## Nightly consolidation digest ({now.strftime('%Y-%m-%d %H:%M')})\n"
    body = format_items(items) if items else "- (No high-salience items in the last window.)"

    if dry_run:
        print(f"Would write to {out_file}:")
        print(header + body)
        return 0

    existing = out_file.read_text(encoding="utf-8") if out_file.exists() else f"# {day}\n"
    out_file.write_text(existing + header + body + "\n", encoding="utf-8")

    print(f"Wrote digest to {out_file} ({len(items)} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
