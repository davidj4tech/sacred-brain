"""Oracle layer for REM reflection — astrology + tarot influences.

Provides a small, side-effect-free snapshot the dreaming sweep can fold
into its nightly narrative. Two ingredients:

1. **Astrology** — a kerykeion `AstrologicalSubject` for *now*. If we have
   stored natal details for the user we build a transit chart (current
   sky aspected to their natal placements). Otherwise we fall back to a
   mundane snapshot (just current sky, no aspects).
2. **Tarot** — a deterministic single-card pull seeded on
   `(user_id, UTC date)`. Same night → same card. The 78-card deck
   (Rider-Waite keywords) is bundled in this module.

Natal data lives at `<state_dir>/oracle/natal/<user_id>.json`. Use
`scripts/sacred-brain-oracle` to manage it.

All HTTP and filesystem IO is contained here; tests can drive the
formatters with hand-built dicts.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NATAL_FIELDS = ("name", "year", "month", "day", "hour", "minute",
                "city", "nation", "lng", "lat", "tz_str")


# ---------------------------------------------------------------------------
# Natal storage
# ---------------------------------------------------------------------------

def natal_dir(state_dir: Path) -> Path:
    return state_dir / "oracle" / "natal"


def natal_path(state_dir: Path, user_id: str) -> Path:
    safe = user_id.replace("/", "_")
    return natal_dir(state_dir) / f"{safe}.json"


def load_natal(state_dir: Path, user_id: str) -> dict[str, Any] | None:
    p = natal_path(state_dir, user_id)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Natal-from-memory recovery
# ---------------------------------------------------------------------------

# Probe queries used to fish natal data out of long-term memory. Kept short
# so the substring fallback in HippocampusClient.query_memories has a chance.
NATAL_QUERIES = (
    "born",
    "birthday",
    "birth date",
    "birth time",
    "birthplace",
    "natal chart",
    "astrology",
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _extract_natal_fields(text: str) -> dict[str, Any]:
    """Best-effort regex pass over a memory text for birth date/time/place.

    Conservative: only returns keys we found high-confidence matches for.
    Caller merges across multiple memories.
    """
    out: dict[str, Any] = {}
    t = text.strip()
    low = t.lower()

    # ISO date  YYYY-MM-DD
    m = re.search(r"\b(19|20)\d{2}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b", t)
    if m:
        y, mo, d = m.group(0).split("-")
        out["year"], out["month"], out["day"] = int(y), int(mo), int(d)
    else:
        # "June 15, 1990" / "15 June 1990"
        m = re.search(
            r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(19\d{2}|20\d{2})\b", t)
        if m and m.group(1).lower() in _MONTHS:
            out["month"] = _MONTHS[m.group(1).lower()]
            out["day"] = int(m.group(2))
            out["year"] = int(m.group(3))
        else:
            m = re.search(
                r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(19\d{2}|20\d{2})\b", t)
            if m and m.group(2).lower() in _MONTHS:
                out["day"] = int(m.group(1))
                out["month"] = _MONTHS[m.group(2).lower()]
                out["year"] = int(m.group(3))

    # Time   "born at 2:32pm" / "14:32"
    m = re.search(
        r"\b(?:at\s+)?(\d{1,2}):(\d{2})\s*(am|pm|a\.m\.|p\.m\.)?\b", low)
    if m:
        hh = int(m.group(1)); mm = int(m.group(2))
        suf = (m.group(3) or "").replace(".", "")
        if suf == "pm" and hh < 12:
            hh += 12
        elif suf == "am" and hh == 12:
            hh = 0
        if 0 <= hh < 24 and 0 <= mm < 60:
            out["hour"], out["minute"] = hh, mm

    # Place: "born ... in <City>[, <Region>]" — allow words between "born" and "in"
    m = re.search(
        r"\bborn\b[^\n.]{0,80}?\bin\s+([A-Z][A-Za-z .'-]+?)"
        r"(?:,\s*([A-Z][A-Za-z .'-]+?))?(?=[\.,\n]|$)",
        t,
    )
    if m:
        out["city"] = m.group(1).strip()
        if m.group(2):
            # crude: 2-letter US state → US, otherwise leave nation default
            tail = m.group(2).strip()
            if len(tail) == 2 and tail.isupper():
                out["nation"] = "US"
    return out


async def discover_natal_from_memory(
    user_id: str,
    hippo,
    *,
    limit_per_query: int = 10,
) -> tuple[dict[str, Any], list[str]]:
    """Probe long-term memory for natal facts.

    Returns `(merged_fields, source_memory_ids)`. Earlier queries win on
    conflict — `NATAL_QUERIES` is ordered from most-specific to least.
    """
    merged: dict[str, Any] = {}
    sources: list[str] = []

    for q in NATAL_QUERIES:
        try:
            mems = await hippo.query_memories(user_id, q, limit=limit_per_query)
        except Exception:
            mems = []
        for mem in mems or []:
            text = mem.get("text") or mem.get("memory") or ""
            if not text:
                continue
            found = _extract_natal_fields(text)
            if not found:
                continue
            mid = mem.get("id") or mem.get("memory_id") or ""
            new_keys = [k for k in found if k not in merged]
            if new_keys:
                for k in new_keys:
                    merged[k] = found[k]
                if mid:
                    sources.append(mid)
            if all(k in merged for k in ("year", "month", "day")) and "city" in merged:
                return merged, sources
    return merged, sources


def natal_is_complete(data: dict[str, Any] | None) -> bool:
    """True iff data is sufficient to build a transit chart at all.

    A bare date (year/month/day) is enough — see `natal_precision` for the
    quality tier.
    """
    if not data:
        return False
    return all(k in data for k in ("year", "month", "day"))


def natal_precision(data: dict[str, Any] | None) -> str:
    """Classify how complete the natal record is.

    - "datetime" — has date, time, and a real location (lat/lng or city+tz).
                   Full chart: Ascendant, MC, houses, Moon all reliable.
    - "date"     — has date but missing time and/or location. Slow planets
                   are reliable; Moon is approximate (±6°), Ascendant/MC/
                   houses are unreliable and should not be used.
    - "none"     — date itself is missing.
    """
    if not natal_is_complete(data):
        return "none"
    has_time = "hour" in data and "minute" in data
    has_loc = ("lat" in data and "lng" in data) or ("city" in data and "tz_str" in data)
    if has_time and has_loc:
        return "datetime"
    return "date"


def save_natal(state_dir: Path, user_id: str, data: dict[str, Any]) -> Path:
    if not natal_is_complete(data):
        missing = [k for k in ("year", "month", "day") if k not in data]
        raise ValueError(f"natal data missing required fields: {missing}")
    data.setdefault("name", data.get("name") or "Native")
    p = natal_path(state_dir, user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tarot — bundled 78-card deck
# ---------------------------------------------------------------------------

# Compact: (name, upright keyword, reversed keyword)
_TAROT: list[tuple[str, str, str]] = [
    # Major Arcana
    ("The Fool", "beginnings, leap of faith", "recklessness, hesitation"),
    ("The Magician", "manifestation, focus", "manipulation, untapped talent"),
    ("The High Priestess", "intuition, hidden knowledge", "secrets ignored, repression"),
    ("The Empress", "abundance, nurture", "stagnation, dependence"),
    ("The Emperor", "structure, authority", "rigidity, control issues"),
    ("The Hierophant", "tradition, mentorship", "dogma, rebellion"),
    ("The Lovers", "alignment, choice", "misalignment, indecision"),
    ("The Chariot", "willpower, momentum", "scattered force, loss of direction"),
    ("Strength", "quiet courage, patience", "self-doubt, forced action"),
    ("The Hermit", "introspection, withdrawal", "isolation, refusing counsel"),
    ("Wheel of Fortune", "cycles, turning point", "stuck cycles, bad timing"),
    ("Justice", "truth, accountability", "evasion, imbalance"),
    ("The Hanged Man", "perspective shift, surrender", "stalled, wasted sacrifice"),
    ("Death", "ending, transformation", "resistance to change"),
    ("Temperance", "balance, integration", "excess, mismatch"),
    ("The Devil", "attachment, shadow", "release, breaking bonds"),
    ("The Tower", "sudden upheaval, rupture", "averted disaster, delayed reckoning"),
    ("The Star", "hope, recalibration", "discouragement, faithlessness"),
    ("The Moon", "illusion, the unconscious", "fears surfacing, deception revealed"),
    ("The Sun", "vitality, clarity", "dimmed joy, false confidence"),
    ("Judgement", "reckoning, awakening", "self-doubt, refusing the call"),
    ("The World", "completion, integration", "incomplete, lingering"),
]
# Minor Arcana
for _suit, _theme_up, _theme_rev in (
    ("Wands", "drive, creation, spirit", "burnout, scattered fire"),
    ("Cups", "feeling, relationship, water", "emotional block, withdrawal"),
    ("Swords", "thought, conflict, air", "confused mind, cruelty"),
    ("Pentacles", "matter, work, earth", "scarcity, neglect"),
):
    _TAROT.extend([
        (f"Ace of {_suit}", f"new {_theme_up}", f"blocked {_theme_up}"),
        (f"Two of {_suit}", "balance, choice", "imbalance"),
        (f"Three of {_suit}", "growth, collaboration", "miscoordination"),
        (f"Four of {_suit}", "stability, rest", "stagnation"),
        (f"Five of {_suit}", "loss, conflict", "recovery"),
        (f"Six of {_suit}", "harmony, giving", "imbalance in giving"),
        (f"Seven of {_suit}", "challenge, persistence", "futility"),
        (f"Eight of {_suit}", "movement, mastery", "blockage"),
        (f"Nine of {_suit}", "near-completion, vigilance", "anxiety, depletion"),
        (f"Ten of {_suit}", "culmination, fullness", "burden"),
        (f"Page of {_suit}", "curiosity, beginner's mind", "immaturity, scattered energy"),
        (f"Knight of {_suit}", "action, pursuit", "haste or paralysis"),
        (f"Queen of {_suit}", "embodiment, depth", "distortion of the suit's gift"),
        (f"King of {_suit}", "mastery, command", "abuse or hollowing of the suit"),
    ])

assert len(_TAROT) == 78, f"deck must be 78 cards, got {len(_TAROT)}"


def draw_tarot(user_id: str, *, now_ts: float | None = None) -> dict[str, Any]:
    """Deterministic single-card pull seeded on (user_id, UTC date).

    Same user, same UTC day → same card and orientation.
    """
    now = now_ts if now_ts is not None else time.time()
    date = time.strftime("%Y-%m-%d", time.gmtime(now))
    seed_src = f"{user_id}|{date}".encode("utf-8")
    digest = hashlib.sha256(seed_src).digest()
    idx = int.from_bytes(digest[:4], "big") % 78
    reversed_ = bool(digest[4] & 1)
    name, up_kw, rev_kw = _TAROT[idx]
    return {
        "card": name,
        "reversed": reversed_,
        "keyword": rev_kw if reversed_ else up_kw,
        "date": date,
    }


# ---------------------------------------------------------------------------
# Astrology — kerykeion adapter
# ---------------------------------------------------------------------------

@dataclass
class AstroSnapshot:
    mode: str  # "transit" | "transit_partial" | "mundane" | "unavailable"
    precision: str = "datetime"  # "datetime" | "date" | "none"
    moon_sign: str | None = None
    moon_phase: str | None = None
    sun_sign: str | None = None
    ascendant: str | None = None
    notable: list[str] = None  # type: ignore[assignment]
    caveats: list[str] = None  # type: ignore[assignment]
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "precision": self.precision,
            "moon_sign": self.moon_sign,
            "moon_phase": self.moon_phase,
            "sun_sign": self.sun_sign,
            "ascendant": self.ascendant,
            "notable": list(self.notable or []),
            "caveats": list(self.caveats or []),
            "error": self.error,
        }


def _moon_phase_label(sun_lon: float, moon_lon: float) -> str:
    """Crude 8-phase label from sun/moon ecliptic longitudes (degrees)."""
    delta = (moon_lon - sun_lon) % 360.0
    bands = [
        (22.5, "new moon"),
        (67.5, "waxing crescent"),
        (112.5, "first quarter"),
        (157.5, "waxing gibbous"),
        (202.5, "full moon"),
        (247.5, "waning gibbous"),
        (292.5, "last quarter"),
        (337.5, "waning crescent"),
    ]
    for cutoff, label in bands:
        if delta < cutoff:
            return label
    return "new moon"


def _now_subject(name: str = "Now"):
    """Build a kerykeion subject for the current UTC moment, mundane defaults."""
    from kerykeion import AstrologicalSubject  # local import — heavy dep

    t = time.gmtime()
    # Default location: Greenwich. Mundane snapshot only cares about planet
    # positions, not house cusps; lat/lng don't move sun/moon signs.
    return AstrologicalSubject(
        name=name,
        year=t.tm_year, month=t.tm_mon, day=t.tm_mday,
        hour=t.tm_hour, minute=t.tm_min,
        city="Greenwich", nation="GB",
        lng=0.0, lat=51.4769, tz_str="UTC",
        online=False,
    )


# Points whose aspects are unreliable when birth time / location are unknown.
# Moon moves ~13°/day so a noon stand-in can mis-aspect by half a sign.
# Ascendant, Midheaven, and house cusps depend entirely on time + location.
_TIME_DEPENDENT_POINTS = {
    "Moon", "Mean_Node", "True_Node", "Mean_South_Node", "True_South_Node",
    "Asc", "Ascendant", "First_House", "Mc", "MC", "Tenth_House",
    "Second_House", "Third_House", "Fourth_House", "Fifth_House",
    "Sixth_House", "Seventh_House", "Eighth_House", "Ninth_House",
    "Eleventh_House", "Twelfth_House",
}


def _natal_subject(natal: dict[str, Any]):
    from kerykeion import AstrologicalSubject

    # When time/location are missing we use noon UTC at Greenwich. This keeps
    # slow planets (Sun, Mercury through Pluto) accurate to within a fraction
    # of a degree; the Moon and any time-dependent points are filtered out
    # downstream by `_TIME_DEPENDENT_POINTS`.
    return AstrologicalSubject(
        name=natal.get("name", "Native"),
        year=int(natal["year"]),
        month=int(natal["month"]),
        day=int(natal["day"]),
        hour=int(natal.get("hour", 12)),
        minute=int(natal.get("minute", 0)),
        city=natal.get("city", "Greenwich"),
        nation=natal.get("nation", "GB"),
        lng=float(natal.get("lng", 0.0)),
        lat=float(natal.get("lat", 51.4769)),
        tz_str=natal.get("tz_str", "UTC"),
        online=False,
    )


def _planet_attr(subject, key: str) -> Any:
    """kerykeion versions vary on attribute access; tolerate both shapes."""
    obj = getattr(subject, key, None)
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    # PlanetModel-style: has .sign, .abs_pos
    return obj


def _sign(p) -> str | None:
    if p is None:
        return None
    if isinstance(p, dict):
        return p.get("sign")
    return getattr(p, "sign", None)


def _abs_pos(p) -> float | None:
    if p is None:
        return None
    if isinstance(p, dict):
        return p.get("abs_pos")
    return getattr(p, "abs_pos", None)


def _transit_aspects(
    now_subj,
    natal_subj,
    *,
    max_orb: float = 3.0,
    skip_points: set[str] | None = None,
) -> list[str]:
    """Major aspects from transiting planets to natal points, tight orbs only.

    `skip_points` drops aspects whose p1 or p2 names appear in the set
    (case-insensitive on a `_`-normalised form). Used to filter Moon /
    Ascendant / house aspects when birth time is unknown.
    """
    try:
        from kerykeion import SynastryAspects
    except ImportError:
        return []
    try:
        synastry = SynastryAspects(now_subj, natal_subj)
        aspects = synastry.relevant_aspects
    except Exception:
        return []

    skip = {p.lower() for p in (skip_points or set())}

    out: list[str] = []
    for asp in aspects or []:
        try:
            orb = abs(float(asp.get("orbit", 99)))
            if orb > max_orb:
                continue
            p1 = asp.get("p1_name")
            p2 = asp.get("p2_name")
            kind = asp.get("aspect")
            if not (p1 and p2 and kind):
                continue
            if skip and (p1.lower() in skip or p2.lower() in skip):
                continue
            out.append(f"transit {p1} {kind} natal {p2} (orb {orb:.1f}°)")
        except Exception:
            continue
        if len(out) >= 6:
            break
    return out


def build_astro_snapshot(natal: dict[str, Any] | None) -> AstroSnapshot:
    """Build an astrology snapshot. Never raises — errors land in `error`."""
    try:
        now_subj = _now_subject()
    except Exception as exc:  # noqa: BLE001
        return AstroSnapshot(mode="unavailable", error=f"now subject failed: {exc}")

    sun = _planet_attr(now_subj, "sun")
    moon = _planet_attr(now_subj, "moon")
    asc = _planet_attr(now_subj, "first_house") or _planet_attr(now_subj, "asc")

    moon_phase = None
    sun_lon = _abs_pos(sun)
    moon_lon = _abs_pos(moon)
    if sun_lon is not None and moon_lon is not None:
        moon_phase = _moon_phase_label(float(sun_lon), float(moon_lon))

    snap = AstroSnapshot(
        mode="mundane",
        precision="datetime",  # mundane "now" is always exact
        moon_sign=_sign(moon),
        moon_phase=moon_phase,
        sun_sign=_sign(sun),
        ascendant=_sign(asc),
        notable=[],
        caveats=[],
    )

    if natal:
        precision = natal_precision(natal)
        if precision == "none":
            return snap
        skip = _TIME_DEPENDENT_POINTS if precision != "datetime" else None
        try:
            natal_subj = _natal_subject(natal)
            snap.notable = _transit_aspects(now_subj, natal_subj, skip_points=skip)
            snap.precision = precision
            if precision == "datetime":
                snap.mode = "transit"
            else:
                snap.mode = "transit_partial"
                snap.caveats = [
                    "natal time unknown — Moon position approximate (±6°)",
                    "natal Ascendant / Midheaven / houses unknown; "
                    "those aspects are excluded",
                ]
        except Exception as exc:  # noqa: BLE001
            snap.error = f"transit chart failed: {exc}"

    return snap


# ---------------------------------------------------------------------------
# Composite snapshot for REM
# ---------------------------------------------------------------------------

def build_oracle_snapshot(
    user_id: str,
    state_dir: Path,
    *,
    enabled: bool = True,
    now_ts: float | None = None,
) -> dict[str, Any] | None:
    """Top-level entry called by the dreaming sweep.

    Returns `None` when oracle is disabled, so callers can `if oracle:`
    without conditionals leaking into formatting.
    """
    if not enabled:
        return None
    natal = load_natal(state_dir, user_id)
    astro = build_astro_snapshot(natal)
    tarot = draw_tarot(user_id, now_ts=now_ts)
    return {
        "user_id": user_id,
        "astro": astro.as_dict(),
        "tarot": tarot,
        "natal_used": natal is not None,
    }


def format_oracle_block(oracle: dict[str, Any]) -> str:
    """Plain-text block to fold into the REM user message."""
    astro = oracle.get("astro") or {}
    tarot = oracle.get("tarot") or {}

    lines: list[str] = []
    mode = astro.get("mode", "unavailable")
    precision = astro.get("precision") or "datetime"
    if mode == "unavailable":
        lines.append(f"Sky: unavailable ({astro.get('error') or 'no data'})")
    else:
        sun = astro.get("sun_sign") or "?"
        moon = astro.get("moon_sign") or "?"
        phase = astro.get("moon_phase") or "?"
        asc = astro.get("ascendant")
        label = mode if precision == "datetime" else f"{mode}, {precision}-only"
        sky = f"Sun in {sun}, Moon in {moon} ({phase})"
        if asc:
            sky += f", Ascendant {asc}"
        lines.append(f"Sky ({label}): {sky}")
        for n in astro.get("notable") or []:
            lines.append(f"  · {n}")
        for c in astro.get("caveats") or []:
            lines.append(f"  ! {c}")

    card = tarot.get("card", "?")
    orient = "reversed" if tarot.get("reversed") else "upright"
    kw = tarot.get("keyword", "")
    lines.append(f"Tarot: {card} ({orient}) — {kw}")
    return "\n".join(lines)
