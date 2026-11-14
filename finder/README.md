# Finder (Part A)

Listing screener: candidates near a point from `data/models_index.csv`, accessibility checks
(hallway, door, turning space), ranked results with evidence. Uncertainty means failure.

Owner and task list: [TASKS.md](../TASKS.md) lane A. Plan: [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) §4-5.

## Usage

Run from the repo root:

```
.venv/bin/python -m finder.screen --lat 34.0636 --lon -118.2999 --radius-km 2 --limit 15
.venv/bin/python finder/test_checks.py
```

Outputs: `out/finder/<sid>.json` per listing (candidate, checks, error) and `out/finder/ranked.json`.
Raw API data is cached in `cache/finder/` (use `--refresh` to re-fetch).

- Hallway under 36 in, doorway under 32 in, or no bathroom with a 60 in narrow side = **fail**.
- A check passes only when measured and meeting the threshold. Missing data = **fail (no data)**; a
  doorway under 20 in = **fail (bad measurement)**. Sizes are room bounding boxes, not clear widths.
- One listing per building (`costar_property_id`, else rounded lat/lon); other units shown as `+N`.
- Ranking: fewest fails, then fewest "no data", then nearest. Listings that failed to load go last.
