# Phase 0 test scripts

Two scripts that answer the go / no go questions in `docs/PROJECT_CONTEXT.md`. Run everything from the **repo root**.

## Setup (5 min)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt
cp .env.example .env        # paste keys from /costar-keys in Discord
```

Download `models_index.csv` from the hackathon site (it sits next to the quickstart notebook) and put it in the repo root. It's gitignored.

## 1. Data check (about 2 min)

```bash
python scripts/phase0_check.py --index models_index.csv --sample 25
```

What it tells you:
1. Whether your key works and how many models it sees.
2. **Whether wall edges expose door openings.** It inspects the API schema, and if `openings` exists it pulls them automatically.
3. Whether your key can read the Rabinowitz Hall scan (`P3S6VUTP3qB`).
4. What's in `models_index.csv`, including how many "commercial" models are really apartments.
5. On a sample of models: hallway widths in inches vs the 36 in ADA minimum, bathrooms vs the 60 in turning circle, and every edge type seen.

It ends with a short verdict, and writes everything to `out/phase0_report.json`.

## 2. Localization test (about 10 min plus photo taking)

1. Take **5 photos** from different spots around the hall: phone, or frames from the glasses. Hold the camera level and point at walls, doors and windows rather than crowds. Put them in `photos/`.
2. Run:

```bash
python scripts/localize_test.py --photos photos/
python scripts/localize_test.py --photos photos/ --defurnished          # also try the no furniture panoramas
python scripts/localize_test.py --photos photos/ --embed-model facebook/dinov2-base   # stronger, slower
```

3. Open `out/localize/*_matches.jpg`. Each shows your photo next to its top 3 matched scan positions. `map_*.png` shows where the best match sits in the building; color is height, which separates floors.

**Pass = at least 3 of 5 photos match the right spot.** The printed `margin` is the gap between the best and second best scan position. Under about 0.02 means it's guessing.

The first run downloads the DINOv2 model (~100 MB) and the panorama faces (cached in `cache/`).

### If the key can't read the venue scan

Ask in **#costar-group** to add `P3S6VUTP3qB` to the HackPrinceton folder. Meanwhile, open the public tour (https://my.matterport.com/show?m=P3S6VUTP3qB), screenshot 20 to 40 views around the areas you'll demo in, put them in `shots/`, and run:

```bash
python scripts/localize_test.py --photos photos/ --ref-dir shots/
```

## Notes

- Skybox faces 1 to 4 are the horizon. The script checks which direction they chain and builds 8 views per scan position, 45° apart. The headings are relative to the model, not compass directions.
- Panorama links are signed and expire. Rerunning refetches only what isn't cached.
- `mp_common.py` holds the shared `graph()` helper (HTTP basic auth: API key = user, token = password).
