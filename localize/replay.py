"""Replay a saved walk (server --save-frames) through the locator, to retune the rules offline.

    python -m localize.replay data/frames/phone-g5e9pv                    # current rules
    python -m localize.replay data/frames/phone-g5e9pv --min-margin 0.03 --quiet
    python -m localize.replay data/frames/phone-g5e9pv --compare           # vs. what the live run said

Frames are fed in at their saved timestamps. "New walk" taps aren't saved, so a reset is assumed
wherever the live run restarted at 1 frame less than MAX_AGE_S after the previous frame.
Per-frame scores are cached in cache/localize/, so trying other cutoffs takes about a second.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from localize import locator as L
from localize.index import CACHE, DEFAULT_EMBED, DEFAULT_MODEL, lt, load_or_build


def load_walk(folder):
    jsons = sorted(Path(folder).glob("*.json"), key=lambda p: float(p.name.split("_")[0]))
    if not jsons:
        raise SystemExit(f"no saved frames in {folder} (run the server with --save-frames)")
    times = [float(p.name.split("_")[0]) for p in jsons]
    live = [json.loads(p.read_text()) for p in jsons]
    resets = {k for k in range(1, len(jsons))
              if live[k]["frames"] == 1 and times[k] - times[k - 1] < L.MAX_AGE_S}
    return jsons, times, live, resets


def frame_scores(loc, jsons, cache_file):
    if cache_file.exists():
        z = np.load(cache_file)
        if len(z["scores"]) == len(jsons):
            return z["scores"], z["headings"]
    out = [loc.score_image(Image.open(p.with_suffix(".jpg"))) for p in jsons]
    scores, headings = np.array([o[0] for o in out]), np.array([o[1] for o in out])
    np.savez(cache_file, scores=scores, headings=headings)
    return scores, headings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="data/frames/<session>")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--embed-model", default=DEFAULT_EMBED)
    d = L.Thresholds()
    for name in ("min_score", "min_margin", "min_agree", "min_frame_score"):
        ap.add_argument("--" + name.replace("_", "-"), type=float, default=getattr(d, name))
    ap.add_argument("--min-frames", type=int, default=d.min_frames)
    ap.add_argument("--quiet", action="store_true", help="summary only")
    ap.add_argument("--compare", action="store_true", help="also show the live answer per frame")
    a = ap.parse_args()

    embedder = lt.Embedder(a.embed_model)
    index = load_or_build(a.model, a.embed_model, embedder=embedder)
    th = L.Thresholds(a.min_score, a.min_margin, a.min_agree, a.min_frames, a.min_frame_score)
    loc = L.Locator(index, embedder, th)
    jsons, times, live, resets = load_walk(a.folder)
    scores, headings = frame_scores(loc, jsons, CACHE / f"replay_{Path(a.folder).name}_{Path(a.embed_model).name}.npz")

    counts = {}
    for k, p in enumerate(jsons):
        if k in resets:
            loc.reset("replay")
        loc.score_image = lambda img, k=k: (scores[k], headings[k])  # reuse the cached scores
        r = loc.locate(None, session="replay", now=times[k])
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        if a.quiet:
            continue
        g, lv = r["best_guess"], live[k]
        line = (f"#{k:<3} {'R' if k in resets else ' '} {r['status']:7s} spot {g['label']:>3} {g['floor']:8s} "
                f"h{g['heading_deg']:<3} score {r['score']:.3f} margin {r['margin']:+.3f} agree {r['agreement']:.0%}")
        if a.compare:
            line += f"   live: {lv['status']:7s} {lv['best_guess']['label']:>3}"
        print(line + (f"   ({r['reason']})" if r.get("reason") else ""))
    print(f"{len(jsons)} frames, resets at {sorted(resets)}: " +
          ", ".join(f"{s} {n}" for s, n in sorted(counts.items())))


if __name__ == "__main__":
    main()
