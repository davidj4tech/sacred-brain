#!/usr/bin/env python3
"""Wrapper that runs the actual logger from repo root."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
impl = root / 'scripts' / 'codex_log_impl.py'
cmd = [sys.executable, str(impl), *sys.argv[1:]]
result = subprocess.run(cmd, cwd=root)
sys.exit(result.returncode)
