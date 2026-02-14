#!/usr/bin/env python3
"""
Adaptive tuning for auto memory capture.

Reads auto-memory pressure from SQLite and writes tuning hints to
var/auto_memory_tuning.json (or AUTO_TUNE_PATH).

Heuristic:
- pressure = count + (oldest_days * 0.5)
- If pressure > 300 or count > 250: tighten (min_words=6, llm_strict=true)
- If pressure < 120: loosen slightly (min_words=3, llm_strict=false)
- Else: medium (min_words=4, llm_strict=false)

This does not delete anything; prune is handled separately.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "hippocampus_memories.sqlite"
DB_PATH = Path(os.getenv("HIPPOCAMPUS_SQLITE_PATH", DEFAULT_DB))
TUNE_PATH = Path(os.getenv("AUTO_TUNE_PATH", "var/auto_memory_tuning.json"))


def load_auto_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT user_id, metadata, created_at FROM memories").fetchall()
    autos: list[sqlite3.Row] = []
    for row in rows:
        meta_raw = row["metadata"]
        try:
            meta = json.loads(meta_raw) if meta_raw else {}
        except Exception:
            meta = {}
        if meta.get("auto") is True:
            autos.append(row)
    return autos


def pressure(rows: list[sqlite3.Row]) -> tuple[int, float]:
    now = dt.datetime.now(dt.UTC)
    count = len(rows)
    ages = []
    for row in rows:
        ts = row["created_at"]
        try:
            if isinstance(ts, (int, float)):
                ts_dt = dt.datetime.fromtimestamp(ts, dt.UTC)
            else:
                ts_dt = dt.datetime.fromisoformat(str(ts))
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=dt.UTC)
        except Exception:
            ts_dt = now
        ages.append((now - ts_dt).total_seconds() / 86400)
    oldest = max(ages) if ages else 0.0
    score = count + (oldest * 0.5)
    return count, score


def tune(count: int, score: float) -> dict[str, object]:
    if score > 300 or count > 250:
        return {"min_words": 6, "llm_strict": True, "llm_enabled": True}
    if score < 120:
        return {"min_words": 3, "llm_strict": False, "llm_enabled": True}
    return {"min_words": 4, "llm_strict": False, "llm_enabled": True}


def main() -> None:
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = load_auto_rows(conn)
    finally:
        conn.close()
    count, score = pressure(rows)
    settings = tune(count, score)
    TUNE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TUNE_PATH.write_text(json.dumps(settings, indent=2))
    print(f"Auto memory tuning written to {TUNE_PATH}: {settings}")


if __name__ == "__main__":
    main()
