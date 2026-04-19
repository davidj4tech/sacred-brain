#!/usr/bin/env python3
"""Sync Claude Code auto-memory files into the Governor.

Walks ~/.claude/projects/*/memory/*.md, parses YAML frontmatter, and POSTs
each file to /remember with scope project:<dirname>/user:<GOVERNOR_USER_ID>.

Idempotent via a local ledger: only re-POSTs when (frontmatter+body) hash
changes. `--force` re-sends everything; `--dry-run` prints actions without
hitting the network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("sync_claude_memory.py: pyyaml not installed; run `pip install pyyaml`", file=sys.stderr)
    sys.exit(2)

try:
    import requests
except ImportError:
    print("sync_claude_memory.py: requests not installed", file=sys.stderr)
    sys.exit(2)


TYPE_MAP: dict[str, tuple[str, float]] = {
    "user":      ("semantic",   0.80),
    "feedback":  ("procedural", 0.85),
    "project":   ("episodic",   0.70),
    "reference": ("semantic",   0.75),
}
# `type: user` and `type: reference` also get posted at bare user:<id> scope
# so they surface in non-project sessions.
PERSONA_WIDE_TYPES = {"user", "reference"}


@dataclass
class ParsedMemory:
    path: Path
    project_slug: str
    type_: str
    name: str
    description: str
    body: str
    content_hash: str


def parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---\n"):
        return {}, raw
    try:
        _, fm, body = raw.split("---\n", 2)
    except ValueError:
        return {}, raw
    try:
        meta = yaml.safe_load(fm) or {}
    except yaml.YAMLError:
        return {}, raw
    if not isinstance(meta, dict):
        return {}, raw
    return meta, body.lstrip("\n")


def walk_memories(root: Path) -> list[ParsedMemory]:
    out: list[ParsedMemory] = []
    for md in root.glob("*/memory/*.md"):
        # Skip the MEMORY.md index
        if md.name == "MEMORY.md":
            continue
        raw = md.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(raw)
        type_ = str(meta.get("type") or "project")
        if type_ not in TYPE_MAP:
            # unknown type — default to project/episodic
            type_ = "project"
        name = str(meta.get("name") or md.stem)
        desc = str(meta.get("description") or "")
        content_hash = hashlib.sha256((json.dumps(meta, sort_keys=True) + "\n" + body).encode()).hexdigest()
        project_slug = md.parent.parent.name
        out.append(ParsedMemory(
            path=md,
            project_slug=project_slug,
            type_=type_,
            name=name,
            description=desc,
            body=body.strip(),
            content_hash=content_hash,
        ))
    return out


def load_ledger(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def save_ledger(path: Path, ledger: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True))


def build_scope(project_slug: str, user_id: str, wide: bool = False) -> dict[str, Any]:
    if wide:
        return {"kind": "user", "id": user_id, "parent": None}
    return {
        "kind": "project", "id": project_slug,
        "parent": {"kind": "user", "id": user_id, "parent": None},
    }


def post_remember(
    governor_url: str, api_key: str | None, mem: ParsedMemory, user_id: str,
    scope: dict[str, Any], dry_run: bool,
) -> bool:
    kind, conf = TYPE_MAP[mem.type_]
    text = f"{mem.description}\n\n{mem.body}".strip() if mem.description else mem.body
    payload = {
        "source": "claude-code:sync",
        "user_id": user_id,
        "text": text,
        "kind": kind,
        "scope": scope,
        "metadata": {
            "confidence": conf,
            "origin": "claude-code",
            "claude_type": mem.type_,
            "path": str(mem.path),
            "name": mem.name,
        },
    }
    if dry_run:
        print(f"[DRY] {mem.path} → kind={kind} conf={conf} scope={scope['kind']}:{scope['id']}")
        return True
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    try:
        r = requests.post(f"{governor_url}/remember", json=payload, headers=headers, timeout=5)
        r.raise_for_status()
        return True
    except Exception as exc:
        print(f"[ERR] {mem.path}: {exc}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path.home() / ".claude" / "projects"))
    ap.add_argument("--ledger", default=str(Path.home() / ".cache" / "sacred-brain" / "claude-sync-ledger.json"))
    ap.add_argument("--user-id", default=os.environ.get("GOVERNOR_USER_ID", "sam"))
    ap.add_argument("--governor-url", default=os.environ.get("GOVERNOR_URL", "http://127.0.0.1:54323"))
    ap.add_argument("--api-key", default=os.environ.get("GOVERNOR_API_KEY"))
    ap.add_argument("--force", action="store_true", help="re-sync every file")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--watch", action="store_true", help="keep running, sync on edit (requires inotifywait)")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"root not found: {root}", file=sys.stderr)
        return 1

    ledger_path = Path(args.ledger)

    def sync_once() -> int:
        ledger = load_ledger(ledger_path)
        memories = walk_memories(root)
        changed = 0
        for mem in memories:
            key = str(mem.path)
            if not args.force and ledger.get(key) == mem.content_hash:
                continue
            scope = build_scope(mem.project_slug, args.user_id, wide=False)
            ok = post_remember(args.governor_url, args.api_key, mem, args.user_id, scope, args.dry_run)
            if ok and mem.type_ in PERSONA_WIDE_TYPES:
                wide = build_scope(mem.project_slug, args.user_id, wide=True)
                post_remember(args.governor_url, args.api_key, mem, args.user_id, wide, args.dry_run)
            if ok:
                ledger[key] = mem.content_hash
                changed += 1
        if not args.dry_run:
            save_ledger(ledger_path, ledger)
        print(f"synced {changed}/{len(memories)} memories", file=sys.stderr)
        return changed

    if not args.watch:
        sync_once()
        return 0

    import shutil, subprocess
    if not shutil.which("inotifywait"):
        print("--watch requires inotifywait; running once and exiting", file=sys.stderr)
        sync_once()
        return 0
    sync_once()
    # Watch for changes under root; any *.md change in a memory/ subdir triggers a sync.
    proc = subprocess.Popen(
        ["inotifywait", "-m", "-r", "-e", "modify,close_write,move,create", "--format", "%w%f", str(root)],
        stdout=subprocess.PIPE, text=True,
    )
    assert proc.stdout
    for line in proc.stdout:
        p = line.strip()
        if "/memory/" in p and p.endswith(".md"):
            sync_once()
    return 0


if __name__ == "__main__":
    sys.exit(main())
