# Tasks

Who is doing what right now. The plan behind these is in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).
Each lane owns its own folder, so nobody edits the same files. Shared code (`scripts/mp_common.py`)
changes only after a heads-up in the team chat.

Update this file when you pick up or finish something. `git pull --rebase` first.

## Lanes

| Lane | Owner | Folder | Status |
|---|---|---|---|
| A. Finder (listing screener) | Inuk | `finder/` | Starting |
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
5. [ ] Then: Vexcel entrance/parking check, agent loop, evidence report (PROJECT_CONTEXT.md §7).

**Done when:** one command prints a ranked list for an LA point with pass / fail per check and the reason for each fail (measured, no data, bad measurement).

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
