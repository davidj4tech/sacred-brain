#!/usr/bin/env python3
"""
Synchronise Mem0 memories with Org/Denote files for org-roam access.

Export:
    python scripts/mem0_org_sync.py export [--dir data/memories-denote] [--user alice]

Import (Org/Denote -> Mem0):
    python scripts/mem0_org_sync.py import [--dir data/memories-denote] [--user alice]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import textwrap
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from brain.hippocampus.config import HippocampusSettings, load_settings
from brain.hippocampus.mem0_adapter import Mem0Adapter
from brain.hippocampus.models import ExperienceCreate


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Mem0 memories with Org/Denote notes.")
    sub = parser.add_subparsers(dest="command", required=True)

    export_p = sub.add_parser("export", help="Export Mem0 memories to Org/Denote files.")
    export_p.add_argument("--dir", dest="notes_dir", default=None, help="Target notes directory.")
    export_p.add_argument("--user", dest="user_id", default=None, help="Filter memories to a user_id.")
    export_p.add_argument("--limit", dest="limit", type=int, default=None, help="Limit number of memories.")

    import_p = sub.add_parser("import", help="Import Org/Denote notes into Mem0.")
    import_p.add_argument("--dir", dest="notes_dir", default=None, help="Source notes directory.")
    import_p.add_argument("--user", dest="user_id", default=None, help="Default user_id for new notes.")

    args = parser.parse_args()
    settings = load_settings()
    adapter = _build_adapter(settings)
    notes_dir = Path(args.notes_dir or settings.notes.notes_dir).expanduser()
    notes_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "export":
        export_memories(adapter, settings, notes_dir, user_id=args.user_id, limit=args.limit)
    elif args.command == "import":
        import_notes(adapter, settings, notes_dir, default_user=args.user_id)


def _build_adapter(settings: HippocampusSettings) -> Mem0Adapter:
    return Mem0Adapter(
        enabled=settings.mem0.enabled,
        api_key=settings.mem0.api_key,
        backend=settings.mem0.backend,
        backend_url=settings.mem0.backend_url,
        summary_max_length=settings.mem0.summary_max_length,
        default_query_limit=settings.mem0.query_limit,
        persistence_path=settings.mem0.persistence_path,
    )


def export_memories(
    adapter: Mem0Adapter,
    settings: HippocampusSettings,
    notes_dir: Path,
    user_id: Optional[str],
    limit: Optional[int],
) -> None:
    existing = _index_existing_notes(notes_dir)
    records = adapter.list_memories(user_id=user_id, limit=limit)
    for record in records:
        note_path = existing.get(record.id)
        if note_path:
            note_file = Path(note_path)
        else:
            timestamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            slug = _slugify(record.text)
            filename = f"{timestamp}--{slug}__mem0.org"
            note_file = notes_dir / filename
        content = render_org_note(record, default_user=settings.notes.default_user)
        note_file.write_text(content, encoding="utf-8")


def import_notes(
    adapter: Mem0Adapter,
    settings: HippocampusSettings,
    notes_dir: Path,
    default_user: Optional[str],
) -> None:
    for path in sorted(notes_dir.glob("*.org")):
        properties, body = parse_org_file(path)
        mem0_id = properties.get("MEM0_ID") or properties.get("ID")
        user_id = properties.get("USER") or default_user or settings.notes.default_user

        # Skip notes that already have a Mem0 ID.
        if mem0_id:
            continue

        experience = ExperienceCreate(user_id=user_id, text=body.strip(), metadata=_properties_to_metadata(properties))
        record = adapter.add_experience(experience)
        properties["MEM0_ID"] = record.id
        properties["ID"] = record.id
        updated = render_org_note(record, default_user=user_id, extra_properties=properties, body_override=body)
        path.write_text(updated, encoding="utf-8")


def _index_existing_notes(notes_dir: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for path in notes_dir.glob("*.org"):
        props, _ = parse_org_file(path)
        mem_id = props.get("MEM0_ID") or props.get("ID")
        if mem_id:
            mapping[mem_id] = str(path)
    return mapping


def parse_org_file(path: Path) -> Tuple[Dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    properties: Dict[str, str] = {}
    body_lines: List[str] = []
    in_properties = False
    for line in lines:
        if line.strip().startswith(":PROPERTIES:"):
            in_properties = True
            continue
        if in_properties and line.strip().startswith(":END:"):
            in_properties = False
            continue
        if in_properties:
            match = re.match(r":([^:]+):\s*(.+)", line)
            if match:
                properties[match.group(1).strip().upper()] = match.group(2).strip()
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return properties, body


def render_org_note(
    record,
    default_user: str,
    extra_properties: Optional[Dict[str, str]] = None,
    body_override: Optional[str] = None,
) -> str:
    tags = record.metadata.get("tags") if hasattr(record, "metadata") else {}
    if isinstance(tags, dict):
        tags_value = " ".join(str(tag) for tag in tags.values())
    elif isinstance(tags, (list, tuple, set)):
        tags_value = " ".join(str(tag) for tag in tags)
    else:
        tags_value = str(tags) if tags else ""

    created = record.metadata.get("created_at") if hasattr(record, "metadata") else None
    created = created or dt.datetime.utcnow().isoformat()

    props = {
        "ID": getattr(record, "id", ""),
        "MEM0_ID": getattr(record, "id", ""),
        "USER": getattr(record, "user_id", default_user),
        "SOURCE": "mem0",
        "CREATED": str(created),
    }
    if tags_value:
        props["TAGS"] = tags_value
    if extra_properties:
        for key, value in extra_properties.items():
            props[key.upper()] = value

    body_text = body_override if body_override is not None else getattr(record, "text", "")
    header = textwrap.dedent(
        f"""\
        #+title: Memory: { _slugify(body_text) }
        #+date: {created}
        :PROPERTIES:
        """
    )
    properties_block = "\n".join(f":{key}: {value}" for key, value in props.items())
    return "\n".join([header, properties_block, ":END:", "", body_text.strip(), ""])


def _properties_to_metadata(properties: Dict[str, str]) -> Dict[str, str]:
    metadata = dict(properties)
    metadata.pop("MEM0_ID", None)
    metadata.pop("ID", None)
    metadata.pop("USER", None)
    metadata.pop("SOURCE", None)
    return metadata


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip())[:48]
    cleaned = cleaned.strip("-").lower()
    return cleaned or "memory"


if __name__ == "__main__":
    main()
