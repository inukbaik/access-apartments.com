# CLAUDE.md

Context for Claude Code. Read this first, then the docs it links to.

## What this project is

HackPrinceton Fall 2026 entry, targeting the **CoStar special track** ("Inside and Out: AI for the Built World"). Two halves:

1. **Before you go:** an agent that screens Houston and LA listings for wheelchair accessibility using Matterport room data, Vexcel aerial imagery and CoStar records, and produces an evidence report.
2. **When you're there:** Meta Ray-Ban glasses figure out where the user is inside a building by matching camera frames to that building's Matterport panoramas, then speak step-free directions. Demoed live in Rabinowitz Hall (Matterport id `P3S6VUTP3qB`).

**Deadline: Devpost submission by 8:00 AM Sunday Nov 15, 2026.** Judging is a 2 minute live demo. Optimize for a working, demoable path over completeness.

## Read these before doing anything substantial

- `docs/PROJECT_CONTEXT.md`: the plan, what the data actually contains, the accessibility checks (with ADA numbers), architecture, phases, risks, pitch.
- `docs/DISCUSSION_LOG.md`: why this idea won and what was rejected. **Don't propose the rejected ideas again** unless asked.
- `scripts/README.md`: how to run the Phase 0 tests.

## Current status (update this section as work progresses)

- [x] `scripts/phase0_check.py` written and run against the API (steps 1 to 3 done; 4 and 5 need `models_index.csv`).
- [x] `scripts/localize_test.py` tested end to end offline with synthetic images and real DINOv2-small on MPS (5 of 5 correct). **Not yet tried on real venue panoramas or real photos.**
- [x] Get keys (`/costar-keys` in Discord) → `.env` (the `.env` sits at the repo root; `load_dotenv()` finds it by walking up from `scripts/`)
- [ ] Download `models_index.csv` from the hackathon site → `accessible-spaces/`
- [ ] Rerun `phase0_check.py` with the index for steps 4 and 5
- [ ] Take 5 photos in Rabinowitz Hall → `photos/`; run `localize_test.py`; record the score below
- [ ] **Decision:** localization ≥ 3/5 → build both halves; else drop the glasses and go all in on the finder

### Phase 0 results (2026-11-14)
- Key works: folder 'HackPrinceton 2026', 14,945 models (13,014 commercial, 1,930 residential).
- Door openings in API: **YES.** `Edge.openings` → `Opening { id label type width height lowerElevation relativeCenter }`. Types seen: `doorway`, `window`.
- Venue scan reachable with our key: **YES.** 'Princeton - Rabinowitz Hall' (public), 3 floors, 41 rooms, 66 panoramas.
- Venue measurements: 9 doorways mapped (widths 19.3 to 69 in; 6 of 9 ≥ 32 in), 3 windows. Only 9 doorways across 3 floors, so the opening data is **sparse**; treat a missing door as unknown, not absent. Edge types: `wall` 317, `invisible` 17.
- Venue room labels are mostly `Void` (31) / `Other` (8) / `Hallway` (2). Hallway "narrow side" comes from room width/depth (899 in and 148 in): a bounding box, **not a corridor clear width**.
- Hallway widths / bathroom dimensions across listings: _unknown_ (needs `models_index.csv`)
- Commercial models that are really apartments: _unknown_ (needs `models_index.csv`)
- Localization score: _unknown_

## Key facts about the data and APIs (verified from the track reference page)

- **Matterport Model API:** GraphQL, `POST https://api.matterport.com/api/models/graph`, HTTP basic auth (API key = username, API token = password). Production only.
  - ~14,944 models in the HackPrinceton folder.
  - **No geo search:** use `models_index.csv` for lat/lon lookups.
- **Useful Matterport fields:**
  - `rooms { classifications { label confidence } dimensions(units: metric) { areaFloor width depth height } }`
  - `floors { vertices { id position { x y } } edges { id type thickness vertices { id } } }`
  - `panoLocations { id label position { x y z } skybox(resolution: "2k") { status children } }`: 6 faces, 0 = up, 1 to 4 = horizon, 5 = down; links are signed and expire.
  - `view(type: "matterport.model.defurnished") { id }`: query that id like a model to get furniture-removed panoramas.
  - `assets { floorplans(provider: "matterport") { ... } }` and the MatterPak (mesh + point cloud) via `bundle(id: "mp:matterpak")`.
- **Door widths are unconfirmed.** The example only showed `type: "wall"` edges. `phase0_check.py` introspects `Edge` for `openings`.
- **Vexcel:** `X-API-KEY` header; Houston and LA only (403 elsewhere).
  - Ortho clip: `POST https://api.vexcelgroup.com/v2/ortho/extract` with a WKT polygon, `srid 4326`, `layer "urban,urban-r,wide-area,urban-g"`.
  - MCP server: `https://api.vexcelgroup.com/v2/mcp`.
- **CoStar kit:** password protected zip; joins on Homes listing id (residential) or CoStar property id (commercial). The join is untested by CoStar.
- **Meta glasses:** Wearables Device Access Toolkit (phone app, iOS or Android). Enable Developer Mode in the Meta AI app. Mock Device Kit simulates the glasses with the phone camera. On iOS, streaming moves the phone onto the glasses' wifi, so internet goes over cellular. Continuous streaming drains the battery fast, so stream only while navigating.

## ADA thresholds used

| Check | Threshold |
|---|---|
| Hallway / route width | 36 in (0.914 m) |
| Door clear width | 32 in (0.813 m) |
| Turning circle | 60 in (1.524 m) |
| Max ramp slope | 1:12 |

The agent must report **unknown** instead of guessing when data is missing, and attach evidence.

## Conventions

- Python 3, scripts run from the **repo root**. Shared API helper: `scripts/mp_common.py` (`graph(query, variables) -> (data, errors)`).
- **Secrets only in `.env`** (gitignored). Never print, log or commit keys. `models_index.csv`, `out/`, `cache/`, `photos/` are gitignored.
- Keep outputs in `out/`, downloads in `cache/`.
- The repo must be public on GitHub for submission, so double check nothing secret is committed.

## Help

CoStar engineers are in **#costar-group** on Discord (or `/ask-costar`). Ted Weidling knows the API; Lucas Hayne knows semantic search. If the venue scan isn't reachable with our key, ask them to add `P3S6VUTP3qB` to the HackPrinceton folder.
