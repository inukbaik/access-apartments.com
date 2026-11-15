"""Visual evidence for a listing: floor plans with every doorway marked pass/fail, and a photo of each
failing doorway rendered from the nearest Matterport panorama that can see it.

    .venv/bin/python -m finder.evidence yzUpnSvCqVR        # writes out/evidence/<sid>/

Geometry: wall edges have two vertices; an opening sits at `relativeCenter` (0..1) along its edge.
Panoramas share that x/y frame. A skybox's faces are in the panorama's own frame; `rotation`
(a quaternion, z up) turns them into the model frame. Face convention checked on test doors:
faces 1..4 go around the horizon turning right, face 1 looks along local +y (FACE1_DEG = 90), and
the quaternion maps model -> panorama directions as R^T applied to row vectors (rays @ R.T).
Checked by aiming at doorways 0.5 m from a panorama: within about 15 degrees.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from mp_common import graph  # noqa: E402

from finder.checks import DOOR_MIN_IN, DOOR_PLAUSIBLE_MIN_IN, M_TO_IN  # noqa: E402

CACHE = "cache/evidence"
OUT = "out/evidence"
FACE1_DEG = 90  # local direction of skybox face 1
VIEW_MIN_M, VIEW_MAX_M = 0.8, 5.0  # how far a panorama may be from the doorway it shows
VIEW_BEST_M = 2.2  # preferred distance: the whole door frame fits in the view
FOV = 100  # wide, so the doorway is in view even when its mapped position is a little off

QUERY = """query Evidence($id: ID!) { model(id: $id) { id name
  floors { id label edges { id type vertices { position { x y } }
                            openings { id type width relativeCenter } } }
  panoLocations { id label position { x y z } rotation { x y z w } anchor { floor { id } }
                  skybox(resolution: "2k") { status children } }
} }"""


class EvidenceError(Exception):
    pass


# ------------------------------------------------------------------ data
def fetch(sid, refresh=False):
    """Geometry + panorama poses (cached JSON) and skybox faces (cached JPEGs)."""
    path = os.path.join(CACHE, f"{sid}.json")
    if not refresh and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    data, errors = graph(QUERY, {"id": sid})
    model = (data or {}).get("model")
    if errors or not model:
        raise EvidenceError(f"{sid}: API returned no model. errors={json.dumps(errors)[:300] if errors else None}")
    os.makedirs(os.path.join(CACHE, "sky"), exist_ok=True)
    jobs = []  # signed links expire within minutes: download now, in parallel
    for p in model["panoLocations"]:
        sky = p.pop("skybox", None) or {}
        urls = sky.get("children") or []
        p["has_sky"] = sky.get("status") == "available" and len(urls) >= 5
        if p["has_sky"]:
            jobs += [(_face_path(sid, p["id"], i), u) for i, u in enumerate(urls[:6])]
    with ThreadPoolExecutor(16) as ex:
        failed = [p for p, ok in zip(jobs, ex.map(_download, jobs)) if not ok]
    if failed:
        raise EvidenceError(f"{sid}: {len(failed)} panorama images failed to download; retry with --refresh")
    with open(path, "w") as f:
        json.dump(model, f)
    return model


def _face_path(sid, pano_id, i):
    return os.path.join(CACHE, "sky", f"{sid}_{pano_id}_f{i}.jpg")


def _download(job):
    path, url = job
    if os.path.exists(path) and os.path.getsize(path):
        return True
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except requests.RequestException:
        return False
    with open(path, "wb") as f:
        f.write(r.content)
    return True


def _xy(p):
    return np.array([p["x"], p["y"]], dtype=float)


def doorways(model):
    """Every mapped doorway: floor, center, width and the same pass/fail rule as checks.check_door."""
    out = []
    for floor in model.get("floors") or []:
        for e in floor.get("edges") or []:
            vs = e.get("vertices") or []
            if len(vs) != 2:
                continue
            a, b = _xy(vs[0]["position"]), _xy(vs[1]["position"])
            for o in e.get("openings") or []:
                if o.get("type") != "doorway" or not o.get("width"):
                    continue
                w = o["width"] * M_TO_IN
                status = ("bad measurement" if w < DOOR_PLAUSIBLE_MIN_IN
                          else "fail" if w < DOOR_MIN_IN else "pass")
                t = o.get("relativeCenter")
                t = 0.5 if t is None else t
                out.append({"id": o["id"], "edge": e["id"], "floor": floor["id"], "floor_label": floor["label"],
                            "center": (a + t * (b - a)).tolist(), "wall": [a.tolist(), b.tolist()],
                            "width_in": round(w, 1), "status": status})
    return out


# ------------------------------------------------------------------ floor plans
STATUS_COLOR = {"pass": (46, 158, 79), "fail": (208, 64, 52), "bad measurement": (150, 150, 150)}


def floor_plan(model, floor, doors, scale=60, pad=0.8):
    """PIL image of one floor: walls in black, doorways as colored dots with their width."""
    pts = [_xy(v["position"]) for e in floor["edges"] for v in e["vertices"]]
    if not pts:
        return None
    pts = np.array(pts)
    lo, hi = pts.min(0) - pad, pts.max(0) + pad
    w, h = ((hi - lo) * scale).astype(int)
    img = Image.new("RGB", (int(w), int(h)), "white")
    d = ImageDraw.Draw(img)
    px = lambda p: (float((p[0] - lo[0]) * scale), float((hi[1] - p[1]) * scale))  # noqa: E731
    for e in floor["edges"]:
        a, b = (px(_xy(v["position"])) for v in e["vertices"])
        d.line([a, b], fill=(30, 30, 30) if e["type"] == "wall" else (170, 170, 170), width=4)
    for dr in doors:
        if dr["floor"] != floor["id"]:
            continue
        x, y = px(dr["center"])
        c = STATUS_COLOR[dr["status"]]
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=c, outline="white", width=2)
        d.text((x + 11, y - 7), f'{dr["width_in"]:.0f}"', fill=c)
    return img


# ------------------------------------------------------------------ door photos
def _rot(q):
    x, y, z, w = q["x"], q["y"], q["z"], q["w"]
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def render_view(faces, rotation, yaw_deg, fov=FOV, size=800):
    """Perspective view looking along model-frame yaw (degrees from +x, counter-clockwise), level."""
    f = np.tan(np.radians(fov) / 2)
    j, i = np.meshgrid(np.linspace(-f, f, size), np.linspace(f, -f, size))
    yaw = np.radians(yaw_deg)
    fwd, right, up = np.array([np.cos(yaw), np.sin(yaw), 0]), np.array([np.sin(yaw), -np.cos(yaw), 0]), np.array([0, 0, 1.0])
    rays = (fwd + j[..., None] * right + i[..., None] * up).reshape(-1, 3)
    loc = rays @ _rot(rotation).T  # model frame -> panorama frame (row vectors)
    out = np.zeros((len(loc), 3), np.uint8)
    H, W = faces[1].shape[:2]
    best = np.full(len(loc), -np.inf)
    for k in range(4):
        c = np.radians(FACE1_DEG - 90 * k)
        fk, rk = np.array([np.cos(c), np.sin(c), 0]), np.array([np.sin(c), -np.cos(c), 0])
        dk = loc @ fk
        sel = dk > best
        best[sel] = dk[sel]
        u = (loc[sel] @ rk) / dk[sel]
        v = -loc[sel, 2] / dk[sel]
        cols = np.clip(((u + 1) / 2 * W).astype(int), 0, W - 1)
        rows = np.clip(((v + 1) / 2 * H).astype(int), 0, H - 1)
        out[sel] = faces[k + 1][rows, cols]
    return Image.fromarray(out.reshape(size, size, 3))


def _mark_door(img, door, pos, yaw_deg, fov=FOV):
    """The view is aimed at the doorway's mapped center; the page's caption gives the width. No overlay:
    door positions in the scan are approximate, so marks on the photo would overstate the precision."""
    return


def _crosses(p, q, a, b):
    """Do segments p-q and a-b properly intersect?"""
    def side(o, s, t):
        return np.sign((s[0] - o[0]) * (t[1] - o[1]) - (s[1] - o[1]) * (t[0] - o[0]))
    return side(p, q, a) * side(p, q, b) < 0 and side(a, b, p) * side(a, b, q) < 0


def best_pano(model, door):
    """Closest panorama on the door's floor, 0.8-5 m away, whose line of sight to the doorway
    crosses no other wall. Prefers looking at the door face-on. None if no panorama qualifies."""
    c = np.array(door["center"])
    a, b = (np.array(v) for v in door["wall"])
    normal = np.array([-(b - a)[1], (b - a)[0]]) / (np.linalg.norm(b - a) or 1)
    floor = next(f for f in model["floors"] if f["id"] == door["floor"])
    walls = [(_xy(e["vertices"][0]["position"]), _xy(e["vertices"][1]["position"]))
             for e in floor["edges"] if e["id"] != door["edge"] and len(e["vertices"]) == 2]
    best = None
    for p in model["panoLocations"]:
        if not p.get("has_sky") or ((p.get("anchor") or {}).get("floor") or {}).get("id") != door["floor"]:
            continue
        pos = _xy(p["position"])
        v = c - pos
        dist = np.linalg.norm(v)
        if not VIEW_MIN_M <= dist <= VIEW_MAX_M or any(_crosses(pos, c, wa, wb) for wa, wb in walls):
            continue
        facing = abs(np.dot(v / dist, normal))  # 1 = straight at the door
        score = (abs(dist - VIEW_BEST_M) + 0.5) * (2 - facing)
        if best is None or score < best[0]:
            best = (score, p, dist)
    return best


def door_photo(sid, model, door):
    pick = best_pano(model, door)
    if not pick:
        return None, None
    _, p, dist = pick
    faces = [np.asarray(Image.open(_face_path(sid, p["id"], i)).convert("RGB")) for i in range(6)]
    pos = _xy(p["position"])
    v = np.array(door["center"]) - pos
    yaw = np.degrees(np.arctan2(v[1], v[0]))
    img = render_view(faces, p["rotation"], yaw)
    _mark_door(img, door, pos, yaw)
    return img, {"pano": p["id"], "pano_label": p["label"], "distance_m": round(float(dist), 1)}


# ------------------------------------------------------------------ listing photo
THUMB_QUERY = """query Thumb($id: ID!) { model(id: $id) {
  panoLocations { id label skybox(resolution: "2k") { status children } } } }"""


def thumbnail(sid):
    """A photo for the listing row: one horizon face of the scan's first panorama (JPEG path)."""
    path = os.path.join(OUT, sid, "thumb.jpg")
    if os.path.exists(path):
        return path
    data, errors = graph(THUMB_QUERY, {"id": sid})
    panos = [p for p in ((data or {}).get("model") or {}).get("panoLocations") or []
             if (p.get("skybox") or {}).get("status") == "available" and len(p["skybox"].get("children") or []) >= 5]
    if not panos:
        raise EvidenceError(f"{sid}: no panorama available. errors={json.dumps(errors)[:200] if errors else None}")
    panos.sort(key=lambda p: int(p["label"]) if str(p.get("label", "")).isdigit() else 10 ** 6)
    url = panos[0]["skybox"]["children"][1]
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.open(__import__("io").BytesIO(r.content)).convert("RGB")
    img.thumbnail((480, 480))
    img.save(path, quality=82)
    return path


# ------------------------------------------------------------------ report
def build(sid, refresh=False, out_dir=OUT, photos="fail"):
    """Write plans + door photos to out/evidence/<sid>/ and return a JSON-able summary.
    photos: "fail" (failing and bad-measurement doors) or "all"."""
    model = fetch(sid, refresh)
    doors = doorways(model)
    d = os.path.join(out_dir, sid)
    os.makedirs(d, exist_ok=True)
    plans = []
    for floor in model.get("floors") or []:
        if not any(dr["floor"] == floor["id"] for dr in doors) and not floor.get("edges"):
            continue
        img = floor_plan(model, floor, doors)
        if img:
            name = f"plan_{floor['label'].replace(' ', '_')}.png"
            img.save(os.path.join(d, name))
            plans.append({"floor": floor["label"], "image": name})
    for n, dr in enumerate(doors):
        dr["photo"] = None
        if photos == "all" or dr["status"] != "pass":
            img, info = door_photo(sid, model, dr)
            if img:
                name = f"door_{n}.jpg"
                img.save(os.path.join(d, name), quality=85)
                dr["photo"], dr["photo_from"] = name, info
    floors = [{"id": f["id"], "label": f["label"],
               "walls": [[*_xy(e["vertices"][0]["position"]), *_xy(e["vertices"][1]["position"])]
                         for e in f.get("edges") or [] if len(e.get("vertices") or []) == 2 and e.get("type") == "wall"]}
              for f in model.get("floors") or []]
    floors = [f for f in floors if f["walls"]]
    summary = {"sid": sid, "name": model.get("name"), "photos": photos, "plans": plans, "floors": floors, "doors": doors,
               "note": "Door widths come from the scan's mapped openings and may include the frame. "
                       "Photos are rendered from the nearest panorama that can see the doorway."}
    with open(os.path.join(d, "evidence.json"), "w") as f:
        json.dump(summary, f, indent=1)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sid", nargs="+", help="Matterport model id(s)")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--all-photos", action="store_true", help="photograph passing doors too")
    a = ap.parse_args()
    for sid in a.sid:
        s = build(sid, a.refresh, photos="all" if a.all_photos else "fail")
        n = {k: sum(dr["status"] == k for dr in s["doors"]) for k in STATUS_COLOR}
        shot = sum(bool(dr["photo"]) for dr in s["doors"])
        print(f"{sid} {s['name']}: {len(s['plans'])} floor plans, doors {n}, {shot} photos -> {OUT}/{sid}/")


if __name__ == "__main__":
    main()
