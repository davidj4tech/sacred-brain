#!/usr/bin/env python3
"""Dreaming sweep runner (Task 009).

Usage:
    python scripts/dream_sweep.py --user-id sam --dry-run
    python scripts/dream_sweep.py --user-id sam --dry-run --json
    python scripts/dream_sweep.py --user-id sam --dry-run --limit 100

Currently implements the dry-run path only: fetch all memories for a user,
score them, print the table. Promote + reflect steps land in follow-up
commits.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from memory_governor.clients import HippocampusClient
from memory_governor.config import load_config
from memory_governor.dream import (
    format_score_table,
    record_passing_promotions,
    score_memories,
)
from memory_governor.schemas import ScoreThresholds
from memory_governor.store import WorkingStore


async def _run(args: argparse.Namespace) -> int:
    cfg = load_config()
    store = WorkingStore(cfg.db_path, ttl_hours=cfg.working_ttl_hours)
    hippo = HippocampusClient(
        hippocampus_url=cfg.hippocampus_url,
        hippocampus_api_key=cfg.hippocampus_api_key,
    )

    memories = await hippo.list_memories(args.user_id, limit=args.limit)
    if not memories:
        print(f"No memories found for user_id={args.user_id}", file=sys.stderr)
        return 1

    thresholds = ScoreThresholds(
        min_score=args.min_score,
        min_recall_count=args.min_recall_count,
        min_unique_queries=args.min_unique_queries,
    )

    scored = score_memories(
        memories,
        recall_stats_lookup=store.get_recall_stats,
        thresholds=thresholds,
    )

    if args.apply:
        recorded = record_passing_promotions(scored, store.record_dream_promotion)
        print(f"Recorded {recorded} dream_promotions row(s).", file=sys.stderr)

    if args.json:
        payload = [
            {
                "memory_id": s.memory_id,
                "text": s.text,
                "score": s.result.score,
                "passed": s.result.passed,
                "reasons": s.result.reasons,
                "signals": s.result.signals.model_dump(),
                "weighted": s.result.weighted.model_dump(),
                "stats": s.stats.model_dump(),
            }
            for s in scored
        ]
        print(json.dumps(payload, indent=2))
    else:
        print(format_score_table(scored))

    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Dreaming sweep runner")
    p.add_argument("--user-id", required=True, help="Hippocampus user_id to sweep")
    p.add_argument("--apply", action="store_true",
                   help="Write dream_promotions rows for passing memories (default: dry-run)")
    p.add_argument("--limit", type=int, default=500,
                   help="Max memories to fetch from Hippocampus (default 500)")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of table")
    p.add_argument("--min-score", type=float, default=0.35)
    p.add_argument("--min-recall-count", type=int, default=2)
    p.add_argument("--min-unique-queries", type=int, default=2)
    args = p.parse_args()

    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
