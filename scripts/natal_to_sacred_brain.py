#!/usr/bin/env python3
"""Compute a natal chart with kerykeion and emit memory payloads for sacred brain.

Per-user one-shot ingest: produces 22 memories (1 canonical JSON blob, 12
placements including angles, 8 tightest aspects, 1 element/modality synthesis)
under the given user_id, all tagged metadata.source = 'natal-chart-v1' so the
set is bulk-replaceable on schema changes.

Examples:

    # David
    natal_to_sacred_brain.py --user-id david --name David \\
        --dob 1976-04-22 --time 12:19 --place Melbourne --country AU --dry-run

    # ...then --post when the dry-run looks right.

Reads HIPPOCAMPUS_URL / HIPPOCAMPUS_API_KEY from env or ~/.config/hippocampus.env.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

from kerykeion import AstrologicalSubject

SOURCE_TAG = "natal-chart-v1"

SIGN_FULL = {
    "Ari": "Aries", "Tau": "Taurus", "Gem": "Gemini", "Can": "Cancer",
    "Leo": "Leo", "Vir": "Virgo", "Lib": "Libra", "Sco": "Scorpio",
    "Sag": "Sagittarius", "Cap": "Capricorn", "Aqu": "Aquarius", "Pis": "Pisces",
}
SIGN_ELEMENT = {
    "Aries": "fire", "Leo": "fire", "Sagittarius": "fire",
    "Taurus": "earth", "Virgo": "earth", "Capricorn": "earth",
    "Gemini": "air", "Libra": "air", "Aquarius": "air",
    "Cancer": "water", "Scorpio": "water", "Pisces": "water",
}
SIGN_MODALITY = {
    "Aries": "cardinal", "Cancer": "cardinal", "Libra": "cardinal", "Capricorn": "cardinal",
    "Taurus": "fixed", "Leo": "fixed", "Scorpio": "fixed", "Aquarius": "fixed",
    "Gemini": "mutable", "Virgo": "mutable", "Sagittarius": "mutable", "Pisces": "mutable",
}
HOUSE_NUM = {
    "First_House": 1, "Second_House": 2, "Third_House": 3, "Fourth_House": 4,
    "Fifth_House": 5, "Sixth_House": 6, "Seventh_House": 7, "Eighth_House": 8,
    "Ninth_House": 9, "Tenth_House": 10, "Eleventh_House": 11, "Twelfth_House": 12,
}
HOUSE_ATTR = {  # kerykeion uses lowercase attrs
    "First_House": "first_house", "Second_House": "second_house",
    "Third_House": "third_house", "Fourth_House": "fourth_house",
    "Fifth_House": "fifth_house", "Sixth_House": "sixth_house",
    "Seventh_House": "seventh_house", "Eighth_House": "eighth_house",
    "Ninth_House": "ninth_house", "Tenth_House": "tenth_house",
    "Eleventh_House": "eleventh_house", "Twelfth_House": "twelfth_house",
}
PLANETS = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
           "uranus", "neptune", "pluto", "mean_node"]
PLANET_LABEL = {
    "sun": "Sun", "moon": "Moon", "mercury": "Mercury", "venus": "Venus",
    "mars": "Mars", "jupiter": "Jupiter", "saturn": "Saturn",
    "uranus": "Uranus", "neptune": "Neptune", "pluto": "Pluto",
    "mean_node": "North Node (mean)",
}


def fmt_deg(pos: float) -> str:
    d = int(pos)
    m = int(round((pos - d) * 60))
    if m == 60:
        d += 1
        m = 0
    return f"{d}°{m:02d}'"


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


SIGN_ORDER = ["Ari", "Tau", "Gem", "Can", "Leo", "Vir",
              "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis"]


def absolute_longitude(p) -> float:
    """kerykeion's .position is degrees within sign; sign abbr gives the offset."""
    return SIGN_ORDER.index(p.sign) * 30.0 + p.position


def planet_dict(p) -> dict:
    sign = SIGN_FULL[p.sign]
    house = HOUSE_NUM.get(getattr(p, "house", "") or "", None)
    return {
        "name": p.name,
        "sign": sign,
        "sign_abbr": p.sign,
        "abs_longitude": round(absolute_longitude(p), 4),
        "deg_in_sign": fmt_deg(p.position),
        "house": house,
        "retrograde": bool(getattr(p, "retrograde", False)),
        "element": SIGN_ELEMENT[sign],
        "modality": SIGN_MODALITY[sign],
    }


def aspects(subject) -> list[dict]:
    """Compute major aspects between planet pairs with tight orbs."""
    from itertools import combinations
    ASPECT_ANGLES = {
        "conjunction": 0,
        "sextile": 60,
        "square": 90,
        "trine": 120,
        "opposition": 180,
    }
    ORB = 6.0  # degrees; tight enough to be meaningful
    points = []
    for key in PLANETS:
        p = getattr(subject, key, None)
        if p is None:
            continue
        points.append((key, absolute_longitude(p)))
    out = []
    for (a_key, a_lon), (b_key, b_lon) in combinations(points, 2):
        diff = abs(a_lon - b_lon) % 360
        if diff > 180:
            diff = 360 - diff
        for asp_name, angle in ASPECT_ANGLES.items():
            orb = abs(diff - angle)
            if orb <= ORB:
                out.append({
                    "a": a_key, "b": b_key, "aspect": asp_name,
                    "angle": angle, "orb": round(orb, 2),
                })
                break
    out.sort(key=lambda x: x["orb"])
    return out


def build_chart(subject, who: dict) -> dict:
    planets = {key: planet_dict(getattr(subject, key)) for key in PLANETS
               if getattr(subject, key, None) is not None}
    asc = subject.first_house
    mc = subject.tenth_house
    chart = {
        "subject": {
            "name": who["name"],
            "dob": who["dob"],
            "time_local": who["time"],
            "place": f"{who['place']}, {who['country']}",
        },
        "ascendant": {
            "sign": SIGN_FULL[asc.sign],
            "deg_in_sign": fmt_deg(asc.position),
            "abs_longitude": round(absolute_longitude(asc), 4),
        },
        "midheaven": {
            "sign": SIGN_FULL[mc.sign],
            "deg_in_sign": fmt_deg(mc.position),
            "abs_longitude": round(absolute_longitude(mc), 4),
        },
        "houses": {
            HOUSE_NUM[hk]: {"sign": SIGN_FULL[getattr(subject, HOUSE_ATTR[hk]).sign],
                            "deg_in_sign": fmt_deg(getattr(subject, HOUSE_ATTR[hk]).position),
                            "abs_longitude": round(absolute_longitude(getattr(subject, HOUSE_ATTR[hk])), 4)}
            for hk in HOUSE_NUM
        },
        "planets": planets,
        "aspects": aspects(subject),
    }
    # Synthesis
    elem_counts = Counter(p["element"] for p in planets.values()
                          if p["name"] not in ("Mean_Node",))
    mod_counts = Counter(p["modality"] for p in planets.values()
                         if p["name"] not in ("Mean_Node",))
    chart["synthesis"] = {
        "elements": dict(elem_counts),
        "modalities": dict(mod_counts),
        "dominant_element": elem_counts.most_common(1)[0][0],
        "dominant_modality": mod_counts.most_common(1)[0][0],
    }
    return chart


def memory_payloads(chart: dict, who: dict) -> list[dict]:
    """Return list of {text, metadata} dicts to write to sacred brain."""
    from datetime import date
    name = who["name"]
    canonical_phrase = f"{name.lower()} natal chart full"
    # Pretty date for the blob preface ("22 April 1976" reads better than "1976-04-22").
    y, m, d = (int(x) for x in who["dob"].split("-"))
    pretty_dob = date(y, m, d).strftime("%-d %B %Y")
    out = []
    # 1. The canonical full-chart blob.
    blob_text = (
        f"{name}'s natal chart (full). Canonical query phrase: \"{canonical_phrase}\". "
        f"Born {pretty_dob} {who['time']} local time, {who['place']}, {who['country']}. "
        f"Computed with kerykeion (Swiss Ephemeris). JSON follows.\n\n"
        f"```json\n{json.dumps(chart, indent=2)}\n```"
    )
    out.append({
        "text": blob_text,
        "metadata": {"source": SOURCE_TAG, "kind": "natal_chart_full",
                     "canonical_query": canonical_phrase},
    })

    # 2. Per-placement atoms (sun, moon, asc, mc, then other planets).
    asc = chart["ascendant"]
    mc = chart["midheaven"]
    out.append({
        "text": f"{name}'s natal Ascendant (rising sign) is {asc['sign']} at {asc['deg_in_sign']}.",
        "metadata": {"source": SOURCE_TAG, "kind": "placement", "point": "ascendant"},
    })
    out.append({
        "text": f"{name}'s natal Midheaven (MC) is {mc['sign']} at {mc['deg_in_sign']}.",
        "metadata": {"source": SOURCE_TAG, "kind": "placement", "point": "midheaven"},
    })
    for key, p in chart["planets"].items():
        if key in ("mean_node",):
            # Still emit but lower-priority in the prose
            out.append({
                "text": (f"{name}'s natal {PLANET_LABEL[key]} is in {p['sign']} at "
                         f"{p['deg_in_sign']}, in the {ordinal(p['house'])} house"
                         f"{' (retrograde)' if p['retrograde'] else ''}."),
                "metadata": {"source": SOURCE_TAG, "kind": "placement", "point": key},
            })
            continue
        out.append({
            "text": (f"{name}'s natal {PLANET_LABEL[key]} is in {p['sign']} at "
                     f"{p['deg_in_sign']}, in the {ordinal(p['house'])} house"
                     f"{' (retrograde)' if p['retrograde'] else ''}. "
                     f"{p['sign']} is a {p['modality']} {p['element']} sign."),
            "metadata": {"source": SOURCE_TAG, "kind": "placement", "point": key},
        })

    # 3. Tightest aspects (top 8).
    ASP_VERB = {
        "conjunction": "conjunct",
        "sextile": "sextile",
        "square": "square",
        "trine": "trine",
        "opposition": "opposite",
    }
    for asp in chart["aspects"][:8]:
        a_label = PLANET_LABEL[asp["a"]]
        b_label = PLANET_LABEL[asp["b"]]
        out.append({
            "text": (f"{name}'s natal {a_label} is {ASP_VERB[asp['aspect']]} {b_label} "
                     f"(orb {asp['orb']}°)."),
            "metadata": {"source": SOURCE_TAG, "kind": "aspect",
                         "a": asp["a"], "b": asp["b"], "aspect": asp["aspect"]},
        })

    # 4. Synthesis atoms.
    s = chart["synthesis"]
    out.append({
        "text": (f"{name}'s natal chart is dominantly {s['dominant_element']} "
                 f"by element ({s['elements']}) and {s['dominant_modality']} "
                 f"by modality ({s['modalities']}), counting Sun through Pluto."),
        "metadata": {"source": SOURCE_TAG, "kind": "synthesis"},
    })
    return out


def post_to_hippocampus(payloads: list[dict], user_id: str) -> None:
    import urllib.request
    url = os.environ.get("HIPPOCAMPUS_URL", "http://127.0.0.1:54321") + "/memories"
    api_key = os.environ.get("HIPPOCAMPUS_API_KEY", "")
    if not api_key:
        # Try loading from ~/.config/hippocampus.env
        env_path = os.path.expanduser("~/.config/hippocampus.env")
        if os.path.exists(env_path):
            for line in open(env_path):
                line = line.strip()
                if line.startswith("HIPPOCAMPUS_API_KEY="):
                    api_key = line.split("=", 1)[1]
                if line.startswith("HIPPOCAMPUS_URL="):
                    url = line.split("=", 1)[1].rstrip("/") + "/memories"
    if not api_key:
        sys.exit("HIPPOCAMPUS_API_KEY not set and not in ~/.config/hippocampus.env")
    for i, p in enumerate(payloads, 1):
        body = json.dumps({"user_id": user_id, "text": p["text"],
                           "metadata": p["metadata"]}).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-API-Key", api_key)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        mid = data.get("memory", {}).get("id", "?")
        kind = p["metadata"].get("kind")
        print(f"[{i}/{len(payloads)}] posted ({kind}) id={mid}")


def parse_dob(s: str) -> tuple[int, int, int]:
    """Parse YYYY-MM-DD into (year, month, day)."""
    y, m, d = s.split("-")
    return int(y), int(m), int(d)


def parse_time(s: str) -> tuple[int, int]:
    """Parse HH:MM (24h) into (hour, minute)."""
    h, mn = s.split(":")
    return int(h), int(mn)


def main():
    ap = argparse.ArgumentParser(
        description="Compute a natal chart and write memory payloads to sacred brain.",
    )
    ap.add_argument("--user-id", required=True,
                    help="sacred-brain user_id to write memories under (e.g. david, sam, mel)")
    ap.add_argument("--name", required=True,
                    help="Person's name as it should appear in memory text (e.g. 'David')")
    ap.add_argument("--dob", required=True,
                    help="Date of birth, YYYY-MM-DD (e.g. 1976-04-22)")
    ap.add_argument("--time", required=True,
                    help="Local birth time, HH:MM 24h (e.g. 12:19)")
    ap.add_argument("--place", required=True,
                    help="Birth city (e.g. Melbourne)")
    ap.add_argument("--country", required=True,
                    help="ISO 3166-1 alpha-2 country code (e.g. AU)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print payloads, do not POST")
    ap.add_argument("--post", action="store_true", help="POST to Hippocampus")
    ap.add_argument("--geonames-username", default=os.environ.get("KERYKEION_GEONAMES_USERNAME"),
                    help="Geonames username (recommended; default is shared and rate-limited)")
    args = ap.parse_args()
    if not args.dry_run and not args.post:
        ap.error("specify --dry-run or --post")

    year, month, day = parse_dob(args.dob)
    hour, minute = parse_time(args.time)
    who = {
        "user_id": args.user_id,
        "name": args.name,
        "dob": args.dob,
        "time": args.time,
        "place": args.place,
        "country": args.country,
    }

    kwargs = {}
    if args.geonames_username:
        kwargs["geonames_username"] = args.geonames_username
    subject = AstrologicalSubject(
        args.name, year, month, day, hour, minute, args.place, args.country, **kwargs
    )
    chart = build_chart(subject, who)
    payloads = memory_payloads(chart, who)

    if args.dry_run:
        for i, p in enumerate(payloads, 1):
            print(f"--- payload {i}/{len(payloads)} (kind={p['metadata'].get('kind')}) ---")
            print(p["text"])
            print(f"metadata: {json.dumps(p['metadata'])}")
            print()
        return
    post_to_hippocampus(payloads, args.user_id)


if __name__ == "__main__":
    main()
