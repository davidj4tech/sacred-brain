#!/usr/bin/env python3
"""Memory Governor test harness.

Creates a small set of synthetic observations for a scope (default user:sam),
waits briefly for the async durable queue to flush to Hippocampus, then runs recall.

Env:
  MG_URL=http://127.0.0.1:54323
  MG_INCLUDE_ARCHIVE=0|1  (default 0)
  MG_WAIT_SECONDS=3

Usage:
  python3 scripts/memory_governor_test_harness.py run
"""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any, Dict, List, Tuple

import requests

MG_URL = (os.environ.get("MG_URL") or "http://127.0.0.1:54323").rstrip("/")
WAIT_SECONDS = float(os.environ.get("MG_WAIT_SECONDS") or "3")


def post(path: str, payload: dict) -> dict:
    r = requests.post(f"{MG_URL}{path}", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def observe(scope: dict, text: str, event_id: str, source: str = "harness") -> dict:
    return post(
        "/observe",
        {
            "source": source,
            "user_id": scope.get("id"),
            "text": text,
            "timestamp": int(time.time() * 1000),
            "scope": scope,
            "metadata": {"event_id": event_id},
        },
    )


def consolidate(scope: dict, mode: str = "all") -> dict:
    return post("/consolidate", {"scope": scope, "mode": mode})


def recall(scope: dict, query: str, kinds: List[str], k: int = 5) -> dict:
    return post(
        "/recall",
        {
            "user_id": scope.get("id"),
            "query": query,
            "k": k,
            "filters": {
                "kinds": kinds,
                "since_days": 365,
                "min_confidence": 0.1,
                "scope": scope,
            },
        },
    )


def top_texts(resp: dict) -> List[str]:
    include_archive = os.environ.get("MG_INCLUDE_ARCHIVE", "0") == "1"
    items = resp.get("results") or resp.get("memories") or []
    out: List[str] = []
    for it in items:
        t = (it.get("text") or "").strip().replace("\n", " ")
        if not t:
            continue
        if (not include_archive) and t.startswith("ChatGPT export:"):
            continue
        out.append(t[:140])
        if len(out) >= 5:
            break
    return out


def run(scope: dict) -> int:
    cases: List[Tuple[str, str]] = [
        ("pihole", "Pi-hole admin now works via Tailscale on port 8082 and HTTPS on 8443."),
        ("tts", "Sam has keyword triggers: openai voice vs qwen voice; default uses Piper."),
        ("dns", "Tailscale Split DNS for ryer.org can break matrix; prefer hostname override."),
        ("repo", "Sam runtime is in /opt/sam/runtime and memory repo in /opt/sam/memory."),
        ("cron", "Nightly jobs run: digest 03:20, sync-all 03:25, consolidate 03:45."),
    ]

    print("== Observe (inject synthetic events) ==")
    for key, text in cases:
        observe(scope, text, event_id=f"harness-{key}-{int(time.time())}")
        time.sleep(0.05)
    print(f"Injected {len(cases)} events into scope {scope}.")

    print("\n== Consolidate ==")
    c = consolidate(scope)
    print(json.dumps(c, indent=2)[:600])

    print(f"\n== Wait {WAIT_SECONDS}s for durable queue to flush ==")
    time.sleep(WAIT_SECONDS)

    print("\n== Recall smoke tests ==")
    queries = [
        ("pihole", ["semantic", "procedural", "episodic"]),
        ("openai voice", ["semantic", "procedural"]),
        ("Split DNS", ["semantic", "procedural"]),
        ("/opt/sam", ["semantic", "procedural"]),
        ("03:45", ["procedural", "semantic"]),
    ]

    for q, kinds in queries:
        r = recall(scope, q, kinds=kinds, k=8)
        tops = top_texts(r)
        print(f"\nQuery: {q} | kinds={kinds}")
        if tops:
            for t in tops:
                print(f"- {t}")
        else:
            print("- (no results)")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    _ = sub.add_parser("run")
    _args = ap.parse_args()

    scope = {"kind": "user", "id": "sam"}
    return run(scope)


if __name__ == "__main__":
    raise SystemExit(main())
