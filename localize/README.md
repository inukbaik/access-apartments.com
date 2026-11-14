# Localize (Part B)

Where am I in the venue scan? Frames from the glasses go in; a scan position, floor and heading
come out, or **"unknown"** when the service isn't sure. Owner and tasks: [TASKS.md](../TASKS.md)
lane B. Background and Phase 0 results: [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) §5–6.

## Run it (from the repo root)

```sh
python -m localize.index                              # once: download panoramas, build the index (~1 min)
python -m localize.cli data/photos/glasses/*.jpg      # try photos, each on its own
python -m localize.cli --sequence frames/*.jpg        # try consecutive frames as one walk
python -m localize.server --token <secret> --save-frames   # HTTP service on port 8765
python -m localize.replay data/frames/<session> --compare  # rerun a saved walk with the current rules
```

## Phone test (no glasses needed)

The phone does **not** need to be near the laptop; it needs the public HTTPS link. Phones only
allow the camera on https pages.

1. On the laptop: `python -m localize.server --token <secret> --save-frames`
2. In a second terminal: `cloudflared tunnel --url http://localhost:8765` (`brew install cloudflared`).
   It prints a `https://….trycloudflare.com` link that changes every run.
3. In Rabinowitz Hall (Floors 2–3), open `<link>/?token=<secret>` on the phone, tap **Start**.
   It sends a frame every second, shows the matched scan view next to the camera and speaks the
   answer. Tap **New walk** when you move somewhere new.
4. Frames and results land in `data/frames/<session>/` (git-ignored) for tuning the rules.

## HTTP API (for the glasses app, lane C)

| Call | Body | Returns |
|---|---|---|
| `POST /localize?session=<phone-id>` | one JPEG (`Content-Type: image/jpeg`) | result JSON (below) |
| `POST /localize?session=<id>&floor=Floor%203` | same; restricts the answer to that floor | result JSON |
| `POST /reset?session=<id>` | none | `{"ok": true}` (start a new walk) |
| `GET /health` | none | index info |

Send a frame every 0.5–1 s while navigating. The session votes over the last 4 frames (max 10 s
old) and favors spots next to its last confident answer.

```json
{
  "status": "ok",                 // "held": plain view, this is the last "ok" answer (< 5 s old)
                                  // "unknown": never tell the user a position as fact
  "reason": "score 0.69 < 0.75",  // only when held or unknown
  "frames": 3, "score": 0.838, "margin": 0.061, "agreement": 1.0,
  "floor_margin": 0.09,
  "best_guess": {
    "pano_id": "9xmt…", "label": "65", "floor": "Floor 3",   // floor can be "unknown"
    "room": "Hallway", "position_m": {"x": 11.91, "y": -12.45, "z": 5.49},
    "heading_deg": 180            // relative to the scan, not a compass heading
  },
  "floor_candidates": ["Floor 2", "Floor 3"],   // only when the floor is unsure
  "latency_ms": 40
}
```

## How it decides

1. Each frame is compared with 8 views (45° apart) at each of the 66 scan positions (DINOv2-small).
2. Scores are averaged over the session's recent frames; spots within 2 walking steps of the last
   confident answer get a small bonus. A frame that scores < 0.65 everywhere (floor, blank wall,
   blur) doesn't vote.
3. **"ok"** needs all of: ≥ 2 frames, top score ≥ 0.75, a lead ≥ 0.02 over the best *different*
   spot (> 4 m away in x/y), and ≥ 60% of recent frames agreeing.
4. Otherwise **"held"** if the last "ok" is under 5 s old (turning toward a plain wall shouldn't
   lose you; the phone page stays quiet), else **"unknown"**.
5. If the only close rival is the same spot on the other floor, the answer is "ok" with
   `floor: "unknown"`. The app can send `floor=` once it knows the floor.

## Calibration: first phone walk (Sat Nov 14, 189 frames, Rabinowitz Hall Floors 2–3)

Correctness judged by eye (each frame next to its matched view); there is no surveyed ground truth.

| Rules | ok | held | unknown | Wrong "ok"/"held" |
|---|---|---|---|---|
| Live run (1 frame enough, lead ≥ 0.01, no hold) | 101 | – | 88 | ~8 |
| Current rules (`python -m localize.replay … --compare`) | 89 | 39 | 61 | 3 |

- Most old "unknown"s were plain views while standing at a known spot; "held" now covers them.
- Fixed: first frame after a reset picking the right x/y on the wrong floor (spot 61 vs. 13);
  frosted-glass and empty-corridor views with a thin lead.
- Still wrong: a glass stairwell door on Floor 3 that has no scan position matches the atrium
  stairs (spot 45). Thresholds can't fix places the scan doesn't cover: keep the demo route on
  scanned spots.
- Solid spots for the demo route: elevator 32, atrium 35/23, glass door 21, hallways 65, 16,
  15/14, wood-panel hallway 31 → 25.

## Calibration (Phase 0 photos, one photo at a time, before the multi-frame rules)

| Set | Correct "ok" | Correct "unknown" (off-scan) | Cautious "unknown" (right spot, close rival) | Wrong "ok" |
|---|---|---|---|---|
| Glasses (6) | 4 | 1 (window) | 0 | 1 (elevator lobby, off-scan, score 0.805) |
| Phone (7) | 1 | 2 (window, restroom door) | 4 | 0 |

- **One frame can't fully separate off-scan from on-scan**: the elevator lobby scores higher
  than some real matches. The phone walk above is the multi-frame test.
- The scan has **no Floor 1 positions**: only Floors 2 (36) and 3 (30).
- Some spots look alike across the building (e.g. positions 20/44 and 19/65 are the same x/y on
  Floors 2 and 3).

## Files

| File | What |
|---|---|
| `index.py` | Downloads panoramas (parallel; re-queries expired links), embeds views, caches to `cache/localize/` |
| `graph.py` | Walking graph from Matterport `anchor.neighbors`, same floor, ≤ 8 m per edge |
| `locator.py` | Scoring, voting, graph prior, "unknown" rules |
| `server.py` | HTTP service + phone test page (standard library only) |
| `static/index.html` | Phone test page: camera → `/localize` → speech |
| `cli.py` | Try photos without a phone |
| `replay.py` | Rerun a saved walk (`data/frames/<session>`) with other cutoffs |
