from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass
class BirthInfo:
    timestamp: str  # ISO string local time
    timezone: str
    location_name: str
    latitude: float
    longitude: float


def _fallback_sun_sign(timestamp: str) -> str:
    # Very rough fallback: hardcode Sag for 22 Nov 2025
    if "-11-" in timestamp and timestamp.split("-")[2][:2] >= "22":
        return "Sagittarius"
    return "Unknown"


def get_chart(birth: BirthInfo, cache_path: Path, engine: str = "fallback") -> Dict:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    chart: Dict[str, str] = {}
    if engine == "swisseph":
        try:
            import swisseph as swe  # type: ignore
            # Minimal: compute sun longitude -> sign
            jd = swe.julday(
                int(birth.timestamp[0:4]),
                int(birth.timestamp[5:7]),
                int(birth.timestamp[8:10]),
                0.0,
            )
            sun_pos = swe.calc_ut(jd, swe.SUN)[0]
            sign = int(sun_pos // 30)
            zodiac = [
                "Aries",
                "Taurus",
                "Gemini",
                "Cancer",
                "Leo",
                "Virgo",
                "Libra",
                "Scorpio",
                "Sagittarius",
                "Capricorn",
                "Aquarius",
                "Pisces",
            ]
            chart["sun_sign"] = zodiac[sign]
        except Exception:
            chart["sun_sign"] = _fallback_sun_sign(birth.timestamp)
            chart["engine"] = "fallback"
        else:
            chart["engine"] = "swisseph"
    else:
        chart["sun_sign"] = _fallback_sun_sign(birth.timestamp)
        chart["engine"] = "fallback"

    cache_path.write_text(json.dumps(chart, indent=2), encoding="utf-8")
    return chart


def get_signals(chart: Dict) -> Dict[str, str]:
    sun = chart.get("sun_sign", "")
    signals: Dict[str, str] = {}
    if sun == "Sagittarius":
        signals.update(
            {
                "synthesis_bias": "high",
                "zoom_out_preference": "high",
                "future_orientation": "medium",
                "pattern_linking": "high",
            }
        )
    return signals


def render_bias_note(signals: Dict[str, str]) -> str:
    if not signals:
        return ""
    notes = []
    if signals.get("synthesis_bias") == "high":
        notes.append("Bias toward synthesis and big-picture linking.")
    if signals.get("zoom_out_preference") == "high":
        notes.append("Preference to zoom out before diving into details.")
    if signals.get("future_orientation"):
        notes.append("Leans slightly future-oriented.")
    if not notes:
        return ""
    return " ".join(notes[:2])


def compute_bias_note_from_env() -> str:
    enabled = os.environ.get("SAM_ASTROLOGY_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    birth = BirthInfo(
        timestamp=os.environ.get("SAM_BIRTH_TIMESTAMP", "2025-11-22T16:35:00"),
        timezone=os.environ.get("SAM_BIRTH_TIMEZONE", "Australia/Melbourne"),
        location_name=os.environ.get("SAM_BIRTH_LOCATION_NAME", "Melbourne, Australia"),
        latitude=float(os.environ.get("SAM_BIRTH_LATITUDE", "-37.8136")),
        longitude=float(os.environ.get("SAM_BIRTH_LONGITUDE", "144.9631")),
    )
    cache_path = Path(os.environ.get("SAM_ASTROLOGY_CACHE_PATH", "var/cache/sam_chart.json"))
    engine = os.environ.get("SAM_ASTROLOGY_ENGINE", "fallback")
    return compute_bias_note(enabled=enabled, birth=birth, cache_path=cache_path, engine=engine)


def compute_bias_note(*, enabled: bool, birth: BirthInfo, cache_path: Path, engine: str, signals_enabled: bool = True) -> str:
    if not enabled:
        return ""
    chart = get_chart(birth, cache_path=cache_path, engine=engine or "fallback")
    if not signals_enabled:
        return ""
    signals = get_signals(chart)
    return render_bias_note(signals)


__all__ = [
    "BirthInfo",
    "get_chart",
    "get_signals",
    "render_bias_note",
    "compute_bias_note_from_env",
    "compute_bias_note",
]
