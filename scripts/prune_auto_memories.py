#!/usr/bin/env python3
"""
Prune low-salience auto memories from Hippocampus.

Uses HIPPOCAMPUS_URL and HIPPOCAMPUS_API_KEY (X-API-Key) if set, or can
read the SQLite file directly when HIPPOCAMPUS_SQLITE_PATH is provided.

Default policy:
- Only consider entries tagged metadata.auto=true.
- Hard-drop anything explicitly tagged relevance=drop.
- Prune items older than MAX_AGE_DAYS (default 30).
- Keep only the most recent MAX_PER_USER (default 200) per user after applying
  relevance/age rules.
"""
from __future__ import annotations

import datetime as dt

from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "hippocampus_memories.sqlite"
import os
import sqlite3
import sys
from typing import Any

import requests

HIPPO_URL = os.getenv("HIPPOCAMPUS_URL", "http://127.0.0.1:54321")
HIPPO_KEY = os.getenv("HIPPOCAMPUS_API_KEY") or os.getenv("HIPPO_API_KEY")
SQLITE_PATH = os.getenv("HIPPOCAMPUS_SQLITE_PATH", str(DEFAULT_DB))
MAX_PER_USER = int(os.getenv("AUTO_PRUNE_MAX_PER_USER", "200"))
MAX_AGE_DAYS = int(os.getenv("AUTO_PRUNE_MAX_AGE_DAYS", "30"))
RESPECT_RELEVANCE = os.getenv("AUTO_PRUNE_RESPECT_RELEVANCE", "true").lower() in {"1", "true", "yes", "on"}
GOVERNOR_URL = os.getenv("GOVERNOR_URL", "http://127.0.0.1:54323")
GOVERNOR_PROTECT_DAYS = int(os.getenv("MG_RECALL_PROTECT_DAYS", "30"))
OUTCOME_GRACE_DAYS = int(os.getenv("MG_OUTCOME_GRACE_DAYS", "7"))
PRUNE_CONFIDENCE_FLOOR = float(os.getenv("MG_PRUNE_CONFIDENCE_FLOOR", "0.15"))


def fetch_protected_ids() -> set[str]:
    """Memory ids that must not be pruned this run.

    Union of:
      - recently-recalled (MG_RECALL_PROTECT_DAYS)
      - had any outcome within MG_OUTCOME_GRACE_DAYS (loop needs time to correct)
    """
    protected: set[str] = set()
    try:
        resp = requests.get(
            f"{GOVERNOR_URL}/recall_stats",
            params={"since_days": GOVERNOR_PROTECT_DAYS},
            timeout=5,
        )
        resp.raise_for_status()
        protected.update(resp.json().get("memory_ids", []))
    except Exception:
        pass
    try:
        resp = requests.get(
            f"{GOVERNOR_URL}/outcome_stats",
            params={"grace_days": OUTCOME_GRACE_DAYS},
            timeout=5,
        )
        resp.raise_for_status()
        protected.update(resp.json().get("grace_memory_ids", []))
    except Exception:
        pass
    return protected


def fetch_disputed_low_conf_ids() -> set[str]:
    """Ids below confidence floor AND disputed — prune candidates from outcome overlay."""
    try:
        resp = requests.get(
            f"{GOVERNOR_URL}/outcome_stats",
            params={"disputed_below": PRUNE_CONFIDENCE_FLOOR},
            timeout=5,
        )
        resp.raise_for_status()
        return set(resp.json().get("disputed_below_floor", []))
    except Exception:
        return set()


def _headers() -> dict[str, str]:
    headers = {}
    if HIPPO_KEY:
        headers["X-API-Key"] = HIPPO_KEY
    return headers


def fetch_user_ids_from_sqlite(db_path: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT DISTINCT user_id FROM memories").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def fetch_memories(user_id: str) -> list[dict[str, Any]]:
    url = f"{HIPPO_URL}/memories/{user_id}?query=*"
    resp = requests.get(url, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json().get("memories", [])


def fetch_memory(mem_id: str) -> dict[str, Any] | None:
    url = f"{HIPPO_URL}/memories/{mem_id}"
    resp = requests.get(url, headers=_headers(), timeout=10)
    if resp.status_code == 200:
        try:
            return resp.json().get("memory") or resp.json()
        except Exception:
            return None
    return None


def add_memory(user_id: str, text: str, metadata: dict[str, Any]) -> None:
    url = f"{HIPPO_URL}/memories"
    payload = {"user_id": user_id, "text": text, "metadata": metadata}
    requests.post(url, json=payload, headers=_headers(), timeout=10)


def is_auto(mem: dict[str, Any]) -> bool:
    meta = mem.get("metadata") or {}
    return meta.get("auto") is True


def relevance(mem: dict[str, Any]) -> str:
    meta = mem.get("metadata") or {}
    return str(meta.get("relevance", "")).lower()


def too_old(mem: dict[str, Any], cutoff: dt.datetime) -> bool:
    ts = mem.get("metadata", {}).get("timestamp")
    if not ts:
        return False
    try:
        # expect ISO or epoch ms
        if isinstance(ts, (int, float)):
            ts_dt = dt.datetime.fromtimestamp(ts / 1000, dt.UTC)
        else:
            ts_dt = dt.datetime.fromisoformat(str(ts))
        return ts_dt < cutoff
    except Exception:
        return False


def prune_user(user_id: str, protected_ids: set[str] | None = None) -> int:
    protected_ids = protected_ids or set()
    memories = [m for m in fetch_memories(user_id) if is_auto(m)]
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=MAX_AGE_DAYS)
    # Sort by metadata timestamp if present, else leave order
    def _sort_key(m: dict[str, Any]):
        ts = m.get("metadata", {}).get("timestamp")
        if isinstance(ts, (int, float)):
            return ts
        try:
            return dt.datetime.fromisoformat(str(ts)).timestamp()
        except Exception:
            return 0

    memories.sort(key=_sort_key, reverse=True)
    to_delete = []
    seen_text: set[str] = set()
    for m in memories:
        norm_text = str(m.get("text", "")).strip().lower()
        if norm_text in seen_text:
            to_delete.append(m)
            continue
        seen_text.add(norm_text)
        rel = relevance(m)
        if RESPECT_RELEVANCE and rel == "drop":
            to_delete.append(m)
        elif too_old(m, cutoff):
            to_delete.append(m)
    # enforce cap after relevance/age
    capped = memories
    if len(capped) > MAX_PER_USER:
        capped = capped[:MAX_PER_USER]
    extra = [m for m in memories if m not in capped and m not in to_delete]
    to_delete.extend(extra)
    deleted = 0
    for mem in to_delete:
        mem_id = mem.get("id")
        if not mem_id:
            continue
        if mem_id in protected_ids:
            continue
        # If we are deleting a "keep/high" due to cap, promote once before deletion
        if relevance(mem) in {"keep", "high"}:
            original = fetch_memory(mem_id) or mem
            meta = dict(original.get("metadata") or {})
            meta.pop("auto", None)
            meta["sticky"] = True
            meta["salience"] = "high"
            add_memory(mem.get("user_id", user_id), original.get("text", ""), meta)
        url = f"{HIPPO_URL}/memories/{mem_id}"
        try:
            resp = requests.delete(url, headers=_headers(), timeout=10)
            if resp.ok:
                deleted += 1
        except Exception:
            continue
    return deleted


def main(user_ids: list[str]) -> int:
    protected = fetch_protected_ids()
    if protected:
        print(f"Protected {len(protected)} recently-active memories from prune", file=sys.stderr)
    disputed_low = fetch_disputed_low_conf_ids() - protected
    if disputed_low:
        print(f"Targeting {len(disputed_low)} disputed low-confidence memories", file=sys.stderr)
        for mem_id in disputed_low:
            try:
                url = f"{HIPPO_URL}/memories/{mem_id}"
                requests.delete(url, headers=_headers(), timeout=10)
            except Exception:
                continue
    total = len(disputed_low)
    for uid in user_ids:
        total += prune_user(uid, protected)
    return total


if __name__ == "__main__":
    users = sys.argv[1:]
    if not users and SQLITE_PATH and Path(SQLITE_PATH).exists():
        users = fetch_user_ids_from_sqlite(SQLITE_PATH)
    if not users:
        print("Usage: prune_auto_memories.py <user_id> [user_id...] or set HIPPOCAMPUS_SQLITE_PATH", file=sys.stderr)
        sys.exit(1)
    deleted = main(users)
    print(f"Deleted {deleted} auto memories")
