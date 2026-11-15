"""Group units (index rows) into buildings. Pure functions, no I/O.

Priority: street_key of the address, street_key of the name, costar_property_id,
"<building> - <unit>" name prefix (within 50 m), then lat/lon proximity (within 15 m).
When unsure, do not merge: a wrong merge can hide a failing unit behind a passing one.
"""
import re
from typing import Any

import usaddress

from finder.candidates import haversine_km

NAME_RADIUS_M = 50
NEAR_RADIUS_M = 15
KEY_RADIUS_M = 150  # same street_key farther apart than this is a data error: do not merge

_DIRS = {"west": "w", "east": "e", "north": "n", "south": "s", "northwest": "nw", "northeast": "ne",
         "southwest": "sw", "southeast": "se"}
_UNIT_WORDS = {"br", "bd", "bed", "beds", "ba", "bath", "baths", "studio", "sf", "sqft"}
# "1288 3 W 35": usaddress reads the unit "3" as the street and "35" as an occupancy.
_UNIT_BEFORE_DIR = re.compile(r"^(\d+)\s+\d+\s+(" + "|".join(sorted(set(_DIRS) | set(_DIRS.values()), key=len, reverse=True))
                              + r")\.?\s+(\d+)(?:st|nd|rd|th)?(?:\s+[a-z]+\.?)?$", re.I)


def _dir(d):
    d = re.sub(r"[^a-z]", "", d.lower())
    return _DIRS.get(d, d)


def _sub_building(address):
    """The "3" in "1288 3 W 35th Pl": a separate structure at the same street number, or None."""
    m = _UNIT_BEFORE_DIR.match(str(address or "").split(",")[0].strip())
    return m.group(0).split()[1] if m else None


def street_key(text):
    """House number + pre-direction + street name, lowercase; unit, street type and city dropped.
    None unless both a house number and a street name are present (units, "US", "2BR, 1BA" -> None)."""
    text = str(text or "").strip()
    if not text:
        return None
    street_part = text.split(",")[0].strip()
    m = _UNIT_BEFORE_DIR.match(street_part)
    if m:
        return f"{m.group(1)} {_dir(m.group(2))} {m.group(3)}"
    try:
        tags = usaddress.tag(text)[0]
    except usaddress.RepeatedLabelError:
        return None  # ambiguous parse: do not guess
    num = tags.get("AddressNumber", "").strip()
    name = tags.get("StreetName", "").strip().lower()
    if not re.fullmatch(r"\d+", num) or not name:
        return None
    if set(re.findall(r"[a-z]+", name)) & _UNIT_WORDS or re.search(r"\d(?:br|ba|bd|sf)\b", text.lower()):
        return None
    name = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", re.sub(r"[^\w/\s]", " ", name))
    parts = [num + (" " + tags["AddressNumberSuffix"].strip() if tags.get("AddressNumberSuffix") else "")]
    if tags.get("StreetNamePreDirectional"):
        parts.append(_dir(tags["StreetNamePreDirectional"]))
    parts.append(" ".join(name.split()))
    return " ".join(parts)


def name_prefix(name):
    parts = str(name or "").split(" - ")
    return parts[0].strip().lower() if len(parts) > 1 and parts[0].strip() else None


def _dist_m(a, b):
    return haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) * 1000


def _cluster(items, radius_m):
    """Single-linkage clusters: items within radius_m of any member share a cluster."""
    clusters: list[Any] = []
    for it in items:
        near = [c for c in clusters if any(_dist_m(it, m) <= radius_m for m in c)]
        merged = [it]
        for c in near:
            merged += c
            clusters.remove(c)
        clusters.append(merged)
    return clusters


def group_buildings(items):
    """Split items (dicts with address, costar_property_id, name, lat, lon) into buildings.
    Returns a list of lists, each in input order."""
    groups: dict[Any, list[Any]] = {}
    rest: list[Any] = []
    for it in items:
        key = street_key(it.get("address"))
        if key:
            # "1288 1 W 35th Pl" vs "1288 2 W 35th Pl": same street_key, but likely separate
            # structures, so the sub-number stays part of the grouping key (do not merge when unsure).
            key = (key, _sub_building(it.get("address")))
        else:
            key = street_key(it.get("name"))
        pid = str(it.get("costar_property_id") or "").strip()
        if key:
            groups.setdefault(("key", key), []).append(it)
        elif pid:
            groups.setdefault(("pid", pid), []).append(it)
        else:
            rest.append(it)
    out = [g for members in groups.values() for g in _cluster(members, KEY_RADIUS_M)]
    by_prefix: dict[Any, list[Any]] = {}
    loose: list[Any] = []
    for it in rest:
        p = name_prefix(it.get("name"))
        (by_prefix.setdefault(p, []) if p else loose).append(it)
    for members in by_prefix.values():
        out += _cluster(members, NAME_RADIUS_M)
    out += _cluster(loose, NEAR_RADIUS_M)
    order = {id(it): i for i, it in enumerate(items)}
    for g in out:
        g.sort(key=lambda it: order[id(it)])
    return out
