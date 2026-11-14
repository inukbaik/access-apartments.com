"""Download every panorama of a Matterport model as 6 skybox faces, plus positions.

Usage:  python3 scripts/fetch_venue_panos.py [MODEL_ID] [RESOLUTION]
        defaults: P3S6VUTP3qB (Rabinowitz Hall), 2k
Needs MATTERPORT_API_KEY / MATTERPORT_API_TOKEN in the environment (source .env).
Output: data/venue/<MODEL_ID>/<pano_id>/skybox{0..5}.jpg and data/venue/<MODEL_ID>/panos.json
Signed download links expire about an hour after the query, so the script downloads right away.
"""
import base64
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.matterport.com/api/models/graph"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "P3S6VUTP3qB"
RES = sys.argv[2] if len(sys.argv) > 2 else "2k"
OUT = os.path.join("data", "venue", MODEL)

key, token = os.environ.get("MATTERPORT_API_KEY"), os.environ.get("MATTERPORT_API_TOKEN")
if not key or not token:
    sys.exit("MATTERPORT_API_KEY / MATTERPORT_API_TOKEN not set. Run: set -a; source .env; set +a")

query = """{ model(id: "%s") { name panoLocations { id label
  position { x y z } rotation { x y z w }
  skybox(resolution: "%s") { status children } } } }""" % (MODEL, RES)
req = urllib.request.Request(
    API,
    data=json.dumps({"query": query}).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": "Basic " + base64.b64encode(f"{key}:{token}".encode()).decode(),
    },
)
with urllib.request.urlopen(req) as r:
    resp = json.load(r)
if resp.get("errors"):
    sys.exit(f"Model API error: {[e.get('message') for e in resp['errors']]}")
model = resp["data"]["model"]
if not model:
    sys.exit(f"Model {MODEL} not returned (no access?)")

jobs, meta = [], []
for p in model["panoLocations"]:
    sky = p.get("skybox") or {}
    faces = sky.get("children") or []
    if len(faces) != 6:
        print(f"WARNING: pano {p['id']} has {len(faces)} skybox faces (status {sky.get('status')}); skipped")
        continue
    d = os.path.join(OUT, p["id"])
    os.makedirs(d, exist_ok=True)
    jobs += [(url, os.path.join(d, f"skybox{i}.jpg")) for i, url in enumerate(faces)]
    meta.append({k: p[k] for k in ("id", "label", "position", "rotation")})


def fetch(job):
    url, path = job
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return None
    try:
        urllib.request.urlretrieve(url, path)
        return None
    except Exception as e:  # report every failed face, never skip silently
        return f"{path}: {e}"


with ThreadPoolExecutor(8) as ex:
    errors = [e for e in ex.map(fetch, jobs) if e]
with open(os.path.join(OUT, "panos.json"), "w") as f:
    json.dump({"model": MODEL, "name": model["name"], "resolution": RES, "panos": meta}, f, indent=1)

print(f"{model['name']}: {len(meta)} panoramas, {len(jobs) - len(errors)}/{len(jobs)} faces -> {OUT}")
if errors:
    print("FAILED downloads:\n  " + "\n  ".join(errors))
    sys.exit(1)
