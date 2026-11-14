# Proposal: AI Accessible-Route Agent (HackPrinceton F26)

> **For teammates and their coding agents:** this file holds the agreed direction, the reasoning
> behind it, and the decisions still open. Read it before writing code. Facts about rules and
> prizes come from `F26 Onsite Hacker Packet - Google Docs.pdf` in this repo. Anything marked
> **(unverified)** has not been checked yet.

## 1. Constraints from the hacker packet

| Item | Detail |
|---|---|
| Deadline | **8:00 AM Sunday, Nov 15, 2026** (hard). Devpost submission with a public GitHub repo. |
| Repo rule | Repo must be created Nov 13–15. This repo was created Nov 13 at 9:40 PM ET, so it qualifies. |
| Main track | Exactly one. **Chosen: Education** ("make learning more interactive, accessible, or personalized"). |
| Special track | **Chosen: Amazon, Best Practical AI Innovation.** Ignore the other special tracks for now. |
| Demo | Live, in person, **2 minutes max**: the problem, then a walkthrough. An optional 2-minute video goes on Devpost. |
| Main judging | Creativity, Utility, Charity (societal need), Avidity (passion and polish). |
| Team | Max 4. Add Discord usernames to the submission. |

### Amazon track: what we must hit
- Scoring: **Creativity 25%, Usefulness 25%, Technical Implementation 25%, User Experience 25%**.
- Focus: **agentic behavior** (reason, plan, take multi-step actions), **adaptive intelligence**
  (learn from context, feedback, preferences), real-world impact, simple UX.
- Required deliverables: a **working prototype**, a **clear use case and target user**, **basic
  documentation**, and a **pitch**.
- The packet's example ideas include "an accessibility tool that uses voice, vision, or gesture
  to help underserved users navigate".

**Implication:** a map that calls a routing API is not enough. It has to be an **agent** that
plans, verifies, re-plans and adapts.

## 2. Problem and pitch

**Problem:** Google Maps has no wheelchair-aware walking routes. It only flags
wheelchair-accessible transit. A student who uses a wheelchair cannot tell whether the "5-minute
walk" to class has stairs, a steep grade, a missing curb ramp, or an entrance that is only
reachable by steps.

**Pitch (Education framing):** an AI mobility agent that gets students with disabilities to
class, labs and events. It plans routes within their limits, explains every decision, admits
what it doesn't know, and learns from reports.

**Target user:** a university student or campus visitor who uses a wheelchair or has limited
mobility.

**Demo location: the HackPrinceton venue.** The packet includes maps of JRR, LAS, Friend Center
and Robertson (SPIA). Judges know these buildings, so "Friend Center → JRR, no stairs, max 5%
slope" is instantly relatable, and we can check the route on foot on Saturday.

## 3. Prior art and how we differ

| Existing | What it does | Gap |
|---|---|---|
| Google Maps | Wheelchair-accessible transit flag | No sidewalk, slope or curb awareness |
| AccessMap (UW, OpenSidewalks) | Slope-aware sidewalk routing in select cities | Static data, no reasoning, limited coverage |
| Wheelmap | Crowdsourced place accessibility | Places only, no routing |
| OpenRouteService `wheelchair` profile | Routing by surface, incline, kerb and width | Relies on OSM tags, which are sparse; silent when data is missing |

**Our differentiator:** a **verify-and-explain agent**. OSM accessibility tags are incomplete, so
the agent checks segments with more evidence (elevation, street imagery), marks unknowns honestly
with a confidence level, re-plans around barriers, and remembers user feedback.

## 4. Architecture

```
[React map UI] ──request + user profile──▶ [Backend API]
                                              │
                                              ▼
                                   [LLM agent, tool-use loop]
                                              │ calls tools
        ┌───────────────┬───────────────┬─────┴─────────┬──────────────────┬────────────────┐
        ▼               ▼               ▼               ▼                  ▼                ▼
   geocode    get_candidate_routes  get_elevation  get_segment_     check_street_image  report_barrier /
                                    _profile       accessibility    (vision LLM on      get_user_reports
                                                   (OSM tags)       Mapillary photos)   (feedback store)
```

### Agent loop
1. Parse the request ("Friend Center to JRR, I can't do slopes over 5%").
2. Load the user profile: max slope, min width, curb ramp required, surface preferences, fatigue limit.
3. Generate 2–3 candidate routes.
4. Verify each segment with OSM tags, slope from elevation, user reports and (stretch) image checks.
5. Reject routes that fail, or **re-plan** around the failing segment.
6. Return the chosen route with **per-segment explanations and confidence**, e.g. "Avoiding
   the Nassau St crossing: no curb ramp visible; 2 users reported it blocked."
7. **Adaptive:** user feedback ("that ramp was blocked") is stored and changes future routes.
   Showing this live is the strongest demo moment.

### Data sources (free)
| Need | Source |
|---|---|
| Sidewalks, crossings, curbs, surface, incline | OpenStreetMap (`highway=footway`, `footway=sidewalk/crossing`, `kerb`, `surface`, `incline`, `wheelchair`, `width`) via Overpass API |
| Elevation and slope | USGS 3DEP or Open-Elevation; compute grade per segment |
| Routing engine | OpenRouteService `wheelchair` profile, **or** our own A* on an OSM graph (networkx/osmnx) with custom edge costs. Our own graph makes re-planning and feedback easier. |
| Street imagery (stretch) | Mapillary API plus a vision LLM to spot stairs, missing curb cuts, obstructions |
| Map display | MapLibre GL or Leaflet with OSM tiles |

### Amazon tie-in (optional, decide as a team)
- Run the agent on **Amazon Bedrock** (Claude models are available there). This is a nice nod to
  the sponsor and not a requirement.
- Amazon Location Service for geocoding or base maps. **(unverified)** whether its pedestrian
  routing supports accessibility constraints; check before relying on it.

## 5. Scope

**Must work (MVP):**
- Princeton campus area only.
- One user profile with editable limits.
- Start and destination in; standard route vs accessible route side by side on the map.
- Agent explanation with per-segment reasons and an "unknown" marking.
- Feedback that re-routes live.

**Stretch:** vision check on street imagery; voice input and output; building entrance data.

**Cut:** global coverage, accounts and auth, turn-by-turn navigation, native mobile app.

## 6. Build order and timeline

| When | Work |
|---|---|
| Fri night / early Sat | Repo skeleton. Pull the campus OSM graph. Slope-aware routing works from a script. |
| Sat morning | Agent loop with tools and explanation output. |
| Sat afternoon | Map UI: profile panel, two routes, segment highlights with reasons. |
| Sat evening | Feedback, re-route, persistence. Walk the demo route and fix bad data. |
| Sat night | Stretch features if stable. README, Devpost write-up, 2-minute video. |
| Before 8 AM Sun | Submit. Rehearse the 2-minute live demo. |

## 7. Demo script (2 minutes)
1. **Problem (20s):** "Google says 6 minutes from Friend Center to JRR. For a wheelchair user that
   route has stairs and a steep grade."
2. **Request (20s):** type or say the destination and limits.
3. **Agent at work (40s):** candidate routes, rejected segments with reasons, the chosen route
   with confidence.
4. **Adaptive moment (25s):** report "ramp blocked" and watch the agent re-plan.
5. **Impact and future (15s):** campus rollout, crowdsourced verification, other cities.

## 8. Open decisions (answer before coding)
- [ ] **Stack:** Python (FastAPI) backend with a React frontend? (Suggested; a teammate already
  has FastAPI experience.)
- [ ] **LLM provider:** Amazon Bedrock or the Anthropic API directly?
- [ ] **Routing:** OpenRouteService wheelchair profile vs our own osmnx/networkx graph? (We
  suggest our own graph, for control over re-planning and feedback.)
- [ ] **Team:** size, roles and task split.
- [ ] **Hardware:** a Ray-Ban Meta glasses barrier feed is possible (see
  `HACKATHON_CONTEXT.md`) but risky in this timeframe. Only consider it if someone already has
  it working.

## 9. Notes for coding agents
- Never commit API keys. Use `.env`, and add it to `.gitignore`.
- Keep the MVP path working at all times. Stretch work goes on branches.
- When OSM data is missing, the agent must say "unknown", never assume accessible.
