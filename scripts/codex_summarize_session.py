#!/usr/bin/env python3
"""Summarise the latest Codex transcript into codex/session_memory.md."""
from __future__ import annotations

import argparse
import re
import sys
from collections import deque
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / ".codex"
SESSION_RE = re.compile(r"session-\d{8}-\d{6}\.log$")
ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

sys.path.append(str(ROOT / "scripts"))
from codex_log_impl import append_entry  # type: ignore  # noqa: E402


def find_latest_log() -> Path:
    candidates = [p for p in LOG_DIR.glob("session-*.log") if SESSION_RE.match(p.name)]
    if not candidates:
        raise SystemExit("No session logs found in .codex")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def tail_lines(path: Path, limit: int) -> list[str]:
    buf: deque[str] = deque(maxlen=limit)
    with path.open("r", errors="ignore") as fh:
        for line in fh:
            buf.append(line.rstrip("\n"))
    return list(buf)


def strip_ansi(lines: Iterable[str]) -> list[str]:
    return [ANSI_RE.sub("", line).strip() for line in lines]


def extract_bullets(lines: list[str], max_bullets: int) -> tuple[list[str], list[str]]:
    bullets: list[str] = []
    files: list[str] = []
    seen = set()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        text = line
        if line.startswith("•"):
            text = line.lstrip("•").strip()
        elif line.startswith("- "):
            text = line[2:].strip()
        elif line.lower().startswith("file updated:"):
            text = line.split(":", 1)[1].strip()
            files.append(text)
            text = f"updated {text}"
        elif line.lower().startswith("files:"):
            text = line.split(":", 1)[1].strip()
        elif line.lower().startswith("edited "):
            payload = line.split(" ", 1)[1].strip()
            files.append(payload)
            text = f"edited {payload}"
        if len(text) < 3:
            continue
        if text in seen:
            continue
        seen.add(text)
        bullets.append(text)
        if len(bullets) >= max_bullets:
            break
    return bullets, files


def build_summary(bullets: list[str]) -> str:
    return " | ".join(bullets)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, help="Path to a session-*.log (defaults to latest in .codex)")
    parser.add_argument("--lines", type=int, default=400, help="How many trailing lines to inspect")
    parser.add_argument("--max-bullets", type=int, default=6, help="Maximum bullet points to keep")
    parser.add_argument("--summary", help="Override auto-generated summary text")
    parser.add_argument("--files", nargs="*", default=[], help="Explicit file paths to attach")
    parser.add_argument("--dry-run", action="store_true", help="Print the summary instead of writing it")
    args = parser.parse_args(argv)

    log_path = args.log or find_latest_log()
    raw_lines = tail_lines(log_path, args.lines)
    clean_lines = strip_ansi(raw_lines)
    bullets, inferred_files = extract_bullets(list(reversed(clean_lines)), args.max_bullets)

    summary_text = args.summary or build_summary(bullets)
    if not summary_text:
        raise SystemExit("No summary content detected; provide --summary or increase --lines.")

    files = list(dict.fromkeys(args.files + inferred_files))

    if args.dry_run:
        print(f"Log: {log_path}")
        print(f"Summary: {summary_text}")
        if files:
            print(f"Files: {', '.join(files)}")
        return

    append_entry(summary_text, files)
    print(f"Wrote summary to {ROOT / 'codex' / 'session_memory.md'}")


if __name__ == "__main__":
    main()
