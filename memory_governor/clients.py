from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Iterable, Union

import httpx

LOGGER = logging.getLogger(__name__)


class HippocampusClient:
    def __init__(
        self,
        ingest_url: str,
        hippocampus_url: str,
        hippocampus_api_key: Optional[str] = None,
        timeout: float = 5.0,
        rerank_enabled: bool = False,
        rerank_model: str = "gpt-4o-mini",
        rerank_max: int = 10,
        litellm_base_url: Optional[str] = None,
        litellm_api_key: Optional[str] = None,
    ) -> None:
        self.ingest_url = ingest_url
        self.hippo_url = hippocampus_url.rstrip("/")
        self.hippo_key = hippocampus_api_key
        self.timeout = timeout
        self.rerank_enabled = rerank_enabled
        self.rerank_model = rerank_model
        self.rerank_max = rerank_max
        self.litellm_base_url = litellm_base_url
        self.litellm_api_key = litellm_api_key

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.hippo_key:
            headers["X-API-Key"] = self.hippo_key
        return headers

    async def _rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not (self.rerank_enabled and self.litellm_base_url and self.rerank_model and candidates):
            return candidates
        import json as _json

        prompt = (
            "Reorder the following memories by relevance to the query. "
            "Return JSON array of the memory objects, unchanged, just reordered.\n"
            f"Query: {query}\n"
            f"Memories: {_json.dumps(candidates[: self.rerank_max], ensure_ascii=False)}"
        )
        payload = {
            "model": self.rerank_model,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {"Content-Type": "application/json"}
        if self.litellm_api_key:
            headers["Authorization"] = f"Bearer {self.litellm_api_key}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.litellm_base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = _json.loads(content)
                if isinstance(parsed, list):
                    return parsed
        except Exception as exc:
            LOGGER.warning("Rerank failed, using original order: %s", exc)
        return candidates

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
                        params={"limit": limit or 50},
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
        import re

        tokens = [tok for tok in re.findall(r"\w+", q) if tok]
        for mem in results:
            text = (mem.get("text") or mem.get("memory") or "").lower()
            keywords = (mem.get("metadata", {}) or {}).get("keywords") or []
            kw_lower = [str(k).lower() for k in keywords]
            text_hits = q in text
            kw_hits = q in " ".join(kw_lower)
            if text_hits or kw_hits:
                matched.append(mem)
                continue
            # all tokens must appear (AND)
            if tokens and all(tok in text or tok in kw_lower for tok in tokens):
                matched.append(mem)
                continue
        # If no AND match, fall back to OR matching
        if not matched and tokens:
            for mem in results:
                text = (mem.get("text") or mem.get("memory") or "").lower()
                keywords = (mem.get("metadata", {}) or {}).get("keywords") or []
                kw_lower = [str(k).lower() for k in keywords]
                if any(tok in text or tok in kw_lower for tok in tokens):
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
