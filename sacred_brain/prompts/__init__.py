from pathlib import Path

SYSTEM_PROMPT = (Path(__file__).resolve().parent / "sam_system.txt").read_text(encoding="utf-8")

__all__ = ["SYSTEM_PROMPT"]
