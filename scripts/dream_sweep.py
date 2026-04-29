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
    resolve_dreams_output_path,
    score_memories,
    write_dream_entry,
)
from memory_governor.oracle import (
    build_oracle_snapshot,
    discover_natal_from_memory,
    load_natal,
    natal_is_complete,
    natal_precision,
    save_natal,
)
from memory_governor.store import StreamLog
from memory_governor.rem import (
    build_rem_messages,
    call_haiku_reflection,
    format_dream_entry,
    gather_rem_inputs,
)
from memory_governor.schemas import ScoreThresholds
from memory_governor.store import WorkingStore


async def _ensure_natal_or_alert(user_id: str, cfg, hippo) -> None:
    """If no natal data on file, search memory for it. If still missing, log an
    alert to the stream so it surfaces in tonight's REM data block.

    Auto-saves only when discovery returns a complete date (year/month/day).
    Partial finds (e.g. time but no date) are also logged so the operator can
    fill the rest in via `sacred-brain-oracle set`.
    """
    existing = load_natal(cfg.state_dir, user_id)
    existing_prec = natal_precision(existing)
    # Skip the probe only when we already have full datetime+location.
    if existing_prec == "datetime":
        return

    try:
        found, sources = await discover_natal_from_memory(user_id, hippo)
    except Exception as exc:  # noqa: BLE001
        found, sources = {}, []
        print(f"REM: natal memory probe failed: {exc}", file=sys.stderr)

    stream = StreamLog(cfg.stream_log_path, ttl_days=cfg.stream_ttl_days)

    # Merge any new fields the probe found into whatever exists.
    merged = dict(existing or {})
    for k, v in found.items():
        merged.setdefault(k, v)
    if found:
        merged.setdefault("name", user_id)

    new_prec = natal_precision(merged)

    # Save if we improved the tier (none → date/datetime, or date → datetime).
    if new_prec != "none" and new_prec != existing_prec:
        save_natal(cfg.state_dir, user_id, merged)
        stream.append({
            "kind": "oracle.natal_recovered",
            "user_id": user_id,
            "precision": new_prec,
            "fields": sorted(found.keys()),
            "sources": sources,
            "text": (
                f"natal data auto-recovered for {user_id} from memory "
                f"(precision={new_prec})"
            ),
        })
        print(f"REM: natal recovered for {user_id} "
              f"(precision={new_prec}, new_fields={sorted(found.keys())})",
              file=sys.stderr)

    # Alert when the tier is still below "datetime" so the operator knows
    # what would sharpen tonight's chart.
    if new_prec == "datetime":
        return

    if new_prec == "none":
        kind = "oracle.natal_missing"
        missing = ["year", "month", "day", "hour", "minute", "city", "tz_str"]
        msg = (
            f"oracle: no natal date on file for {user_id}; using mundane sky. "
            f"Run `scripts/sacred-brain-oracle set {user_id} --date YYYY-MM-DD …` "
            "to enable a transit chart."
        )
    else:  # "date" — partial chart drawn; Moon/Asc/houses dropped
        kind = "oracle.natal_partial"
        wanted = ("hour", "minute", "city", "tz_str", "lat", "lng")
        missing = [k for k in wanted if k not in merged]
        msg = (
            f"oracle: partial transit chart drawn for {user_id} (date-only); "
            f"missing {', '.join(missing)}. Moon, Nodes, Ascendant, MC, and "
            f"house-cusp aspects are excluded tonight. "
            f"Run `scripts/sacred-brain-oracle set {user_id} …` with "
            "--time / --lat/--lng / --tz to upgrade."
        )

    stream.append({
        "kind": kind,
        "user_id": user_id,
        "precision": new_prec,
        "have": sorted(merged.keys()),
        "missing": missing,
        "partial_found": found,
        "text": msg,
    })
    print(f"REM: {msg}", file=sys.stderr)


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

    if args.reflect:
        inputs = gather_rem_inputs(store, cfg.stream_log_path, since_hours=24, top_k=20)
        if inputs.is_empty:
            print("REM: no inputs (empty stream + no promotions + no recalls); skipping.",
                  file=sys.stderr)
        else:
            if cfg.oracle_enabled:
                await _ensure_natal_or_alert(args.user_id, cfg, hippo)
            oracle = build_oracle_snapshot(
                args.user_id,
                cfg.state_dir,
                enabled=cfg.oracle_enabled,
                now_ts=inputs.now_ts or None,
            )
            if oracle:
                astro_mode = (oracle.get("astro") or {}).get("mode", "?")
                tarot_card = (oracle.get("tarot") or {}).get("card", "?")
                print(f"REM: oracle astro={astro_mode} tarot={tarot_card}",
                      file=sys.stderr)
            messages = build_rem_messages(inputs, oracle=oracle)
            try:
                reflection = call_haiku_reflection(
                    messages,
                    litellm_base_url=cfg.litellm_base_url,
                    litellm_api_key=cfg.litellm_api_key,
                )
            except Exception as exc:
                print(f"REM: reflection call failed: {exc}", file=sys.stderr)
                return 2
            entry = format_dream_entry(reflection, inputs, oracle=oracle)
            base = resolve_dreams_output_path()
            written = write_dream_entry(base, entry)
            print(f"REM: wrote {written}", file=sys.stderr)

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
    p.add_argument("--reflect", action="store_true",
                   help="Run REM reflection (Haiku) and write a dream entry")
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
