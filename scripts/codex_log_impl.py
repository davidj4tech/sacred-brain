from __future__ import annotations
import argparse
import datetime as dt
import os
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "codex" / "session_memory.md"
MEM0_URL = os.getenv("MEM0_URL", "http://127.0.0.1:8000/memories")
MEM0_API_KEY = os.getenv("MEM0_API_KEY")

def append_entry(summary: str, files: list[str]) -> None:
    timestamp = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    entry_lines = [f"## {timestamp}", f"- summary: {summary}"]
    if files:
        entry_lines.append(f"- files: {', '.join(files)}")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(entry_lines) + "\n\n")
    if MEM0_API_KEY:
        payload = {"user_id": "codex", "text": summary, "metadata": {"files": files, "tag": "codex_session"}}
        headers = {"Content-Type": "application/json", "X-API-Key": MEM0_API_KEY}
        try:
            httpx.post(MEM0_URL, json=payload, headers=headers, timeout=10).raise_for_status()
        except Exception as exc:
            print(f"Warning: failed to push to Mem0: {exc}")

def show_recent(limit: int) -> None:
    if not LOG_PATH.exists():
        print("No log entries yet.")
        return
    lines = LOG_PATH.read_text().strip().splitlines()
    entries: list[list[str]] = []
    chunk: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if chunk:
                entries.append(chunk)
                chunk = []
        chunk.append(line)
    if chunk:
        entries.append(chunk)
    for block in entries[-limit:]:
        print("\n".join(block))
        print()

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    add_cmd = sub.add_parser("add")
    add_cmd.add_argument("summary")
    add_cmd.add_argument("files", nargs="*", default=[])
    recent_cmd = sub.add_parser("recent")
    recent_cmd.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)
    if args.command == "add":
        append_entry(args.summary, args.files)
    elif args.command == "recent":
        show_recent(args.limit)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
