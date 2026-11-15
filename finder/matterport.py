"""Fetch (and cache) the room and opening data the checks need."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from mp_common import graph  # noqa: E402

CACHE_DIR = "cache/finder"

QUERY = """query Screen($id: ID!) { model(id: $id) {
  id name
  rooms { id classifications { label confidence }
          dimensions(units: metric) { areaFloor width depth height }
          boundary { edges { id } } }
  floors { id label edges { id type thickness openings { type label width height lowerElevation } } }
} }"""


class FetchError(Exception):
    pass


def fetch_model(sid, refresh=False):
    """Return the raw `model` dict. Raises FetchError with a clear message on failure."""
    path = os.path.join(CACHE_DIR, f"{sid}.json")
    if not refresh and os.path.exists(path):
        with open(path) as f:
            model = json.load(f)
        rooms = model.get("rooms") or []
        if not rooms or "boundary" in rooms[0]:  # older cache files have no room boundaries: fetch again
            return model
    data, errors = graph(QUERY, {"id": sid})
    model = (data or {}).get("model")
    if errors or not model:
        raise FetchError(f"{sid}: API returned no model. errors={json.dumps(errors)[:300] if errors else None}")
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(model, f)
    return model
