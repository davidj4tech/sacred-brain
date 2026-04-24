from __future__ import annotations

import os
from pathlib import Path

import pytest

from memory_governor.dream import (
    SACRED_BRAIN_DREAMS_DEFAULT,
    dreams_target_for_today,
    resolve_dreams_output_path,
    write_dream_entry,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DREAMS_OUTPUT_PATH", raising=False)


def test_default_no_env_no_package() -> None:
    assert resolve_dreams_output_path() == SACRED_BRAIN_DREAMS_DEFAULT


def test_package_default_beats_sacred_default(tmp_path: Path) -> None:
    pkg = tmp_path / "workspace" / "DREAMS.md"
    assert resolve_dreams_output_path(package_default=pkg) == pkg


def test_env_beats_package_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / "from-env"
    pkg = tmp_path / "workspace" / "DREAMS.md"
    monkeypatch.setenv("DREAMS_OUTPUT_PATH", str(env_path))
    assert resolve_dreams_output_path(package_default=pkg) == env_path


def test_env_expanduser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DREAMS_OUTPUT_PATH", "~/dreams/DREAMS.md")
    result = resolve_dreams_output_path()
    assert not str(result).startswith("~")


def test_target_directory_mode(tmp_path: Path) -> None:
    target, symlink = dreams_target_for_today(tmp_path / "dreams", today="2026-04-24")
    assert target == tmp_path / "dreams" / "2026-04-24.md"
    assert symlink == tmp_path / "dreams" / "latest.md"


def test_target_file_mode(tmp_path: Path) -> None:
    base = tmp_path / "repo" / "DREAMS.md"
    target, symlink = dreams_target_for_today(base, today="2026-04-24")
    assert target == base
    assert symlink is None


def test_write_dream_entry_dated(tmp_path: Path) -> None:
    target = write_dream_entry(tmp_path / "dreams", "hello\n", today="2026-04-24")
    assert target.read_text() == "hello\n"
    latest = tmp_path / "dreams" / "latest.md"
    assert latest.is_symlink()
    assert latest.resolve() == target


def test_write_dream_entry_overwrites_symlink(tmp_path: Path) -> None:
    write_dream_entry(tmp_path / "dreams", "day1\n", today="2026-04-23")
    target = write_dream_entry(tmp_path / "dreams", "day2\n", today="2026-04-24")
    latest = tmp_path / "dreams" / "latest.md"
    assert latest.resolve() == target
    assert latest.resolve().read_text() == "day2\n"


def test_write_dream_entry_file_mode(tmp_path: Path) -> None:
    base = tmp_path / "repo" / "DREAMS.md"
    target = write_dream_entry(base, "content", today="2026-04-24")
    assert target == base
    assert target.read_text() == "content"
    assert not (tmp_path / "repo" / "latest.md").exists()
