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
- One listing per building, decided in this order (see `buildings.py`): (1) `street_key` of the address, (2) `street_key` of the name, (3) `costar_property_id`, (4) a "<building> - <unit>" name prefix within 50 m, (5) lat/lon within 15 m. `street_key` parses with `usaddress` and keeps house number (with fractions like "1286 1/2"), pre-direction and street name; it drops street type, unit, city and zip, and returns None for unit descriptions ("2BR, 1BA", "Studio"). Same key but over 150 m apart is not merged. When unsure, do not merge: a wrong merge can hide a failing unit. Other units shown as `+N`.
- Ranking: fewest fails, then fewest "no data", then nearest. Listings that failed to load go last.
