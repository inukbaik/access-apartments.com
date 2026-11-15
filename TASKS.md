# Tasks

Who is doing what right now. The plan behind these is in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).
Each lane owns its own folder, so nobody edits the same files. Shared code (`scripts/mp_common.py`)
changes only after a heads-up in the team chat.

Update this file when you pick up or finish something. `git pull --rebase` first.

## Lanes

| Lane | Owner | Folder | Status |
|---|---|---|---|
| A. Finder (listing screener) | Inuk, Shane (web page) | `finder/` | Screener, agent, building info and web page done. **This is the demo.** |
| B. Localization + routing | Shane | `localize/` | Dropped for the demo (test results stay in the README) |
| C. Glasses app | _unassigned_ | `glasses-app/` | Dropped with B |
| D. Demo, video, Devpost | _unassigned_ | `docs/` | Not started |

## A. Finder (Inuk)

Goal: given an area and a user's needs, return listings ranked by accessibility, with evidence and
a fail (with the reason) where data is missing. Needed whatever happens with the glasses.

1. [x] Candidate search: models near a lat/lon from `data/models_index.csv` (Houston / LA).
2. [x] Per model: rooms + door openings via `scripts/mp_common.graph()`. The queries in
   `scripts/phase0_check.py` (steps 2 and 5) already work; reuse them.
3. [x] Checks: hallway ≥ 36 in, door ≥ 32 in, bathroom narrow side ≥ 60 in. Uncertainty means
   failure: missing data = fail ("no data"), implausible value = fail ("bad measurement"). Thresholds are in PROJECT_CONTEXT.md §4.
4. [x] Output: JSON per listing (checks, values, evidence ids), then a simple ranked view.
   One row per building (best unit shown, `+N units`); units are grouped by street address
   parsed with `usaddress` (`finder/buildings.py`). When unsure, units are not merged.
5. [x] Then (PROJECT_CONTEXT.md §7):
   - [x] 5b. Agent loop on a local model (Ollama; no paid API key, sponsor data stays on the
     laptop). Model choice in progress.
   - [x] 5a. Building info: stories (CoStar + Vexcel roof height, cross-referenced) and elevator status (CoStar),
     informational only (`--building-info`; never a check, never changes ranking).
   - [x] 5c. Evidence per listing on the web page (`finder/web.py`, `finder/evidence.py`): floor plan
     with every doorway's width, a photo of each doorway from the nearest panorama, building info.
     No aerial crop.
6. [x] Sun Nov 15: doorways into a room the scan classifies as a closet or pantry are not counted
   (unclassified rooms still count); shared amenity scans ("Pool", "Fitness Center") are left out.

**Done when (1–4, met):** one command prints a ranked list for an LA point with pass / fail per check and the reason for each fail (measured, no data, bad measurement).

**Demo point:** USC / W 36th St, LA:
`.venv/bin/python -m finder.screen --lat 34.0242 --lon -118.2991 --radius-km 1.5 --limit 10`
(4 of 10 buildings pass all checks; the rest show each fail reason.)

**Demo point, building info:** Echo Park / downtown edge, LA:
`.venv/bin/python -m finder.screen --lat 34.0705 --lon -118.2491 --radius-km 1.5 --limit 10 --building-info`
(1 of 10 passes all checks; elevator status shows every kind: confirmed by a CoStar record, mentioned
in listing text, information unavailable; stories cross-checked with Vexcel roof height.)

**Demo, web page:** `.venv/bin/python -m finder.web --warm --no-llm`, then http://localhost:8800
(see `finder/README.md`, "Web page" and "Demo").

**Findings** (800 random home listings, LA + Houston, `finder.survey`, Sun Nov 15): 12 pass all
three checks (1.5%). Doors are the bottleneck: 65 of the 412 listings with doorway widths pass
(16%). 590 of 800 lack the data for at least one check. Details in README.md.

**Open questions:** does CoStar allow sending sponsor data to cloud AI models (ask `/ask-costar`)?
Any free LLM credits from sponsors?

## B. Localization + routing (Shane)

1. [ ] Rerun with `--embed-model facebook/dinov2-base` and with `--defurnished`; compare.
2. [ ] Go / no go on the glasses, recorded in PROJECT_CONTEXT.md §6.
3. [ ] If go: localization service (frame → position, heading, confidence) in `localize/`.
4. [ ] Walking graph between scan positions; turn-by-turn text.
5. [ ] Pick the demo route through spots that match reliably.

## C. Glasses app (unassigned)

Only if B is a go. Phone app streams frames from the glasses to the localization service and
speaks the answer. Start from Meta's sample app; see [docs/GLASSES_SDK.md](docs/GLASSES_SDK.md).

## D. Demo, video, Devpost (unassigned)

Pitch script (PROJECT_CONTEXT.md §10), backup video, Devpost writeup, main track choice. Submit
well before **8:00 AM Sun**.
