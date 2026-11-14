"""Reference index for a venue: every scan position's horizon views, embedded once and cached.

Build (or rebuild) from the repo root:
    python -m localize.index                 # defaults: P3S6VUTP3qB, 2k, dinov2-small
    python -m localize.index --rebuild

Writes cache/localize/<model>_<embed>.npz (features) and .json (scan positions, floors, neighbors).
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import localize_test as lt  # noqa: E402  (reuse horizon_views, Embedder, load_photo)
from mp_common import graph  # noqa: E402

DEFAULT_MODEL = "P3S6VUTP3qB"  # Rabinowitz Hall
DEFAULT_EMBED = "facebook/dinov2-small"  # dinov2-base gave no gain in Phase 0 and is slower
CACHE = Path("cache")

PANOS_QUERY = """query($id: ID!) { model(id: $id) { name panoLocations {
  id label position { x y z }
  anchor { floor { id label } room { classifications { label } } neighbors }
  skybox(resolution: "%s") { status children } } } }"""


def _paths(model_id, embed_model):
    stem = f"{model_id}_{embed_model.split('/')[-1]}"
    d = CACHE / "localize"
    return d / f"{stem}.npz", d / f"{stem}.json"


def _query(model_id, resolution):
    data, errors = graph(PANOS_QUERY % resolution, {"id": model_id})
    model = (data or {}).get("model")
    if not model:
        sys.exit(f"Model {model_id} not reachable with this key: {errors}")
    return model


def _download_faces(model_id, resolution, tries=3):
    """Download horizon faces 1-4 of every pano into cache/skybox/.

    Signed links expire within minutes, so download in parallel and, on failure (410 Gone),
    re-query for fresh links. Faces already on disk are kept."""
    skydir = CACHE / "skybox"
    skydir.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, tries + 1):
        model = _query(model_id, resolution)
        jobs = []
        for p in model["panoLocations"]:
            sky = p.get("skybox") or {}
            urls = sky.get("children") or []
            if sky.get("status") != "available" or len(urls) < 5:
                continue
            for i in range(1, 5):  # 0 = up, 1..4 = horizon, 5 = down
                path = skydir / f"{model_id}_scan_{p['id']}_f{i}.jpg"
                if not (path.exists() and path.stat().st_size > 0):
                    jobs.append((urls[i], path))

        def fetch(job):
            url, path = job
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            path.write_bytes(r.content)

        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(lambda j: _safe(fetch, j), jobs))
        failed = [e for e in results if e]
        if not failed:
            return model
        print(f"  {len(failed)} of {len(jobs)} faces failed (attempt {attempt}): {failed[0]}")
    sys.exit("Could not download all panorama faces. Rerun; cached faces are kept.")


def _safe(fn, arg):
    try:
        fn(arg)
        return None
    except Exception as e:  # reported by the caller, never swallowed
        return str(e)[:120]


def build(model_id=DEFAULT_MODEL, embed_model=DEFAULT_EMBED, resolution="2k", embedder=None):
    t0 = time.time()
    model = _download_faces(model_id, resolution)
    panos, views, view_pano, view_heading = [], [], [], []
    for p in model["panoLocations"]:
        faces_paths = [CACHE / "skybox" / f"{model_id}_scan_{p['id']}_f{i}.jpg" for i in range(1, 5)]
        if not all(fp.exists() for fp in faces_paths):
            continue
        anchor = p.get("anchor") or {}
        room = (anchor.get("room") or {}).get("classifications") or []
        panos.append({
            "id": p["id"],
            "label": p.get("label"),
            "pos": p["position"],
            "floor": ((anchor.get("floor") or {}).get("label")) or "unknown",
            "room": room[0]["label"] if room else "unknown",
            "neighbors": anchor.get("neighbors") or [],
        })
        faces = [Image.open(fp).convert("RGB") for fp in faces_paths]
        for heading, img in lt.horizon_views(faces):
            views.append(img)
            view_pano.append(len(panos) - 1)
            view_heading.append(heading)

    embedder = embedder or lt.Embedder(embed_model)
    feats = embedder(views)
    npz_path, json_path = _paths(model_id, embed_model)
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(npz_path, feats=feats.astype(np.float32), view_pano=np.array(view_pano),
             view_heading=np.array(view_heading))
    json_path.write_text(json.dumps({"model_id": model_id, "name": model["name"],
                                     "embed_model": embed_model, "resolution": resolution,
                                     "panos": panos}, indent=1))
    print(f"Index: {len(panos)} scan positions, {len(views)} views, {time.time() - t0:.0f}s -> {npz_path}")
    return load(model_id, embed_model)


class Index:
    def __init__(self, meta, feats, view_pano, view_heading):
        self.meta = meta
        self.panos = meta["panos"]
        self.feats = feats
        self.view_pano = view_pano
        self.view_heading = view_heading
        self.pos = np.array([[p["pos"]["x"], p["pos"]["y"], p["pos"]["z"]] for p in self.panos])
        self.floor = [p["floor"] for p in self.panos]
        self.by_id = {p["id"]: i for i, p in enumerate(self.panos)}


def load(model_id=DEFAULT_MODEL, embed_model=DEFAULT_EMBED):
    npz_path, json_path = _paths(model_id, embed_model)
    if not (npz_path.exists() and json_path.exists()):
        return None
    z = np.load(npz_path)
    return Index(json.loads(json_path.read_text()), z["feats"], z["view_pano"], z["view_heading"])


def load_or_build(model_id=DEFAULT_MODEL, embed_model=DEFAULT_EMBED, embedder=None):
    return load(model_id, embed_model) or build(model_id, embed_model, embedder=embedder)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--embed-model", default=DEFAULT_EMBED)
    ap.add_argument("--resolution", default="2k", choices=["2k", "4k"])
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    idx = None if a.rebuild else load(a.model, a.embed_model)
    if idx:
        print(f"Index already built: {len(idx.panos)} scan positions. Use --rebuild to redo it.")
    else:
        build(a.model, a.embed_model, a.resolution)
