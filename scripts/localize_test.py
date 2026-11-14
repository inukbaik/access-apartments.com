#!/usr/bin/env python3
"""Indoor localization smoke test: can a photo tell us where we are in the venue scan?

Builds an image index from the venue's Matterport panoramas (8 views per scan position,
45 degrees apart), embeds everything with DINOv2, and matches your photos against it.

Pass criterion (PROJECT_CONTEXT.md, Phase 0): 3 of 5 photos match the right spot.
You judge "right" by looking at the side by side images it saves.

Usage:
  # take ~5 photos around the hall (phone or glasses), put them in data/photos/<camera>/
  python scripts/localize_test.py --photos data/photos/phone/
  python scripts/localize_test.py --photos data/photos/phone/ --defurnished      # also index the no furniture view
  python scripts/localize_test.py --photos data/photos/phone/ --ref-dir shots/   # fallback: screenshots of the public tour

Outputs (out/localize/):
  <photo>_matches.jpg   your photo next to its top matches
  map_<photo>.png       top down plot of scan positions with the best match starred (needs matplotlib)
  results.json
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageOps

try:  # iPhone HEIC photos
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
VIEW_SIZE = 448

PANOS_QUERY = """query Panos($id: ID!) { model(id: $id) {
  name
  panoLocations { id label position { x y z } skybox(resolution: "%s") { status children } }
  view(type: "matterport.model.defurnished") { id }
} }"""


# ------------------------------------------------------------ reference views
def download(url, path):
    if path.exists() and path.stat().st_size > 0:
        return path
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    path.write_bytes(r.content)
    return path


def faces_are_reversed(faces):
    """Skybox faces 1..4 go around the horizon. Check which direction they chain:
    in the right order, face i's right edge matches face i+1's left edge."""
    arrs = [np.asarray(f.convert("L"), dtype=np.float32) for f in faces]
    fwd = np.mean([np.abs(arrs[i][:, -1] - arrs[(i + 1) % 4][:, 0]).mean() for i in range(4)])
    rev = np.mean([np.abs(arrs[i][:, 0] - arrs[(i + 1) % 4][:, -1]).mean() for i in range(4)])
    return rev < fwd


def horizon_views(faces):
    """4 horizon faces -> 8 views 45 degrees apart (faces + half/half stitches)."""
    if faces_are_reversed(faces):
        faces = faces[::-1]
    w, h = faces[0].size
    views = []
    for i in range(4):
        views.append((i * 90, faces[i]))
        stitched = Image.new("RGB", (w, h))
        stitched.paste(faces[i].crop((w // 2, 0, w, h)), (0, 0))
        stitched.paste(faces[(i + 1) % 4].crop((0, 0, w // 2, h)), (w // 2, 0))
        views.append((i * 90 + 45, stitched))
    return views


def fetch_model_panos(model_id, resolution):
    from mp_common import graph

    data, errors = graph(PANOS_QUERY % resolution, {"id": model_id})
    model = (data or {}).get("model")
    if not model:
        sys.exit(f"Model {model_id} not reachable with this key: {errors}\n"
                 "Ask #costar-group to add it, or rerun with --ref-dir <tour screenshots>.")
    return model


def build_reference_from_api(model_id, resolution, defurnished, cache):
    model = fetch_model_panos(model_id, resolution)
    print(f"Model '{model['name']}': {len(model['panoLocations'])} panoramas")
    sources = [("scan", model)]
    if defurnished and model.get("view"):
        sources.append(("defurnished", fetch_model_panos(model["view"]["id"], resolution)))

    refs = []
    for tag, m in sources:
        for pano in m["panoLocations"]:
            sky = pano.get("skybox") or {}
            urls = sky.get("children") or []
            if sky.get("status") != "available" or len(urls) < 5:
                continue
            faces = []
            for i in range(1, 5):  # 0 = up, 1..4 = horizon, 5 = down
                p = cache / f"{model_id}_{tag}_{pano['id']}_f{i}.jpg"
                faces.append(Image.open(download(urls[i], p)).convert("RGB"))
            for heading, img in horizon_views(faces):
                refs.append({"pano": pano["id"], "label": pano.get("label"), "source": tag,
                             "heading": heading, "pos": pano.get("position"), "image": img})
        print(f"  {tag}: {len(refs)} views so far")
    return refs


def build_reference_from_dir(ref_dir):
    refs = []
    for p in sorted(Path(ref_dir).iterdir()):
        if p.suffix.lower() in IMG_EXT:
            refs.append({"pano": p.stem, "label": p.stem, "source": "screenshot",
                         "heading": None, "pos": None, "image": Image.open(p).convert("RGB")})
    print(f"Loaded {len(refs)} reference screenshots from {ref_dir}")
    return refs


# ------------------------------------------------------------------ embedding
class Embedder:
    def __init__(self, model_name):
        import torch
        from transformers import AutoImageProcessor, AutoModel

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else (
            "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu")
        self.proc = AutoImageProcessor.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device).eval()
        print(f"Embedding with {model_name} on {self.device}")

    def __call__(self, images, batch=16):
        out = []
        with self.torch.no_grad():
            for i in range(0, len(images), batch):
                inputs = self.proc(images=images[i:i + batch], return_tensors="pt").to(self.device)
                hidden = self.model(**inputs).last_hidden_state
                feat = self.torch.cat([hidden[:, 0], hidden[:, 1:].mean(1)], dim=1)  # CLS + mean patch
                feat = self.torch.nn.functional.normalize(feat, dim=1)
                out.append(feat.cpu().numpy())
        return np.concatenate(out)


def load_photo(path):
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = img.size  # center crop to a square, like the reference views
    s = min(w, h)
    return img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))


# ------------------------------------------------------------------- outputs
def thumb(img, caption, size=VIEW_SIZE):
    t = img.copy()
    t.thumbnail((size, size))
    canvas = Image.new("RGB", (size, size + 28), "white")
    canvas.paste(t, ((size - t.width) // 2, 0))
    ImageDraw.Draw(canvas).text((6, size + 6), caption[:60], fill="black")
    return canvas


def save_montage(photo_img, photo_name, matches, refs, out_dir):
    tiles = [thumb(photo_img, f"QUERY {photo_name}")]
    for m in matches:
        r = refs[m["ref_index"]]
        cap = f"#{m['rank']} pano {r['label']} {r['source']} h{r['heading']} s={m['score']:.3f}"
        tiles.append(thumb(r["image"], cap))
    sheet = Image.new("RGB", (VIEW_SIZE * len(tiles), VIEW_SIZE + 28), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * VIEW_SIZE, 0))
    path = out_dir / f"{Path(photo_name).stem}_matches.jpg"
    sheet.save(path, quality=88)
    return path


def save_map(refs, best, photo_name, out_dir):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    pts = {r["pano"]: r["pos"] for r in refs if r["pos"]}
    if not pts:
        return None
    xs = [p["x"] for p in pts.values()]
    ys = [p["y"] for p in pts.values()]
    zs = [p["z"] for p in pts.values()]
    fig, ax = plt.subplots(figsize=(7, 6))
    sc = ax.scatter(xs, ys, c=zs, cmap="viridis", s=18)
    fig.colorbar(sc, label="height z (m), separates floors")
    b = pts.get(best["pano"])
    if b:
        ax.scatter([b["x"]], [b["y"]], marker="*", s=400, c="red", edgecolors="black",
                   label=f"best: pano {best['label']}")
        ax.legend()
    ax.set_aspect("equal")
    ax.set_title(f"{photo_name}: scan positions (top down)")
    path = out_dir / f"map_{Path(photo_name).stem}.png"
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return path


# ----------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="P3S6VUTP3qB", help="venue Matterport id")
    ap.add_argument("--photos", required=True, help="folder of query photos")
    ap.add_argument("--ref-dir", help="use screenshots in this folder instead of the API")
    ap.add_argument("--resolution", default="2k", choices=["2k", "4k"])
    ap.add_argument("--defurnished", action="store_true", help="also index the furniture removed view")
    ap.add_argument("--embed-model", default="facebook/dinov2-small",
                    help="e.g. facebook/dinov2-base for better (slower) matching")
    ap.add_argument("--topk", type=int, default=3)
    ap.add_argument("--out", default="out/localize")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = Path("cache/skybox")
    cache.mkdir(parents=True, exist_ok=True)

    refs = (build_reference_from_dir(args.ref_dir) if args.ref_dir
            else build_reference_from_api(args.model, args.resolution, args.defurnished, cache))
    if not refs:
        sys.exit("No reference images.")

    photos = sorted(p for p in Path(args.photos).iterdir() if p.suffix.lower() in IMG_EXT)
    if not photos:
        sys.exit(f"No photos in {args.photos}")

    embed = Embedder(args.embed_model)
    ref_feats = embed([r["image"] for r in refs])
    photo_imgs = [load_photo(p) for p in photos]
    photo_feats = embed(photo_imgs)

    results = []
    for photo, img, feat in zip(photos, photo_imgs, photo_feats):
        sims = ref_feats @ feat
        # best view per scan position, then rank positions
        best_per_pano = {}
        for i in np.argsort(-sims):
            key = refs[i]["pano"]
            if key not in best_per_pano:
                best_per_pano[key] = i
            if len(best_per_pano) >= args.topk:
                break
        matches = [{"rank": r + 1, "ref_index": int(i), "pano": refs[i]["pano"], "label": refs[i]["label"],
                    "source": refs[i]["source"], "heading": refs[i]["heading"], "score": float(sims[i]),
                    "pos": refs[i]["pos"]}
                   for r, i in enumerate(best_per_pano.values())]
        margin = matches[0]["score"] - matches[1]["score"] if len(matches) > 1 else None
        montage = save_montage(img, photo.name, matches, refs, out_dir)
        save_map(refs, matches[0], photo.name, out_dir)
        results.append({"photo": photo.name, "matches": matches, "margin": margin})

        top = matches[0]
        margin_txt = f"{margin:.3f}" if margin is not None else "n/a"
        print(f"{photo.name:<28} -> pano {top['label']} ({top['source']}, heading {top['heading']}) "
              f"score {top['score']:.3f}  margin {margin_txt}")
        print(f"{'':<28}    see {montage}")

    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {out_dir}/results.json")
    print("Open the *_matches.jpg files and count how many top matches are the right spot.")
    print("Pass = 3 of 5. A small margin (< ~0.02) means the match is a coin flip.")


if __name__ == "__main__":
    main()
