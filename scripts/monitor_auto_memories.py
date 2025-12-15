#!/usr/bin/env python3
"""Report auto-memory pressure per user."""
from __future__ import annotations

import os
import sqlite3
from collections import defaultdict

DB_PATH = os.getenv("HIPPOCAMPUS_SQLITE_PATH", "data/hippocampus_memories.sqlite")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT user_id, metadata, COUNT(*) as cnt, MIN(created_at), MAX(created_at) "
            "FROM memories WHERE metadata LIKE '%\"auto\": true%' GROUP BY user_id"
        ).fetchall()
        if not rows:
            print("No auto memories found")
            return
        for user_id, meta, cnt, oldest, newest in rows:
            print(f"user={user_id} auto_count={cnt} oldest={oldest} newest={newest}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
