from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from memory_governor.clients import HippocampusClient
from memory_governor.config import GovernorConfig, load_config
from memory_governor.mem_policy import (
    build_candidate_stats,
    canonicalize_memory,
    classify_observation,
    consolidate_events,
    default_tier_for_event,
    extract_tier_and_text,
    score_candidate,
)
from memory_governor.scopes import matches_filter, scope_path as _scope_path
from memory_governor.schemas import (
    ConsolidateRequest,
    ConsolidateResponse,
    ObserveRequest,
    ObserveResponse,
    OutcomeRequest,
    OutcomeResponse,
    PromoteExplainRequest,
    PromoteExplainResponse,
    RecallRequest,
    RecallResponse,
    RememberRequest,
    RememberResponse,
)
from memory_governor.store import DurableQueue, StreamLog, WorkingStore

LOGGER = logging.getLogger("memory_governor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _keywords_from_text(text: str, min_len: int = 4) -> list[str]:
    import re

    tokens = re.findall(r"\w+", text.lower())
    return sorted({t for t in tokens if len(t) >= min_len})


def _scope_path_from_meta(meta: dict[str, Any]) -> str | None:
    """Reconstruct a scope path string from a memory's metadata dict.

    Tolerates both new-style (with parent chain) and legacy flat scope dicts.
    """
    scope_dict = meta.get("scope")
    if not isinstance(scope_dict, dict):
        return None
    parts: list[str] = []
    cur: Any = scope_dict
    seen = 0
    while isinstance(cur, dict) and cur.get("kind") and cur.get("id") is not None and seen < 16:
        parts.append(f"{cur['kind']}:{cur['id']}")
        cur = cur.get("parent")
        seen += 1
    return "/".join(parts) if parts else None


class GovernorRuntime:
    def __init__(self, cfg: GovernorConfig) -> None:
        self.cfg = cfg
        self.store = WorkingStore(cfg.db_path, ttl_hours=cfg.working_ttl_hours)
        self.stream = StreamLog(cfg.stream_log_path, ttl_days=cfg.stream_ttl_days) if cfg.stream_enable else None
        self.queue = DurableQueue(cfg.spool_path)
        self.hippo = HippocampusClient(
            hippocampus_url=cfg.hippocampus_url,
            hippocampus_api_key=cfg.hippocampus_api_key,
            rerank_enabled=cfg.rerank_enabled,
            rerank_model=cfg.rerank_model,
            rerank_max=cfg.rerank_max,
            litellm_base_url=cfg.litellm_base_url,
            litellm_api_key=cfg.litellm_api_key,
        )
        self._queue_rt: asyncio.Queue | None = None
        self._worker: asyncio.Task | None = None

    def enqueue_memory(self, payload: dict[str, Any]) -> str:
        job = self.queue.enqueue({"type": "memory", "payload": payload})
        if self._queue_rt:
            self._queue_rt.put_nowait(job)
        return job["id"]

    def enqueue_recall_hit(
        self,
        memory_id: str,
        query_hash: str | None = None,
        rerank_score: float | None = None,
    ) -> str:
        payload: dict[str, Any] = {"memory_id": memory_id}
        if query_hash:
            payload["query_hash"] = query_hash
        if rerank_score is not None:
            payload["rerank_score"] = float(rerank_score)
        job = self.queue.enqueue({"type": "recall_hit", "payload": payload})
        if self._queue_rt:
            self._queue_rt.put_nowait(job)
        return job["id"]

    def enqueue_delete(self, memory_id: str) -> str:
        job = self.queue.enqueue({"type": "delete_memory", "payload": {"memory_id": memory_id}})
        if self._queue_rt:
            self._queue_rt.put_nowait(job)
        return job["id"]

    async def _process_job(self, job: dict[str, Any]) -> bool:
        # DurableQueue wraps items in {"id", "payload", "ts"} envelope.
        # The actual item is inside job["payload"], which has {"type", "payload"}.
        inner = job.get("payload", job)
        job_type = inner.get("type")
        if job_type == "memory":
            mem_payload = inner.get("payload", {})
            memory_id = await self.hippo.post_memory(mem_payload)
            if memory_id:
                LOGGER.info("Memory written to Hippocampus: %s", memory_id)
                return True
            LOGGER.warning("Memory write to Hippocampus failed")
            return False
        if job_type == "recall_hit":
            p = inner.get("payload", {})
            mem_id = p.get("memory_id")
            if mem_id:
                self.store.bump_recall(
                    mem_id,
                    query_hash=p.get("query_hash"),
                    rerank_score=p.get("rerank_score"),
                )
            return True
        if job_type == "delete_memory":
            mem_id = inner.get("payload", {}).get("memory_id")
            if mem_id:
                ok = await self.hippo.delete_memory(mem_id)
                if ok:
                    LOGGER.info("Deleted memory via outcome-threshold: %s", mem_id)
                return ok
            return True
        LOGGER.warning("Unknown job type: %s (keys: %s)", job_type, list(job.keys()))
        return True

    async def _worker_loop(self) -> None:
        assert self._queue_rt is not None
        while True:
            job = await self._queue_rt.get()
            try:
                ok = await self._process_job(job)
                if ok:
                    self.queue.mark_done(job["id"])
                else:
                    # keep it; requeue after delay
                    await asyncio.sleep(2)
                    self._queue_rt.put_nowait(job)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.error("Worker failed: %s", exc, exc_info=True)
                await asyncio.sleep(2)
                self._queue_rt.put_nowait(job)

    async def start(self) -> None:
        self._queue_rt = asyncio.Queue()
        for job in self.queue.pending():
            self._queue_rt.put_nowait(job)
        self._worker = asyncio.create_task(self._worker_loop())
        LOGGER.info("Memory Governor worker started with %d pending jobs", len(self.queue.pending()))


cfg = load_config()
runtime = GovernorRuntime(cfg)

app = FastAPI(title="Memory Governor", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup() -> None:
    runtime.store.cleanup()
    if runtime.stream:
        runtime.stream.cleanup()
    await runtime.start()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/observe", response_model=ObserveResponse)
async def observe(payload: ObserveRequest) -> ObserveResponse:
    # Tier tagging (safe/raw) + prefix stripping
    default_tier = default_tier_for_event(payload)
    clean_text, tier = extract_tier_and_text(payload.text, default_tier)
    payload.text = clean_text
    payload.metadata = payload.metadata or {}
    payload.metadata.setdefault("tier", tier)

    added = runtime.store.add_working(payload)
    if not added:
        return ObserveResponse(
            status="ok",
            action="working",
            decision={"salience": 0.0, "kind": "ignore"},
        )
    if runtime.stream:
        runtime.stream.append(
            {
                "source": payload.source,
                "user_id": payload.user_id,
                "text": payload.text,
                "timestamp": payload.timestamp or int(time.time()),
                "scope": payload.scope.dict(),
                "metadata": payload.metadata,
            }
        )
    salience, decision_kind = classify_observation(payload)

    if decision_kind == "candidate":
        keywords = _keywords_from_text(payload.text)
        memory_payload = {
            "user_id": payload.user_id,
            "text": payload.text,
            "metadata": {
                "source": payload.source,
                "scope": payload.scope.dict(),
                "kind": "episodic",
                "salience": max(0.7, salience),
                "keywords": keywords,
            "tier": (payload.metadata or {}).get("tier", "safe"),
                "tier": (payload.metadata or {}).get("tier", "safe"),
                **(payload.metadata or {}),
            },
        }
        runtime.enqueue_memory(memory_payload)

    return ObserveResponse(
        status="ok",
        action="working",
        decision={"salience": salience, "kind": decision_kind if decision_kind != "working" else "working"},
    )


@app.post("/remember", response_model=RememberResponse)
async def remember(payload: RememberRequest) -> RememberResponse:
    canon = canonicalize_memory(payload.text)
    # Tier tagging + prefix stripping for explicit remembers
    default_tier = "safe"
    clean_text, tier = extract_tier_and_text(canon, default_tier)
    canon = clean_text
    payload.metadata = payload.metadata or {}
    payload.metadata.setdefault("tier", tier)
    keywords = _keywords_from_text(canon)
    memory_payload = {
        "user_id": payload.user_id,
        "text": canon,
        "metadata": {
            "source": payload.source,
            "scope": payload.scope.dict(),
            "kind": payload.kind,
            "salience": 1.0,
            "confidence": 0.95,
            "keywords": keywords,
            "tier": (payload.metadata or {}).get("tier", "safe"),
                "tier": (payload.metadata or {}).get("tier", "safe"),
                **(payload.metadata or {}),
        },
    }
    job_id = runtime.enqueue_memory(memory_payload)
    return RememberResponse(status="stored", memory_id=job_id)


@app.post("/outcome", response_model=OutcomeResponse)
async def outcome(payload: OutcomeRequest) -> OutcomeResponse:
    from fastapi import HTTPException

    mem = await runtime.hippo.get_memory(payload.user_id, payload.memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="memory not found")

    meta = mem.get("metadata", {}) or {}
    base_conf = meta.get("confidence")
    if base_conf is None:
        base_conf = 0.5
    try:
        base_conf = float(base_conf)
    except (TypeError, ValueError):
        base_conf = 0.5

    result = runtime.store.apply_outcome(
        memory_id=payload.memory_id,
        outcome=payload.outcome,
        base_confidence=base_conf,
        source=payload.source,
        note=payload.note,
    )

    action = "noop"
    if payload.outcome == "bad" and result["confidence_after"] < runtime.cfg.outcome_delete_threshold:
        runtime.enqueue_delete(payload.memory_id)
        action = "deleted"

    if runtime.stream:
        runtime.stream.append({
            "source": "governor:outcome",
            "user_id": payload.user_id,
            "text": f"outcome={payload.outcome} memory_id={payload.memory_id}",
            "timestamp": int(time.time()),
            "scope": {"kind": "user", "id": payload.user_id},
            "metadata": {
                "memory_id": payload.memory_id,
                "outcome": payload.outcome,
                "note": payload.note,
                "client_source": payload.source,
                "confidence_before": result["confidence_before"],
                "confidence_after": result["confidence_after"],
                "action": action,
            },
        })

    return OutcomeResponse(
        status="ok",
        memory_id=payload.memory_id,
        confidence_after=result["confidence_after"],
        action=action,
    )


@app.post("/recall", response_model=RecallResponse)
async def recall(payload: RecallRequest) -> RecallResponse:
    memories = await runtime.hippo.query_memories(
        user_id=payload.user_id,
        query=payload.query,
        limit=payload.k,
    )
    filter_scope_path: str | None = None
    if payload.filters.scope is not None:
        filter_scope_path = _scope_path(payload.filters.scope)

    all_ids = [m.get("id") for m in memories if m.get("id")]
    outcomes = runtime.store.get_outcomes_bulk(all_ids) if all_ids else {}

    filtered = []
    for mem in memories:
        meta = mem.get("metadata", {}) or {}
        kind = meta.get("kind")
        tier = meta.get("tier") or "safe"
        if payload.filters.tiers and tier not in payload.filters.tiers:
            continue
        if payload.filters.kinds and kind and kind not in payload.filters.kinds:
            continue
        mem_id = mem.get("id") or meta.get("memory_id")
        outcome_row = outcomes.get(mem_id or "", {})
        if outcome_row.get("stale") and not payload.filters.include_stale:
            continue

        base_confidence = meta.get("confidence")
        effective_confidence = base_confidence
        if base_confidence is not None:
            effective_confidence = max(0.0, min(0.99, float(base_confidence) + outcome_row.get("confidence_delta", 0.0)))
        if payload.filters.min_confidence is not None and effective_confidence is not None:
            if effective_confidence < payload.filters.min_confidence:
                continue
        stored_scope_path = _scope_path_from_meta(meta)
        if filter_scope_path is not None:
            if stored_scope_path is None or not matches_filter(stored_scope_path, filter_scope_path):
                continue
        ts = meta.get("timestamp") or meta.get("ts")
        filtered.append(
            {
                "memory_id": mem_id,
                "text": mem.get("text") or mem.get("memory") or "",
                "kind": kind,
                "tier": tier,
                "confidence": effective_confidence,
                "timestamp": ts,
                "scope_path": stored_scope_path,
                "disputed": bool(outcome_row.get("disputed")),
                "last_outcome": outcome_row.get("last_outcome"),
                "provenance": {
                    "source": meta.get("source"),
                    "event_id": meta.get("event_id"),
                    "room_id": meta.get("room_id") or meta.get("scope", {}).get("id"),
                },
            }
        )

    memory_ids = [item["memory_id"] for item in filtered if item.get("memory_id")]
    recall_counts = runtime.store.get_recall_counts(memory_ids) if memory_ids else {}

    now = time.time()
    def _score(item: dict[str, Any]) -> float:
        conf = item.get("confidence") or 0.5
        ts_val = item.get("timestamp")
        if ts_val:
            age_days = max(0.0, (now - float(ts_val)) / 86400.0)
            recency = max(0.0, 1.0 - age_days / 30.0)
        else:
            recency = 0.3
        mid = item.get("memory_id")
        rc = recall_counts.get(mid, 0) if mid else 0
        recall_boost = min(1.0, rc / 10.0)
        outcome_bonus = 1.0 if item.get("last_outcome") == "good" else 0.0
        exact_bonus = 0.05 if (
            filter_scope_path is not None and item.get("scope_path") == filter_scope_path
        ) else 0.0
        return (
            conf * 0.6
            + recency * 0.2
            + recall_boost * 0.1
            + outcome_bonus * 0.1
            + exact_bonus
        )

    scored = [(item, _score(item)) for item in filtered]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    top = scored[: payload.k]

    query_hash = (
        hashlib.sha1(payload.query.strip().lower().encode("utf-8")).hexdigest()[:16]
        if payload.query.strip()
        else None
    )
    for item, item_score in top:
        mid = item.get("memory_id")
        if mid:
            runtime.enqueue_recall_hit(mid, query_hash=query_hash, rerank_score=item_score)

    results = [
        {k: v for k, v in item.items() if k not in ("memory_id", "scope_path", "last_outcome")}
        for item, _s in top
    ]
    return RecallResponse(results=results)


@app.get("/outcome_stats")
async def outcome_stats(
    grace_days: int | None = None,
    disputed_below: float | None = None,
) -> dict[str, Any]:
    """Introspection for the prune script.

    - `grace_days` → memory_ids with any outcome in the last N days (protected)
    - `disputed_below` → disputed ids whose effective confidence delta pushes them below the floor
    """
    out: dict[str, Any] = {}
    if grace_days is not None:
        since_ts = int(time.time() - grace_days * 86400)
        out["grace_memory_ids"] = sorted(runtime.store.recent_outcome_ids(since_ts))
    if disputed_below is not None:
        # We only have confidence_delta here, not the base. Approximation: any
        # memory whose delta alone is ≤ (disputed_below - 0.5) from a nominal 0.5
        # base. Precise computation would require fetching each memory; the
        # Governor doesn't do that on a hot path. Return *candidate* ids; the
        # actual deletion still runs via the /outcome threshold path.
        import sqlite3 as _sq
        with _sq.connect(runtime.cfg.db_path) as conn:
            rows = conn.execute(
                "SELECT memory_id FROM memory_outcomes WHERE disputed=1 AND confidence_delta < ?",
                (disputed_below - 0.5,),
            ).fetchall()
        out["disputed_below_floor"] = [r[0] for r in rows]
    return out


@app.get("/scopes")
async def list_scopes(prefix: str | None = None) -> dict[str, Any]:
    scopes = runtime.store.distinct_scopes(prefix=prefix, limit=200)
    return {"scopes": scopes}


@app.get("/recall_stats/{memory_id}")
async def recall_stats(memory_id: str) -> dict[str, Any]:
    stats = runtime.store.get_recall_stats(memory_id)
    if not stats:
        return {"memory_id": memory_id, "recall_count": 0, "last_recalled_at": None}
    return stats


@app.get("/recall_stats")
async def recall_stats_protected(since_days: int | None = None) -> dict[str, Any]:
    days = since_days if since_days is not None else runtime.cfg.recall_protect_days
    since_ts = int(time.time() - days * 86400)
    ids = runtime.store.recently_recalled_ids(since_ts)
    return {"since_days": days, "since_ts": since_ts, "memory_ids": ids}


@app.post("/promote-explain", response_model=PromoteExplainResponse)
async def promote_explain(payload: PromoteExplainRequest) -> PromoteExplainResponse:
    """Explain why a memory would or would not promote under current scoring.

    Reads live state from Hippocampus + recall_stats and runs score_candidate.
    Read-only — does not mutate anything.
    """
    from fastapi import HTTPException

    mem = await runtime.hippo.get_memory(payload.user_id, payload.memory_id)
    if not mem:
        raise HTTPException(status_code=404, detail=f"memory_id {payload.memory_id} not found")

    row = runtime.store.get_recall_stats(payload.memory_id)
    stats = build_candidate_stats(row, mem)
    result = score_candidate(stats, payload.thresholds)

    meta = mem.get("metadata") or {}
    return PromoteExplainResponse(
        memory_id=payload.memory_id,
        text=mem.get("text") or mem.get("memory") or "",
        stats=stats,
        result=result,
        metadata=meta,
    )


@app.post("/consolidate", response_model=ConsolidateResponse)
async def consolidate(payload: ConsolidateRequest) -> ConsolidateResponse:
    events = runtime.store.recent_for_scope(payload.scope, limit=payload.max_items * 3)
    if not events:
        return ConsolidateResponse(status="ok", written={"episodic": 0, "semantic": 0, "procedural": 0}, skipped=0)
    grouped = consolidate_events(events, mode=payload.mode)
    written_counts = {"episodic": 0, "semantic": 0, "procedural": 0}
    skipped = 0
    for kind, items in grouped.items():
        for item in items[: payload.max_items]:
            mem_payload = {
                "user_id": events[0].get("user_id"),
                "text": item["text"],
                "metadata": {
                    "source": item["provenance"].get("source"),
                    "kind": item.get("kind", kind),
                    "confidence": item.get("confidence", 0.5),
                    "tier": item.get("tier") or item.get("provenance", {}).get("tier") or "safe",
                    **{k: v for k, v in item.get("provenance", {}).items() if v is not None},
                },
            }
            runtime.enqueue_memory(mem_payload)
            written_counts[kind] += 1
        if len(items) > payload.max_items:
            skipped += len(items) - payload.max_items
    newest_ts = max(evt.get("timestamp", 0) for evt in events)
    runtime.store.mark_consolidated(payload.scope, newest_ts)
    return ConsolidateResponse(
        status="ok",
        written=written_counts,  # type: ignore[arg-type]
        skipped=skipped,
    )


def run() -> None:
    import uvicorn

    uvicorn.run(
        "memory_governor.app:app",
        host=cfg.bind_host,
        port=cfg.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
