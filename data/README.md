# data/ (local only, never committed)

Everything in `data/` except this file is git-ignored. The repo is public, and the CoStar kit
and Matterport downloads are sponsor data, so **each teammate downloads them locally**. Use the
same paths below so scripts work on everyone's machine.

## Expected layout

```
data/
├── README.md                     ← this file (the only tracked file)
├── costar/                       ← CoStar real estate data kit (~430 MB)
│   ├── index.md                  ← start here: datasets, joins, field docs
│   ├── commercial-properties.csv     PropertyId → MatterportModelId, address
│   ├── residential-listings.csv      ListingId → MatterportModelId, address
│   ├── data/*.jsonl              ← 8 datasets, one record per line
│   ├── models/*.md               ← per-dataset field docs
│   ├── concepts/  schemas/  tools/
└── venue/
    └── P3S6VUTP3qB/              ← Rabinowitz Hall Matterport scan (~160 MB)
        ├── panos.json            ← every panorama with its x/y/z position
        └── <pano_id>/skybox0..5.jpg
```

## Setup (about 10 minutes)

1. **Keys.** In the CoStar track Discord, run `/costar-keys`. Then:
   ```sh
   cp .env.example .env      # fill in the values; .env is git-ignored
   ```
2. **CoStar kit.** Download `costar-hackathon-kit.zip` (link from `/costar-keys`), then unzip it
   with `COSTAR_ZIP_PASSWORD` from `.env`, so that `data/costar/index.md` exists:
   ```sh
   mkdir -p data/costar
   unzip -P "$COSTAR_ZIP_PASSWORD" costar-hackathon-kit.zip -d data/costar
   ```
   If the zip contains a top-level folder, move its contents up so the layout matches the
   layout above.
3. **Venue panoramas.** Needs `MATTERPORT_API_KEY` and `MATTERPORT_API_TOKEN` in `.env`:
   ```sh
   set -a; source .env; set +a
   python3 scripts/fetch_venue_panos.py            # defaults: P3S6VUTP3qB, 2k
   ```
   Signed links expire about an hour after the query, so the script downloads right away.

## Check

```sh
ls data/costar/index.md data/venue/P3S6VUTP3qB/panos.json
```

## Rules

- **Never commit anything in `data/`**, and never paste records into issues, docs or Devpost.
  Use small, made-up examples in docs.
- Want to share files with the team faster? Use a private channel (team DM or a private
  drive), never the public repo.
