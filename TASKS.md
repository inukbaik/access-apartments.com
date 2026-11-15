# Tasks

Who is doing what right now. The plan behind these is in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).
Each lane owns its own folder, so nobody edits the same files. Shared code (`scripts/mp_common.py`)
changes only after a heads-up in the team chat.

Update this file when you pick up or finish something. `git pull --rebase` first.

## Lanes

| Lane | Owner | Folder | Status |
|---|---|---|---|
| A. Finder (listing screener) | Inuk | `finder/` | Core screener done on `feat/finder`; agent loop next |
| B. Localization + routing | Shane | `localize/` | Phase 0 follow-up runs |
| C. Glasses app | _unassigned_ | `glasses-app/` | Waiting on the go / no go for B |
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
5. [ ] Then (PROJECT_CONTEXT.md §7):
   - [ ] 5b. Agent loop on a local model (Ollama; no paid API key, sponsor data stays on the
     laptop). Model choice in progress.
   - [ ] 5a. Vexcel entrance / parking check (try the server-side SAM 3 endpoint `/v2/elements/detect`).
   - [ ] 5c. Evidence report per listing (floor plan, panorama crops, aerial crop).

**Done when (1–4, met):** one command prints a ranked list for an LA point with pass / fail per check and the reason for each fail (measured, no data, bad measurement).

**Demo point:** USC / W 36th St, LA:
`.venv/bin/python -m finder.screen --lat 34.0242 --lon -118.2991 --radius-km 1.5 --limit 10`
(4 of 10 buildings pass all checks; the rest show each fail reason.)

**Findings so far** (800-listing survey, LA + Houston): doors are the bottleneck (only 4% of
listings measure ≥ 32 in on every doorway); 7 listings pass all three checks.

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
