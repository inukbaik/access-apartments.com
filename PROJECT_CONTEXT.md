# HackPrinceton Fall 2026: Accessible Spaces

**The plan.** Last updated Sat Nov 14, evening. Who is doing what right now: [TASKS.md](TASKS.md).
Why this idea, and what we rejected: [docs/DISCUSSION_LOG.md](docs/DISCUSSION_LOG.md).

**Hard deadline:** Devpost submission by **8:00 AM Sunday, Nov 15** (public GitHub repo).
**Judging:** Sunday 9:30 AM to 2:30 PM, in person, **2 minute demo**. A video is optional but recommended (max 2 min).

---

## 1. The idea

People who use wheelchairs (or have low vision) can't tell from a listing whether they could
actually live in a place, and once they arrive, unfamiliar buildings are hard to get around.

- **Part A, before you go (the finder):** an agent screens real Houston and LA listings for
  wheelchair accessibility using CoStar's data: hallway widths, door widths, bathroom turning
  space from the Matterport scans, plus entrance steps and parking from Vexcel aerial imagery.
  It ranks listings, shows its evidence, and **fails** a check (saying "no data") when data is missing.
- **Part B, when you're there (the glasses):** Meta Ray-Ban glasses work out where you're
  standing by matching the camera view to the building's Matterport scan, then speak step-free
  directions. Demoed live in Rabinowitz Hall, the venue, which has a Matterport scan.

Pitch line: *"Find a place you can actually live in, then get around the building when you
arrive. Any scanned building works, and here's the one we're standing in."*

Part B is strongest in larger buildings (an apartment complex's lobby, elevators and amenities,
offices, clinics), not inside a single small apartment.

---

## 2. Tracks and prizes

**Main track (pick exactly one):** Business and Enterprise (real estate tool) or Healthcare
(housing and building access for people with disabilities). _Not decided yet._

| Special track | Prize | Why we fit |
|---|---|---|
| **CoStar: Inside and Out, AI for the Built World** | $1,500 / $500 / $250 + interview fast track | **Primary target.** Uses Matterport + Vexcel + CoStar, agentic, spatial; accessibility tools explicitly welcome |
| Amazon Best Practical AI Innovation | Gift cards | Example list includes an accessibility tool using voice, vision or gesture |
| Best Hardware Hack / Best Physical AI Hack | BambuLab P1S / $500 | Only if the glasses part works |
| ChatOverflow Agent Leaderboard | Cash + raffle | Free: connect the coding agent |

**CoStar scoring:** 30% use of data (combining layers), 30% agentic depth (reasons, plans, acts;
not a chat wrapper), 25% usefulness ("would someone want this on Monday?"), 15% demo and polish.
**HackPrinceton scoring:** Creativity, Utility, Charity (societal need), Avidity.

---

## 3. Data (verified by our Phase 0 tests)

Keys: `/costar-keys` in the CoStar Discord → `.env` (see `.env.example`). Data downloads:
[data/README.md](data/README.md).

### Matterport Model API
- GraphQL, `POST https://api.matterport.com/api/models/graph`, HTTP basic auth (key = username,
  token = password). Production only. Shared helper: `scripts/mp_common.py`.
- **14,944 models**: 13,014 "Commercial Spaces", 1,930 "Residential Spaces". **49% of the
  "commercial" ones are named like apartment units** ("2BR, 1BA…"). Accessible housing is the
  natural use case.
- **No geo search in the API.** Use `data/models_index.csv` (sid, name, segment, lat/lon,
  address, CoStar property id / Homes listing id, splat, pano/room/floor counts, defurnished,
  AI summary). 14,713 models have room data; 232 have an aerial splat.
- **Useful fields:**
  - `rooms { classifications { label } dimensions(units: metric) { areaFloor width depth height } }`
  - `floors { edges { id type thickness openings { type label width height lowerElevation relativeCenter } } }`:
    **door openings exist** (`type: doorway` or `window`, width in meters).
  - `panoLocations { id position { x y z } skybox(resolution: "2k") { status children } }`:
    faces 0 = up, 1–4 = horizon, 5 = down. **Signed links expire within minutes; download right
    after the query.**
  - `view(type: "matterport.model.defurnished") { id }`: query that id like a model for
    furniture-removed panoramas.
  - Floor plans, MatterPak (mesh + point cloud), and for 232 models an aerial splat + drone photos.
- **Data gaps:** many rooms are unlabelled or `Void`; about a third of sampled models had no
  hallway or bathroom. Hallway "width" is the room's bounding box, not a measured clear width.
  Door openings are sparse (Rabinowitz Hall: only 9 doorways mapped across 3 floors). A missing
  door fails the check ("no data"); it does not mean there is no door.
- Interiors were scanned for listings; **exteriors are often missing**.

### Vexcel
- `X-API-KEY` header; **Houston and LA only** (403 elsewhere).
- Ortho clip: `POST https://api.vexcelgroup.com/v2/ortho/extract` (WKT polygon, `srid 4326`,
  `layer "urban,urban-r,wide-area,urban-g"`), 7.5 cm/pixel. Also oblique images, elevation,
  parcels, object detection. MCP server: `https://api.vexcelgroup.com/v2/mcp`.
- Roof height: `GET /v2/property/extract` with `wkt=POINT(lon lat)`, `srid=4326`,
  `include=precomputed,calculated` returns per-structure footprints and `roof-characteristics.height` (m).

### CoStar records
- Password-protected kit (`data/costar/`). Joins to Matterport via CoStar property id
  (commercial) or Homes listing id (residential). **The join is untested by CoStar.**

### The venue scan
- **Rabinowitz Hall** `P3S6VUTP3qB` (https://my.matterport.com/show?m=P3S6VUTP3qB). Our key
  can read it: 3 floors, 41 rooms, 66 panoramas.

---

## 4. Accessibility checks

| Check | Threshold (ADA, approximate) | Data source | Status |
|---|---|---|---|
| Hallway / route width | ≥ 36 in (0.914 m) | Room width/depth for Hallway rooms | Works (bounding box) |
| Door clear width | ≥ 32 in (0.813 m) | `Edge.openings` with `type: doorway` | Works where mapped |
| Wheelchair turning space | 60 in (1.524 m) circle | Bathroom/kitchen narrow side | Works |
| Steps inside | None on route | Panorama vision, point cloud | Not tried |
| Entrance steps | Step free or ramp | Vexcel oblique, drone photos (232 models) | Not tried |
| Path slope from parking | Ramp max 1:12 | Vexcel elevation | Not tried |
| Accessible parking | Marked stall + access aisle | Vexcel ortho + vision model | Not tried |
| Building age | Pre 1990 predates ADA | CoStar record (year built) | Not tried |

A check passes only when it was measured and meets the threshold. Missing data is a fail labelled
"no data"; an implausible value (e.g. a "doorway" under 20 in) is a fail labelled "bad measurement".
The agent attaches evidence (floor plan with flagged spots, panorama crops, aerial crop).

Decision (Sat Nov 14): uncertainty means failure. A check passes only when measured and meeting the threshold; this protects users from being sent to a place they can't use.

Deliberate exception (Sat Nov 14): extra needs the user names (roll-in shower, grab bars, ramp / step-free entry, elevator, wheelchair accessible) are not measured. The core checks stay strict pass/fail. Extra needs are searched in CoStar listing text and reported per building as "listing says" (with the matched phrase and source) or "information unavailable"; never as a pass or a fail. They only reorder buildings within the same measurement group (same fails and no-data count); a building with more failed core checks never moves above one with fewer.

Building info (informational, never ranked): with `--building-info`, each shown building gets its story count and elevator status. Stories cross-reference CoStar (`numStoriesAboveGrade`, residential `storiesTotal`) with Vexcel roof height (only the structure whose footprint contains the point; height divided by 2.7 to 4 m per story gives a range) and say "agree", "disagree" or which source is missing. Elevator status is CoStar only (passenger elevator records, `hasElevator` true, listing text); a missing or false value is "information unavailable", never "no elevator". It is computed after the ranking is final, is never a check, and never changes pass/fail or order.

---

## 5. Architecture

**Part A: finder (`finder/`)**
```
User needs (e.g. power chair, roll-in shower, no steps) + area
  → candidates near lat/lon from data/models_index.csv
  → per candidate: Matterport rooms + door openings (+ panoramas)
                   Vexcel ortho/oblique around the address
                   CoStar record (optional)
  → agent scores checks, flags problems, fails checks with no data
  → ranked list + evidence report per listing
```

**Part B: glasses (`localize/`)**
```
Offline: venue panoramas → 8 views per scan position (45° apart) → DINOv2 embeddings
         → walking graph of connected scan positions; floors connect only via elevator
Live:    glasses frame (Device Access Toolkit phone app) → embed → nearest match
         = position + heading → route on the graph → spoken directions
```
Glasses notes are in [docs/GLASSES_SDK.md](docs/GLASSES_SDK.md). Key points:
- Phone app from Meta's sample (`facebook/meta-wearables-dat-ios` / `-android`), Developer Mode
  on in the Meta AI app.
- The Mock Device Kit lets people without glasses use the phone camera.
- On iOS, streaming puts the phone on the glasses' wifi, so the demo phone needs cellular data.
- Stream only while navigating (battery).

---

## 6. Phase 0 results (Sat Nov 14)

Scripts and how to rerun them: [scripts/README.md](scripts/README.md).

| Question | Answer |
|---|---|
| Keys work | **Yes**, 14,945 models visible |
| Door widths in the API | **Yes**, `Edge.openings` (sparse) |
| Venue scan reachable | **Yes** |
| Listings have hallway / bathroom sizes | **Yes.** In a 25-model sample, 18 of 21 hallways ≥ 36 in (min 27.5 in); 15 of 51 bathrooms fit a 60 in circle; one door measured 0.66 m (26 in), under 32 in |
| Localization (photo → right spot) | **Rough pass**, judged by eye: glasses ~4/6, phone ~5/7 (pass = 3/5). Phone and glasses pick the same positions. Distinctive spots (stairwells, atrium, glass corridors) match; plain spots (window and sign, restroom door, elevator lobby) fail. Margins mostly < 0.02, so confidence is low |

**Still to run:** `--embed-model facebook/dinov2-base` and `--defurnished` on the same photos.

**Decision (pending those runs):** if localization holds, build both parts; demo Part B only on
a route through distinctive spots. If it gets worse, drop the glasses and put everything into
Part A.

---

## 7. Phases

### Phase 1: Finder core (Part A), in progress
- [x] Candidate search near a point from `data/models_index.csv`
- [x] Pull rooms + door openings; hallway, door and turning-space checks (missing data = fail, "no data")
- [ ] Building info: stories (CoStar + Vexcel roof height, cross-referenced) and elevator status (CoStar), informational only
- [ ] Agent loop that reasons over checks, fails checks with no data, ranks listings
- [ ] Evidence report: floor plan with flagged spots, panorama crops, aerial crop

### Phase 2: Indoor localization (Part B), if Phase 0 holds
- [ ] Localization service: frame in → position + heading + confidence out
- [ ] Walking graph between scan positions, elevator-only floor changes
- [ ] Turn-by-turn instructions from position + heading
- [ ] Pick the demo route through spots that match reliably

### Phase 3: Glasses integration
- [ ] Phone app grabs frames from the glasses on demand → localization service
- [ ] Spoken directions through the glasses speakers
- [ ] Rehearse the demo route

### Phase 4: Polish and submit (Sat night → before 8:00 AM Sun)
- [ ] Backup demo video (Mock Device Kit if hardware misbehaves), ≤ 2 min
- [ ] README, public repo check (no data, no keys), Devpost writeup with Discord usernames
- [ ] Pick the main track; add CoStar, Amazon, Hardware/Physical AI (if glasses work), ChatOverflow
- [ ] Rehearse the 2 minute pitch
- [ ] **Submit well before 8:00 AM**

---

## 8. Risks and fallbacks

| Risk | Fallback |
|---|---|
| Door openings sparse | Fail the check, labelled "no data"; later: vision on panoramas or point cloud gaps |
| Localization unreliable (furniture, crowds, plain walls) | Bigger model, defurnished panoramas, demo route through distinctive spots; else drop Part B |
| "Commercial" set is mostly apartments | Lean into it: accessible housing is the use case |
| CoStar join fails | Matterport + Vexcel alone still combine two layers |
| Glasses battery or heat | Stream only while navigating; charge between runs |
| Privacy questions | Frames are processed and discarded; no face analysis |
| Sponsor data leaks into the public repo | Everything lives in git-ignored `data/`; check `git status` before every push |

---

## 9. Competitors and differentiation

| Existing tool | What it does | How we differ |
|---|---|---|
| openrouteservice (wheelchair profile) | Street and sidewalk routing from OpenStreetMap tags | Stops at the front door; we judge whether the place itself is accessible, from measured scans, and guide you inside |
| Google Maps wheelchair routes / entrance info | Transit routes and a yes or no on entrances | No interior measurements, no indoor guidance |
| Wheelmap | Crowdsourced accessible / not accessible ratings | Ratings vs measured widths, turning space and steps with evidence |
| Be My Eyes on Meta glasses | Describes the scene or connects to a volunteer | Generic description vs building-specific directions from the digital twin |

**Framing for judges:** *"openrouteservice gets you to the curb; we take you from the parking
spot to the bathroom."*

---

## 10. Pitch outline (2 minutes)

1. **Problem (20s):** Listings almost never say whether a wheelchair fits; people waste trips.
   Inside unfamiliar buildings, phone maps don't help.
2. **Before you go (40s):** Enter needs → agent screens real LA listings → evidence report
   (narrow hallway flagged, bathroom passes, entrance stairs spotted from the air).
3. **When you're there (40s):** Judge puts on the glasses → "You're on floor 2 near the
   stairwell; the elevator is ahead on your left."
4. **Why it matters (20s):** Uses all of CoStar's layers together; any scanned building works.

---

## 11. People and links

- **CoStar track help:** #costar-group on Discord or `/ask-costar`. On site: Azwad Sabik, Ilia
  Glazkov, Lucas Hayne (semantic search), Olaf Brandt, Ted Weidling (the API), Guillermo Bruce
  (Discord).
- **Track reference page / quickstart (and `models_index.csv`):** https://beta-app.matterport.com/2026-princeton-hackathon/quickstart
- **Matterport Model API docs:** https://matterport.github.io/developer-docs/api/
- **Showcase SDK:** https://matterport.github.io/developer-docs/overview/
- **Vexcel MCP:** https://api.vexcelgroup.com/v2/mcp
- **Meta wearables developer site:** https://wearables.developer.meta.com
- **Devpost:** https://hackprinceton-fall-26.devpost.com/
