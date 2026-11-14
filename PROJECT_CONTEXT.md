# HackPrinceton Fall 2026: Accessible Spaces Project

Working notes for the team. Last updated Sat Nov 14, 2:30 AM.

**Hard deadline:** Devpost submission by **8:00 AM Sunday, Nov 15** (public GitHub repo created during the hackathon).
**Judging:** Sunday 9:30 AM to 2:30 PM, in person, **2 minute demo**. A video is optional but recommended (max 2 min).

---

## 1. The idea in one paragraph

An AI agent that helps people with mobility or vision disabilities find and get around accessible spaces, using CoStar's data. **Before you go:** the agent screens real Houston and LA listings for wheelchair accessibility (hallway widths, bathroom turning space, steps, entrance and parking) and shows its evidence. **When you're there:** Meta Ray-Ban glasses figure out where you're standing by matching what the camera sees to the building's Matterport digital twin, then speak step-free directions. We demo the second half live in Rabinowitz Hall, the building we're in, which has a public Matterport scan.

Pitch line: *"Any scanned building works, and here's the one we're standing in."*

---

## 2. How we got here (ideas we rejected and why)

The main filter: **why not just take out your phone?** Glasses only beat a phone when one of these is true:
1. The user didn't know they'd need it (passive capture).
2. Their hands are busy, gloved or sterile.
3. Their attention has to stay on another person.

| Idea | Why we dropped it |
|---|---|
| Classroom whiteboard reader for blind or low vision students | Too simple; existing products and LMS accessibility features already cover it; talking out loud in class is impractical |
| Behavior logging for special ed and ABA therapists | Privacy and recording minors |
| Lab bench copilot that checks protocol steps | Works off the written protocol, but drops the disability angle; kept as a backup idea |
| Memory aid for dementia (medication, keys, stove) | Privacy; continuous camera drains the battery in roughly 30 to 60 min, so it would have to be event triggered and becomes a narrower medication tracker |
| Arrival guide for public destinations like clinics (first CoStar version) | The data is mostly residential and apartment interiors, few true commercial spaces, and entrances usually aren't scanned |

Also noted: kids and impaired users may treat glasses like a toy, so the glasses should go on whoever is capable and willing.

---

## 3. Tracks and prizes we're targeting

**Main track (pick exactly one):**
- **Business and Enterprise** (most natural for a real estate tool), or
- **Healthcare** (pitch as housing and building access for people with disabilities)

**Special tracks (stack as many as we want):**
| Track | Prize | Why we fit |
|---|---|---|
| **CoStar: Inside and Out, AI for the Built World** | $1,500 / $500 / $250 cash + fast track interviews | Primary target. Uses Matterport + Vexcel + CoStar records, agentic, spatial and visual. They explicitly welcome accessibility tools |
| Amazon Best Practical AI Innovation | Gift cards | Their example list includes an accessibility tool using voice, vision or gesture |
| Best Hardware Hack | BambuLab P1S | Wearables count (only if the glasses part works) |
| Best Physical AI Hack | $500 | AI in a physical hardware build (only if the glasses part works) |
| ChatOverflow Agent Leaderboard | Cash + raffle | Free: just connect the coding agent |

**CoStar scoring:** 30% use of data (combining layers), 30% agentic depth (reasons, plans, acts; not a chat wrapper), 25% usefulness ("would someone want this on Monday?"), 15% demo and polish.

**HackPrinceton scoring:** Creativity, Utility, Charity (societal need), Avidity (team excitement and polish).

---

## 4. What data we actually have

Source: the track reference page (via the Discord link `beta-app.matterport.com/2026-princeton-hackathon/quickstart`). Keys come from `/costar-keys` in Discord. Put them in a `.env` file, never in code.

| Env var | What |
|---|---|
| `MATTERPORT_API_KEY` / `MATTERPORT_API_TOKEN` | Model API, HTTP basic auth (key = username, token = password), production `api.matterport.com/api/models/graph` only |
| `VEXCEL_API_KEY` | Vexcel API, `X-API-KEY` header; **Houston and LA only**, anywhere else answers 403 |
| `COSTAR_ZIP_PASSWORD`, `COSTAR_KIT_URL` | CoStar property and listing records (160 MB kit) |

### Matterport
- **14,944 models**: 13,014 in "Commercial Spaces", 1,930 in "Residential Spaces". The sample "commercial" ones are named like "6BR, 5BA, 1,846SF", so they look like **apartment and rental units**, not offices or clinics.
- **No geo search in the API.** Use `models_index.csv` (lat/lon, address, segment, CoStar property id or Homes listing id, splat yes or no, pano and room counts).
- **Per model:**
  - Address, lat/lon, AI summary (about 90% have one), property type
  - **Panoramas** as 6 face skyboxes (2k or 4k), each with an x/y/z position in meters; signed links expire
  - A **defurnished view** (furniture removed by AI)
  - **Rooms** with a classification (Bedroom, Bathroom, Hallway, Kitchen...) and dimensions in meters (`areaFloor`, `width`, `depth`, `height`)
  - **Wall graph** (vertices + edges with type and thickness), floor plan images and DXF
  - **MatterPak**: OBJ mesh + colored point cloud (unlocked for the 232 splat models, being unlocked for the rest)
  - For **232 models**: an aerial Gaussian splat + the drone photos with GPS
- **Interiors were scanned for listings.** Exteriors are often missing (example notes: "No exterior scans per agent").
- **Example evidence:** 5836 La Mirada Ave has a hallway 0.88 m (~34.6 in) wide, under the ADA 36 in accessible route minimum, and a bathroom 1.93 x 2.88 m that fits a 60 in (1.52 m) turning circle.

### Vexcel
- One call clips a 7.5 cm per pixel overhead image (ortho) around any lat/lon.
- Also oblique (angled) images, elevation (DSM/DTM), parcels, object detection, embedding search.
- There's a Vexcel MCP server: `https://api.vexcelgroup.com/v2/mcp`.

### CoStar records
- Join to Matterport via Homes listing id (residential) or CoStar property id (commercial).
- **The join is untested by CoStar themselves.**

### The venue scan
- **Rabinowitz Hall:** `https://my.matterport.com/show?m=P3S6VUTP3qB` (public). Floors 2 and 3 seen in the floor selector; has measurements and Hide Furniture.
- **Unknown whether our hackathon key can query it** through the Model API (keys only reach the HackPrinceton folder).

---

## 5. Accessibility checks the agent can run

| Check | Standard (ADA, approximate) | Data source |
|---|---|---|
| Hallway / route width | ≥ 36 in (0.91 m) continuous | Room `width`/`depth` for Hallway rooms |
| Door clear width | ≥ 32 in (0.81 m) | **Unconfirmed**: wall graph openings if they exist, else vision on panoramas or point cloud gaps |
| Wheelchair turning space | 60 in (1.52 m) circle | Bathroom and kitchen dimensions, ideally the room polygon |
| Steps / level changes inside | None on route | Panorama vision, point cloud heights |
| Entrance steps | Step free or ramp | Vexcel oblique images, drone photos (232 models) |
| Path slope from parking | Ramp max 1:12 | Vexcel elevation |
| Accessible parking | Marked stall + access aisle | Vexcel ortho + vision model |
| Building age prior | Pre 1990 = predates ADA | CoStar record (year built), if available |

The agent must say **"unknown"** when data is missing rather than guess, and show evidence (floor plan with flagged spots, panorama crops, aerial crop).

---

## 6. Architecture sketch

**Part A: Before you go (web app + agent)**
```
User needs (e.g. power chair, roll-in shower, no steps) + area
  → search models_index.csv near lat/lon
  → for each candidate: Matterport rooms + wall graph + panoramas
                        Vexcel ortho/oblique around the address
                        CoStar record (optional)
  → agent scores checks, flags problems, marks unknowns
  → ranked list + evidence report per listing
```

**Part B: When you're there (glasses + phone)**
```
Offline: pull every panorama of the venue scan → slice into views at several headings
         → embed (DINOv2 or CLIP) → index with scan position + heading
         → build walking graph of connected scan positions; floors connect only via elevator in wheelchair mode
Live:    Meta glasses frame (Device Access Toolkit, phone app)
         → embed → nearest match = where you are + which way you face
         → route to the goal on the graph → spoken directions through the glasses speakers
```

Glasses notes:
- Phone app built on Meta's Device Access Toolkit sample app (`facebook/meta-wearables-dat-ios` or `-android`); enable **Developer Mode** in the Meta AI app.
- **Mock Device Kit** lets teammates without glasses develop with the phone camera.
- On iOS the phone joins the glasses' own wifi when streaming, so internet goes over **cellular**. The demo phone needs data.
- Continuous streaming drains the battery fast (Live AI lasted about 30 min on Gen 1). Stream only while navigating, at a low frame rate.

---

## 7. Phases

### Phase 0: Go / no go checks (now → ~4:00 AM Sat)
- [ ] Get keys via `/costar-keys`, run quickstart sections 1 to 5 on one model
- [ ] Model Playground: does `Edge` have `openings` or edge types other than `wall`? (door widths)
- [ ] `models_index.csv`: how many "commercial" models are apartment units? How many have room data?
- [ ] Query the venue: `{ model(id: "P3S6VUTP3qB") { name floors { label } panoLocations { id } } }`
  - If denied, ask in **#costar-group** to add it to the hackathon folder; fallback is the Showcase SDK screenshotting each scan position
- [ ] **Localization smoke test:** take 5 phone photos around the hall, match them against the venue panoramas. **Pass = 3 of 5 land on the right scan position.**
- [ ] Glasses: Developer Mode on, sample app streaming frames to the phone

**Decision at the end of Phase 0:**
- Localization passes → full plan (A + B)
- Localization fails → **drop the glasses**, all in on Part A

### Phase 1: Finder core (Sat morning → early afternoon)
- [ ] Candidate search near a point from `models_index.csv`
- [ ] Pull rooms + dimensions; implement width and turning space checks
- [ ] Vexcel ortho/oblique fetch per address; vision model checks entrance steps and accessible parking
- [ ] Agent loop that reasons over checks, marks unknowns, ranks listings
- [ ] Evidence report: floor plan with flagged spots, panorama crops, aerial crop

### Phase 2: Indoor localization (Sat afternoon, only if Phase 0 passed)
- [ ] Embedding index over venue panoramas (multiple headings per scan position)
- [ ] Walking graph + elevator only floor transitions
- [ ] Turn by turn instructions from position + heading

### Phase 3: Glasses integration (Sat evening)
- [ ] Phone app: grab frames from the glasses on demand or at a low rate → localization service
- [ ] Spoken directions through the glasses speakers
- [ ] Pick and rehearse one demo route in the venue (e.g. our table → elevator → a target room)

### Phase 4: Polish and submit (Sat night → 8:00 AM Sun)
- [ ] Backup demo video (Mock Device Kit if hardware misbehaves), ≤ 2 min, upload and link on Devpost
- [ ] README, public GitHub repo, Devpost writeup with Discord usernames
- [ ] Select main track + CoStar, Amazon, Hardware, Physical AI (if the glasses work), ChatOverflow
- [ ] Rehearse the 2 min pitch: problem → finder demo on a real LA/Houston listing → live glasses moment → impact
- [ ] **Submit well before 8:00 AM**

---

## 8. Risks and fallbacks

| Risk | Fallback |
|---|---|
| No door widths in the API | Vision on panoramas, point cloud gap measurement, or report "door width unknown" |
| Venue scan not reachable with our key | Ask CoStar to add it; Showcase SDK screenshots |
| Localization unreliable (furniture, crowds, lighting) | Match on walls, doors and windows; try the defurnished view; if still bad, drop Part B |
| "Commercial" set is mostly apartments | Lean into it: accessible housing is the use case |
| CoStar join fails | Matterport + Vexcel alone still satisfy "at least two layers" |
| Glasses battery or heat | Stream only while navigating; charge in the case between runs |
| Privacy questions | Frames are processed and discarded, nothing stored; no face analysis |

---

## 9. Pitch outline (2 minutes)

1. **Problem (20s):** Listings almost never say whether a wheelchair fits; people waste trips. Inside unfamiliar buildings, blind and wheelchair users can't easily use a phone map.
2. **Before you go (40s):** Enter needs → agent screens real LA listings → evidence report (narrow hallway flagged, bathroom passes, entrance stairs spotted from the air).
3. **When you're there (40s):** Judge puts on the glasses → "You're on floor 2 near the stairwell; the elevator is ahead on your left."
4. **Why it matters (20s):** Uses all of CoStar's layers together; any scanned building works; what's next.

---

## 10. People and links

- **CoStar track help:** #costar-group on Discord or `/ask-costar`. On site: Azwad Sabik, Ilia Glazkov, Lucas Hayne (semantic search), Olaf Brandt, Ted Weidling (the API), Guillermo Bruce (Discord).
- **Track reference page:** via `https://beta-app.matterport.com/2026-princeton-hackathon/quickstart`
- **Matterport Model API docs:** https://matterport.github.io/developer-docs/api/
- **Showcase SDK:** https://matterport.github.io/developer-docs/overview/
- **Vexcel MCP:** https://api.vexcelgroup.com/v2/mcp
- **Meta wearables developer site:** https://wearables.developer.meta.com
- **Venue scan:** https://my.matterport.com/show?m=P3S6VUTP3qB
- **Devpost:** https://hackprinceton-fall-26.devpost.com/
