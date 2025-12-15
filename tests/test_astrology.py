from __future__ import annotations

from pathlib import Path

from sacred_brain.astrology import BirthInfo, compute_bias_note, get_chart


def _default_birth() -> BirthInfo:
    return BirthInfo(
        timestamp="2025-11-22T16:35:00",
        timezone="Australia/Melbourne",
        location_name="Melbourne, Australia",
        latitude=-37.8136,
        longitude=144.9631,
    )


def test_fallback_chart_sets_sun_sign(tmp_path: Path) -> None:
    chart = get_chart(_default_birth(), cache_path=tmp_path / "chart.json", engine="fallback")
    assert chart["sun_sign"] == "Sagittarius"
    assert chart["engine"] == "fallback"


def test_bias_note_cached_and_reused(tmp_path: Path) -> None:
    cache = tmp_path / "sam_chart.json"
    note_first = compute_bias_note(
        enabled=True,
        birth=_default_birth(),
        cache_path=cache,
        engine="fallback",
        signals_enabled=True,
    )
    note_second = compute_bias_note(
        enabled=True,
        birth=_default_birth(),
        cache_path=cache,
        engine="swisseph",  # should hit cache instead
        signals_enabled=True,
    )
    assert cache.exists()
    assert note_first == note_second


def test_bias_note_disabled(tmp_path: Path) -> None:
    note = compute_bias_note(
        enabled=False,
        birth=_default_birth(),
        cache_path=tmp_path / "sam_chart.json",
        engine="fallback",
        signals_enabled=True,
    )
    assert note == ""


def test_bias_note_signals_disabled(tmp_path: Path) -> None:
    note = compute_bias_note(
        enabled=True,
        birth=_default_birth(),
        cache_path=tmp_path / "sam_chart.json",
        engine="fallback",
        signals_enabled=False,
    )
    assert note == ""
