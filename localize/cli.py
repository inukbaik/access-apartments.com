"""Try the locator on photos, without a phone.

    python -m localize.cli data/photos/glasses/*.jpg              # each photo on its own
    python -m localize.cli --sequence data/photos/glasses/*.jpg   # photos as one walk (voting + prior)
    python -m localize.cli --scores data/photos/glasses/*.jpg     # also print raw top-3 positions
"""
import argparse
import json
from pathlib import Path

from PIL import Image

from localize.index import DEFAULT_EMBED, DEFAULT_MODEL, lt, load_or_build
from localize.locator import Locator, Thresholds

try:  # iPhone HEIC photos
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photos", nargs="+")
    ap.add_argument("--sequence", action="store_true", help="treat photos as consecutive frames of one walk")
    ap.add_argument("--scores", action="store_true", help="print the raw top 3 positions per photo")
    ap.add_argument("--json", action="store_true", help="print full JSON results")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--embed-model", default=DEFAULT_EMBED)
    ap.add_argument("--min-score", type=float, default=Thresholds.min_score)
    ap.add_argument("--floor", help='restrict to one floor, e.g. "Floor 3"')
    ap.add_argument("--min-margin", type=float, default=Thresholds.min_margin)
    a = ap.parse_args()

    embedder = lt.Embedder(a.embed_model)
    index = load_or_build(a.model, a.embed_model, embedder=embedder)
    loc = Locator(index, embedder, Thresholds(min_score=a.min_score, min_margin=a.min_margin))

    for n, path in enumerate(sorted(a.photos)):
        session = "walk" if a.sequence else f"photo{n}"
        r = loc.locate(Image.open(path), session=session, now=float(n) if a.sequence else None,
                       floor=a.floor)
        g = r["best_guess"]
        line = (f"{Path(path).name:30s} {r['status']:7s} pano {g['label']:>3} {g['floor']:8s} "
                f"h{g['heading_deg']:<3} score {r['score']:.3f} margin {r['margin']:+.3f} "
                f"frames {r['frames']} agree {r['agreement']:.0%}"
                + (f" floor? {'/'.join(r['floor_candidates'])}" if r.get("floor_candidates") else ""))
        print(line + (f"   ({r['reason']})" if r.get("reason") else ""))
        if a.scores:
            scores, _ = loc.score_image(Image.open(path))
            top3 = scores.argsort()[::-1][:3]
            print("    top3: " + ", ".join(f"{index.panos[i]['label']}={scores[i]:.3f}" for i in top3))
        if a.json:
            print(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()
