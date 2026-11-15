"""Pick candidate models near a point from models_index.csv."""
import csv
import math
import os
import sys


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_candidates(index_path, lat, lon, radius_km, limit):
    """Nearest models with coordinates and rooms, within radius_km, sorted by distance."""
    if not os.path.exists(index_path):
        sys.exit(f"Index not found: {index_path}. Download models_index.csv into data/ (see data/README.md).")
    found = []
    with open(index_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rlat, rlon = _float(row.get("lat")), _float(row.get("lon"))
            if rlat is None or rlon is None:
                continue
            rooms = _float(row.get("room_count"))
            if rooms == 0:
                continue
            dist = haversine_km(lat, lon, rlat, rlon)
            if dist > radius_km:
                continue
            found.append({
                "sid": row["sid"], "name": row.get("name"), "address": row.get("address"),
                "city": row.get("city"), "lat": rlat, "lon": rlon, "dist_km": round(dist, 3),
                "costar_property_id": row.get("costar_property_id"),
                "homes_listing_id": row.get("homes_listing_id"),
            })
    found.sort(key=lambda c: c["dist_km"])
    return found[:limit]
