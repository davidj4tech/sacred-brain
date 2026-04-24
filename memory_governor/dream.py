"""Dreaming sweep — scored promotion pipeline (Task 009).

This module is the pure, testable core of the nightly dreaming sweep. IO
(Hippocampus fetch, stream_log writes, reflection LLM call, filesystem
writes) lives in the runner script. Everything here is deterministic given
its inputs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable

from memory_governor.mem_policy import build_candidate_stats, score_candidate
from memory_governor.schemas import CandidateStats, ScoreResult, ScoreThresholds


@dataclass(frozen=True)
class ScoredMemory:
    memory_id: str
    text: str
    stats: CandidateStats
    result: ScoreResult
    memory: dict


RecallStatsLookup = Callable[[str], dict | None]


def score_memories(
    memories: Iterable[dict],
    recall_stats_lookup: RecallStatsLookup,
    now_ts: float | None = None,
    thresholds: ScoreThresholds | None = None,
) -> list[ScoredMemory]:
    """Score every memory, return list sorted by score descending.

    Pure. `recall_stats_lookup(memory_id)` returns the dict from
    WorkingStore.get_recall_stats() or None. `memories` is an iterable of
    Hippocampus memory dicts.
    """
    now = now_ts if now_ts is not None else time.time()
    thresholds = thresholds or ScoreThresholds()

    scored: list[ScoredMemory] = []
    for mem in memories:
        mem_id = mem.get("id") or (mem.get("metadata") or {}).get("memory_id")
        if not mem_id:
            continue
        row = recall_stats_lookup(mem_id)
        stats = build_candidate_stats(row, mem, now_ts=now)
        result = score_candidate(stats, thresholds)
        scored.append(
            ScoredMemory(
                memory_id=mem_id,
                text=mem.get("text") or mem.get("memory") or "",
                stats=stats,
                result=result,
                memory=mem,
            )
        )

    scored.sort(key=lambda s: s.result.score, reverse=True)
    return scored


def format_score_table(scored: list[ScoredMemory], text_width: int = 60) -> str:
    """Render a human-readable score table. Used by dream_sweep.py --dry-run."""
    if not scored:
        return "(no memories scored)\n"

    header = f"{'score':>6}  {'pass':>5}  {'rc':>3}  {'dq':>3}  {'dd':>3}  {'age_d':>5}  text\n"
    sep = "-" * (len(header) - 1) + "\n"
    lines = [header, sep]
    for s in scored:
        snippet = s.text.replace("\n", " ").strip()
        if len(snippet) > text_width:
            snippet = snippet[: text_width - 1] + "…"
        lines.append(
            f"{s.result.score:6.3f}  "
            f"{'✓' if s.result.passed else '✗':>5}  "
            f"{s.stats.recall_count:3d}  "
            f"{s.stats.distinct_queries:3d}  "
            f"{s.stats.distinct_days:3d}  "
            f"{s.stats.age_days:5.1f}  "
            f"{snippet}\n"
        )
    passed = sum(1 for s in scored if s.result.passed)
    lines.append(sep)
    lines.append(f"{passed} / {len(scored)} would promote\n")
    return "".join(lines)
