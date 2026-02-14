#!/usr/bin/env python3
"""Sync Markdown memory files into Sacred Brain Hippocampus.

Reads MEMORY.md + memory/*.md from a configurable source directory and
pushes each non-empty, non-header line as a memory record. Deduplicates
by content hash — only new or changed lines are pushed.

Environment:
  MEMORY_SYNC_ROOT     source directory containing MEMORY.md and/or memory/ subdir (required)
  HIPPOCAMPUS_URL      default http://127.0.0.1:54321
  HIPPOCAMPUS_API_KEY  required when Hippocampus auth is enabled
  HIPPOCAMPUS_USER_ID  default "default"
  HIPPOCAMPUS_SQLITE_PATH  for local dedup (default: /var/lib/sacred-brain/hippocampus/hippocampus_memories.sqlite)

Usage:
  python3 memory_sync.py push
  python3 memory_sync.py push --dry-run
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import time
from collections.abc import Iterable

import requests

DEFAULT_DB = "/var/lib/sacred-brain/hippocampus/hippocampus_memories.sqlite"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def iter_memory_lines(root: pathlib.Path) -> Iterable[tuple[str, dict]]:
    # MEMORY.md at root
    mem = root / "MEMORY.md"
    if mem.exists():
        for i, line in enumerate(mem.read_text(encoding="utf-8").splitlines(), start=1):
            t = line.strip()
            if not t or t.startswith("#"):
                continue
            yield t, {"source": "MEMORY.md", "line": i}

    # memory/*.md (non-recursive — excludes nested subdirs like memory/memory/)
    memdir = root / "memory"
    if memdir.exists():
        for p in sorted(memdir.glob("*.md")):
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
                t = line.strip()
                if not t or t.startswith("#"):
                    continue
                yield t, {"source": str(p.relative_to(root)), "line": i}


def load_existing_hashes(db_path: str, user_id: str) -> set[str]:
    """Load content hashes from existing memories to skip duplicates."""
    hashes: set[str] = set()
    if not pathlib.Path(db_path).exists():
        return hashes
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT metadata FROM memories WHERE user_id = ?", (user_id,)
        ).fetchall()
        conn.close()
        for (meta_str,) in rows:
            if not meta_str:
                continue
            try:
                meta = json.loads(meta_str)
                h = meta.get("hash")
                if h:
                    hashes.add(h)
            except (json.JSONDecodeError, TypeError):
                continue
    except Exception as exc:
        print(f"Warning: could not read existing hashes from DB: {exc}", file=sys.stderr)
    return hashes


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]

    if not args or args[0] not in {"push"}:
        print("Usage: memory_sync.py push [--dry-run]", file=sys.stderr)
        print("  Set MEMORY_SYNC_ROOT to the directory containing MEMORY.md and/or memory/", file=sys.stderr)
        return 2

    root_str = os.environ.get("MEMORY_SYNC_ROOT")
    if not root_str:
        print("Error: MEMORY_SYNC_ROOT environment variable is required", file=sys.stderr)
        return 2
    root = pathlib.Path(root_str)
    if not root.is_dir():
        print(f"Error: MEMORY_SYNC_ROOT={root} is not a directory", file=sys.stderr)
        return 2

    base = os.environ.get("HIPPOCAMPUS_URL", "http://127.0.0.1:54321").rstrip("/")
    api_key = os.environ.get("HIPPOCAMPUS_API_KEY")
    user_id = os.environ.get("HIPPOCAMPUS_USER_ID", "default")
    db_path = os.environ.get("HIPPOCAMPUS_SQLITE_PATH", DEFAULT_DB)

    headers: dict[str, str] = {"content-type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    # Health check
    r = requests.get(f"{base}/health", timeout=5)
    r.raise_for_status()

    # Load existing hashes for dedup
    existing = load_existing_hashes(db_path, user_id)
    print(f"Loaded {len(existing)} existing hashes for user {user_id}")

    pushed = 0
    skipped = 0
    for text, meta in iter_memory_lines(root):
        h = _hash(text)
        if h in existing:
            skipped += 1
            continue

        if dry_run:
            print(f"[new] {meta['source']}:{meta['line']}: {text[:80]}")
            pushed += 1
            continue

        payload = {
            "user_id": user_id,
            "text": text,
            "metadata": {
                **meta,
                "hash": h,
                "kind": "identity",
                "source": f"memory-sync:{meta['source']}",
                "ts": int(time.time()),
            },
        }
        resp = requests.post(f"{base}/memories", json=payload, headers=headers, timeout=15)
        if resp.status_code == 401:
            raise SystemExit("Hippocampus returned 401. Set HIPPOCAMPUS_API_KEY.")
        resp.raise_for_status()
        existing.add(h)
        pushed += 1

    print(f"Done. pushed={pushed} skipped={skipped} dry_run={dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
