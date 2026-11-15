"""Tiny Vexcel client: roof height of the building that contains a point.
GET /v2/property/extract?wkt=POINT(lon lat)&srid=4326&include=precomputed,calculated. Key from
VEXCEL_API_KEY (env or .env). Results (ok and "no data") are cached in cache/finder/vexcel/.

Wrong-building guard (select_height): only ortho captures, newest date, and only the structure whose
footprint contains the point. No containing structure, or an implausible height = unavailable.
"""
import json
import os
import re
import time

import requests
from dotenv import dotenv_values

BASE = "https://api.vexcelgroup.com/v2"
CACHE_DIR = "cache/finder/vexcel"
TIMEOUT = 20
MIN_H, MAX_H = 2.5, 300.0
_state = {"down": False, "calls": 0}


class VexcelError(RuntimeError):
    pass


def _key():
    return dotenv_values(".env").get("VEXCEL_API_KEY") or os.environ.get("VEXCEL_API_KEY")


def _parse_wkt(wkt):
    """WKT POLYGON / MULTIPOLYGON -> list of polygons, each a list of rings of (lon, lat)."""
    s = wkt.strip().upper()
    nums = lambda t: [tuple(map(float, p.split()[:2])) for p in t.split(",")]  # noqa: E731
    rings = [nums(r) for r in re.findall(r"\(([^()]+)\)", wkt)]
    if s.startswith("MULTIPOLYGON"):
        out, i = [], 0
        for poly in re.findall(r"\(\s*(\([^()]+\)(?:\s*,\s*\([^()]+\))*)\s*\)", wkt):
            n = len(re.findall(r"\([^()]+\)", poly))
            out.append(rings[i:i + n])
            i += n
        return out
    if s.startswith("POLYGON"):
        return [rings]
    return []


def _in_ring(x, y, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def contains(wkt, lat, lon):
    """Ray casting; the first ring of each polygon is the outline, the others are holes."""
    for rings in _parse_wkt(wkt):
        if rings and _in_ring(lon, lat, rings[0]) and not any(_in_ring(lon, lat, h) for h in rings[1:]):
            return True
    return False


def _get(d, dotted):
    """Value of a dotted key. The API returns flat keys ("metadata.is-ortho-image"); nested dicts work too."""
    if not isinstance(d, dict):
        return None
    if dotted in d:
        return d[dotted]
    head, _, rest = dotted.partition(".")
    return _get(d.get(head), rest) if rest else None


def select_height(resp, lat, lon):
    """Pure: Vexcel property/extract JSON -> {status, height_m, photo_date, collection, reason}."""
    out = {"status": "unavailable", "height_m": None, "photo_date": None, "collection": None, "reason": ""}
    feats = [f for f in (resp or {}).get("features") or []
             if _get(f.get("properties"), "metadata.is-ortho-image") is True]
    if not feats:
        out["reason"] = "no ortho capture"
        return out
    date = lambda f: str(_get(f["properties"], "metadata.ortho-date-estimate") or "")  # noqa: E731
    feat = max(feats, key=date)
    out["photo_date"] = date(feat)[:10] or None
    out["collection"] = _get(feat["properties"], "metadata.collection")
    hit = None
    for s in feat["properties"].get("structures") or []:
        wkt = _get(s, "footprint.wkt") or ""
        if wkt and contains(wkt, lat, lon):
            hit = s
            break
    if hit is None:
        out["reason"] = "no building footprint contains the point"
        return out
    h = _get(hit, "roof-characteristics.height")
    if not isinstance(h, (int, float)) or isinstance(h, bool):
        out["reason"] = "roof height missing"
    elif h < MIN_H or h > MAX_H:
        out["reason"] = f"implausible roof height {h:.1f} m"
    else:
        out.update(status="ok", height_m=round(float(h), 1))
    return out


def calls():
    """Network calls made so far in this process."""
    return _state["calls"]


def _unavail(reason):
    return {"status": "unavailable", "height_m": None, "photo_date": None, "collection": None, "reason": reason}


def building_height(lat, lon, refresh=False):
    key = _key()
    if not key:
        return _unavail("no VEXCEL_API_KEY")
    path = os.path.join(CACHE_DIR, f"{lat:.6f}_{lon:.6f}.json")
    if not refresh and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    if _state["down"]:
        return _unavail("Vexcel unreachable")
    params = {"wkt": f"POINT({lon:.6f} {lat:.6f})", "srid": 4326, "include": "precomputed,calculated"}
    try:
        for attempt in (0, 1):
            _state["calls"] += 1
            r = requests.get(f"{BASE}/property/extract", params=params, headers={"X-API-KEY": key},
                             timeout=TIMEOUT)
            if r.status_code == 429 and attempt == 0:
                time.sleep(2)
                continue
            break
        if r.status_code == 404:
            res = _unavail("no Vexcel property data here")
        elif r.status_code != 200:
            raise VexcelError(f"Vexcel HTTP {r.status_code}: {r.text[:120]}")
        else:
            res = select_height(r.json(), lat, lon)
    except (requests.RequestException, ValueError, VexcelError) as e:
        _state["down"] = True
        print(f"  Vexcel failed ({e}); skipping Vexcel for the rest of this run")
        return _unavail("Vexcel unreachable")
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f)
    return res
