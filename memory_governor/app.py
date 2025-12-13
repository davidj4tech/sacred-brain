from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from memory_governor.clients import HippocampusClient
from memory_governor.config import GovernorConfig, load_config
from memory_governor.mem_policy import canonicalize_memory, classify_observation, consolidate_events
from memory_governor.schemas import (
    ConsolidateRequest,
    ConsolidateResponse,
    ObserveRequest,
    ObserveResponse,
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


class GovernorRuntime:
    def __init__(self, cfg: GovernorConfig) -> None:
        self.cfg = cfg
        self.store = WorkingStore(cfg.db_path, ttl_hours=cfg.working_ttl_hours)
        self.stream = StreamLog(cfg.stream_log_path, ttl_days=cfg.stream_ttl_days) if cfg.stream_enable else None
        self.queue = DurableQueue(cfg.spool_path)
        self.hippo = HippocampusClient(
            ingest_url=cfg.ingest_url,
            hippocampus_url=cfg.hippocampus_url,
            hippocampus_api_key=cfg.hippocampus_api_key,
        )
        self._queue_rt: Optional[asyncio.Queue] = None
        self._worker: Optional[asyncio.Task] = None

    def enqueue_memory(self, payload: Dict[str, Any]) -> str:
        job = self.queue.enqueue({"type": "memory", "payload": payload})
        if self._queue_rt:
            self._queue_rt.put_nowait(job)
        return job["id"]

    async def _process_job(self, job: Dict[str, Any]) -> bool:
        if job.get("type") == "memory":
            mem_payload = job.get("payload", {})
            memory_id = await self.hippo.post_memory(mem_payload)
            if memory_id:
                return True
            return False
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
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/observe", response_model=ObserveResponse)
async def observe(payload: ObserveRequest) -> ObserveResponse:
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
            **(payload.metadata or {}),
        },
    }
    job_id = runtime.enqueue_memory(memory_payload)
    return RememberResponse(status="stored", memory_id=job_id)


@app.post("/recall", response_model=RecallResponse)
async def recall(payload: RecallRequest) -> RecallResponse:
    memories = await runtime.hippo.query_memories(
        user_id=payload.user_id,
        query=payload.query,
        limit=payload.k,
    )
    filtered = []
    for mem in memories:
        meta = mem.get("metadata", {}) or {}
        kind = meta.get("kind")
        if payload.filters.kinds and kind and kind not in payload.filters.kinds:
            continue
        confidence = meta.get("confidence")
        if payload.filters.min_confidence is not None and confidence is not None:
            if confidence < payload.filters.min_confidence:
                continue
        ts = meta.get("timestamp") or meta.get("ts")
        filtered.append(
            {
                "text": mem.get("text") or mem.get("memory") or "",
                "kind": kind,
                "confidence": confidence,
                "timestamp": ts,
                "provenance": {
                    "source": meta.get("source"),
                    "event_id": meta.get("event_id"),
                    "room_id": meta.get("room_id") or meta.get("scope", {}).get("id"),
                },
            }
        )
    # Simple rerank: combine confidence and recency
    now = time.time()
    def _score(item: Dict[str, Any]) -> float:
        conf = item.get("confidence") or 0.5
        ts_val = item.get("timestamp")
        if ts_val:
            age_days = max(0.0, (now - float(ts_val)) / 86400.0)
            recency = max(0.0, 1.0 - age_days / 30.0)  # linear decay over ~30 days
        else:
            recency = 0.3
        return conf * 0.7 + recency * 0.3

    ranked = sorted(filtered, key=_score, reverse=True)
    # If nothing found, return empty (or could return working data in future)
    return RecallResponse(results=ranked[: payload.k])


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
