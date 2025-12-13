from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

LOGGER = logging.getLogger(__name__)


class HippocampusClient:
    def __init__(
        self,
        ingest_url: str,
        hippocampus_url: str,
        hippocampus_api_key: Optional[str] = None,
        timeout: float = 5.0,
    ) -> None:
        self.ingest_url = ingest_url
        self.hippo_url = hippocampus_url.rstrip("/")
        self.hippo_key = hippocampus_api_key
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.hippo_key:
            headers["X-API-Key"] = self.hippo_key
        return headers

    async def post_memory(self, payload: Dict[str, Any]) -> Optional[str]:
        """Prefer ingest; fall back to Hippocampus direct."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(self.ingest_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("memory_id") or data.get("id")
            except Exception as exc:
                LOGGER.warning("Ingest write failed, falling back to Hippocampus: %s", exc)
                try:
                    resp = await client.post(
                        f"{self.hippo_url}/memories", json=payload, headers=self._headers()
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return data.get("memory", {}).get("id") or data.get("id")
                except Exception as final_exc:
                    LOGGER.error("Hippocampus write failed: %s", final_exc)
                    return None

    async def query_memories(
        self, user_id: str, query: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"query": query}
        if limit:
            params["limit"] = limit
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(
                    f"{self.hippo_url}/memories/{user_id}",
                    params=params,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("memories", [])
            except Exception as exc:
                LOGGER.error("Hippocampus query failed: %s", exc)
                results = []

            # Fallback: if empty or no substring matches, try without query to list recent items and filter locally
            if not results:
                try:
                    resp2 = await client.get(
                        f"{self.hippo_url}/memories/{user_id}",
                        params={"limit": limit or 10},
                        headers=self._headers(),
                    )
                    resp2.raise_for_status()
                    data2 = resp2.json()
                    results = data2.get("memories", [])
                except Exception as exc2:
                    LOGGER.error("Hippocampus fallback list failed: %s", exc2)
                    return []

        # Fallback substring filter (case-insensitive) and simple recency weighting if timestamps present
        q = query.lower()
        matched: List[Dict[str, Any]] = []
        now = None
        for mem in results:
            text = (mem.get("text") or mem.get("memory") or "").lower()
            if q in text:
                matched.append(mem)

        if matched:
            def _score(mem: Dict[str, Any]) -> float:
                meta = mem.get("metadata", {}) or {}
                ts = meta.get("timestamp")
                try:
                    ts_val = float(ts)
                    nonlocal now
                    if now is None:
                        import time as _t
                        now = _t.time()
                    age_days = max(0.0, (now - ts_val) / 86400.0)
                    recency = max(0.0, 1.0 - age_days / 30.0)
                except Exception:
                    recency = 0.3
                return recency
            matched = sorted(matched, key=_score, reverse=True)
            return matched[:limit] if limit else matched

        return results[: (limit or len(results))]
