"""Frame(s) in -> where you are in the venue scan, or "unknown".

Each frame is compared with every scan position's 8 horizon views (DINOv2, cosine similarity).
A position's score is its best view. Then, per session (one phone):
  1. Average the scores over the last WINDOW frames (multi-frame voting).
  2. Add PRIOR_BONUS to positions within 2 walking edges of the last confident answer.
  3. Answer "ok" only if the top score, the margin over the best position that is NOT nearby,
     and the agreement between frames all pass; otherwise answer "unknown".

Headings are relative to the scan's skybox faces (0/45/.../315), not compass directions.
"""
import time
from collections import deque
from dataclasses import dataclass

import numpy as np
from PIL import ImageOps

from localize.graph import NEAR_M, WalkGraph

WINDOW = 4  # frames voted together
MAX_AGE_S = 10.0  # frames older than this drop out of the vote
PRIOR_S = 30.0  # how long the last confident answer keeps helping
PRIOR_BONUS = 0.02


@dataclass
class Thresholds:
    # Calibrated on the Phase 0 photos (see localize/README.md); retune with more photos.
    min_score: float = 0.75
    min_margin: float = 0.01
    min_agree: float = 0.6


def square_crop(img):
    """Upright, center-cropped square, like the reference views (same as localize_test.load_photo)."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    m = min(w, h)
    return img.crop(((w - m) // 2, (h - m) // 2, (w + m) // 2, (h + m) // 2))


class _Session:
    def __init__(self):
        self.frames = deque(maxlen=WINDOW)  # (time, pano_scores, pano_headings)
        self.last = None  # (time, pano index)


class Locator:
    def __init__(self, index, embedder, thresholds=None):
        self.index = index
        self.embedder = embedder
        self.graph = WalkGraph(index)
        self.th = thresholds or Thresholds()
        self.sessions = {}
        n = len(index.panos)
        self._view_rows = [np.where(index.view_pano == i)[0] for i in range(n)]

    # ------------------------------------------------------------------ scoring
    def score_image(self, img):
        """PIL image -> (per-position best score, per-position best heading)."""
        q = self.embedder([square_crop(img)])[0]
        sims = self.index.feats @ q
        scores = np.empty(len(self._view_rows), dtype=np.float32)
        headings = np.empty(len(self._view_rows), dtype=np.int32)
        for i, rows in enumerate(self._view_rows):
            k = rows[np.argmax(sims[rows])]
            scores[i], headings[i] = sims[k], self.index.view_heading[k]
        return scores, headings

    # ----------------------------------------------------------------- locating
    def reset(self, session="default"):
        self.sessions.pop(session, None)

    def locate(self, img, session="default", now=None, floor=None):
        """`floor` (e.g. "Floor 3") restricts the answer to that floor when the app knows it."""
        now = time.time() if now is None else now
        s = self.sessions.setdefault(session, _Session())
        scores, headings = self.score_image(img)
        s.frames.append((now, scores, headings))
        frames = [f for f in s.frames if now - f[0] <= MAX_AGE_S]

        combined = np.mean([f[1] for f in frames], axis=0)
        boosted = combined.copy()
        if s.last and now - s.last[0] <= PRIOR_S:
            boosted[list(self.graph.reachable_within(s.last[1], hops=2))] += PRIOR_BONUS
        floors = self.index.floor
        if floor is not None:
            if floor not in floors:
                raise ValueError(f"unknown floor {floor!r}; the scan has {sorted(set(floors))}")
            boosted[[i for i, f in enumerate(floors) if f != floor]] = -np.inf

        top = int(np.argmax(boosted))
        # Same spot = close in x/y, on any floor. Rabinowitz Hall's floors look alike, so the
        # usual confusion is "right spot, wrong floor"; that is reported separately below.
        spot = set(self.graph.near_xy(top, NEAR_M)) | self.graph.reachable_within(top, hops=1)
        far = [i for i in range(len(boosted)) if i not in spot and np.isfinite(boosted[i])]
        margin = float(boosted[top] - (boosted[far].max() if far else 0.0))
        agree = float(np.mean([int(np.argmax(f[1])) in spot for f in frames]))
        score = float(combined[top])
        other_floor = [i for i in spot if floors[i] != floors[top] and np.isfinite(boosted[i])]
        floor_margin = float(boosted[top] - boosted[other_floor].max()) if other_floor else None
        floor_known = floor_margin is None or floor_margin >= self.th.min_margin

        reasons = []
        if score < self.th.min_score:
            reasons.append(f"score {score:.3f} < {self.th.min_score}")
        if margin < self.th.min_margin:
            reasons.append(f"margin {margin:.3f} < {self.th.min_margin} (a different spot looks as similar)")
        if len(frames) > 1 and agree < self.th.min_agree:
            reasons.append(f"frames agree {agree:.0%} < {self.th.min_agree:.0%}")

        p = self.index.panos[top]
        result = {
            "status": "unknown" if reasons else "ok",
            "frames": len(frames),
            "score": round(score, 3),
            "margin": round(margin, 3),
            "agreement": round(agree, 2),
            "floor_margin": None if floor_margin is None else round(floor_margin, 3),
            "best_guess": {
                "pano_id": p["id"],
                "label": p["label"],
                "floor": p["floor"] if floor_known else "unknown",
                "room": p["room"],
                "position_m": {k: round(v, 2) for k, v in p["pos"].items()},
                "heading_deg": int(headings[top]),
            },
        }
        if not floor_known:
            result["floor_candidates"] = sorted({floors[i] for i in [top] + other_floor})
        if reasons:
            result["reason"] = "; ".join(reasons)
        elif floor_known:  # only a confident, floor-certain answer steers the next frames
            s.last = (now, top)
        return result
