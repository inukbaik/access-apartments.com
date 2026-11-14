# Discussion log: how we got to this idea

A summary of the brainstorming session (Fri Nov 13, 10 PM to Sat Nov 14, 3 AM) that led to the current plan, so teammates who weren't there have the reasoning. The current plan itself lives in [`PROJECT_CONTEXT.md`](../PROJECT_CONTEXT.md).

---

## 1. Starting point (Fri ~10 PM)

**Goal:** use Meta Ray-Ban glasses for a project, leaning toward the Education track, ideally helping someone with a disability in everyday life.

**Facts from the hacker packet that shaped everything:**
- Meta glasses are **not** in the MLH hardware kit (they're actually the Entertainment track prize), so we bring our own.
- We must pick **one** main track but can stack any number of special tracks.
- Judging: Creativity, Utility, Charity, Avidity; a 2 min live demo is required.
- Deadline: 8 AM Sunday.

**How developers use the glasses:** Meta's Wearables Device Access Toolkit (developer preview). A phone app (iOS or Android) gets the camera stream and photos, the microphone, the speakers and the button events. All the AI runs on the phone or in the cloud; the glasses are eyes, ears and a private speaker. Standard Ray-Bans have no display we can draw on. A Mock Device Kit lets people without glasses develop using the phone camera.

## 2. First idea: classroom companion for blind and low vision students

The glasses would read whiteboards and slides into the student's ear, answer spoken questions and build notes.

**Rejected by the team because:**
- Too simple; specialized products and LMS accessibility features (e.g. Brightspace) already cover it.
- Talking out loud in class is impractical.
- Children or cognitively impaired users may not like the glasses or may treat them like a toy.
- **The big one:** why not just take out your phone and ask an AI?

## 3. The "why not your phone?" filter

Glasses only beat a phone when:
1. The user **didn't know they'd need it** (passive capture of a moment nobody would photograph).
2. Their **hands are busy, gloved or sterile**.
3. Their **attention has to stay on another person**.

Design insight: put the glasses on the capable caregiver or worker, not the vulnerable person.

## 4. Second round of ideas

| Idea | Track | Outcome |
|---|---|---|
| Hands-free behavior logging for special ed / ABA therapists (tap to save the 30 s before an incident) | Education | **Rejected:** privacy and recording minors |
| Lab bench copilot: logs wet lab steps and catches skipped steps or wrong reagents | Science + Discovery | Team asked how a model could know right from wrong. **Answer:** it checks against the lab's written protocol (SOPs, protocols.io) turned into a checklist, or a "reference run" recorded by an expert. It verifies observable checkpoints (labels, order, timers), not volumes or chemistry. **Kept as a backup**, but it drops the disability angle |
| Retrospective memory aid for early dementia ("did I take my pills?") | Healthcare | Liked, but privacy concerns. Redesigned as **object-scoped memory**: only remember registered objects, discard every other frame. Then **battery**: continuous streaming lasts roughly 30 to 60 min, so it would need event triggers (medication schedule, leaving home, head tilt). That shrinks it to a medication adherence tracker, which competes with smart pill dispensers. **Shelved** |

## 5. Pivot to the CoStar track (Sat ~1:50 AM)

The CoStar special track (Inside and Out: AI for the Built World) has the biggest prizes: $1,500 / $500 / $250 cash plus interview fast tracks. It welcomes accessibility tools. It provides Houston and LA data from three layers: **CoStar property records, Matterport 3D scans, Vexcel aerial imagery.**

**First version:** a wheelchair / ADA arrival guide for destinations in Houston or LA (parking, step-free entrance, indoor route), with glasses as an optional aid for visually impaired users.

## 6. Testing viability against the real data

We read the track's reference page (one example house walked through every data type). Key findings:
- **~15,000 Matterport models** (13,014 "Commercial", 1,930 "Residential"). But the "commercial" samples are named like "6BR, 5BA, 1,846SF", so they look like **apartment units, not clinics or offices**. CoStar's own unsolved problems list says they don't label commercial room types yet.
- **Per model:** panoramas (plus an AI defurnished version), rooms with type and measured width/depth/height, a wall graph, floor plans, a mesh and point cloud (unlocked for 232 models, more coming), and for 232 models a drone-based 3D exterior.
- **Interiors were scanned for listings; exteriors are often missing.**
- **Vexcel:** 7.5 cm aerial images around any lat/lon, oblique images, elevation, object detection; Houston and LA only.
- **CoStar records:** join via listing id; the join is untested by CoStar.
- **Door widths are unconfirmed:** the example only shows `wall` edges.

**Conclusion:** a public destination guide isn't well supported. The data fits an **accessible housing finder** much better: hallway widths and bathroom sizes come straight from the API. In the example house, the hallway is 0.88 m (~34.6 in), under the ADA 36 in route minimum; the bathroom fits a 60 in turning circle. This also matches CoStar's unsolved problems: finding amenities, agentic annotation, predicting listing attributes from scans.

At that point the glasses no longer fit, because indoor guidance couldn't be demoed from Princeton.

## 7. The venue scan changes things (Sat ~2:00 AM)

A teammate found a public Matterport scan of **Rabinowitz Hall**, our hacking venue: https://my.matterport.com/show?m=P3S6VUTP3qB (Floors 2 and 3 seen).

**New glasses role: indoor localization.** Match the glasses' camera frame against the venue panoramas to find the nearest scan position and heading, then speak step-free directions ("elevator about 20 m ahead on your left"). That passes the phone test (a blind user can't easily aim a phone; a wheelchair user's hands are on the wheels), and now it can be **demoed live in the judging building**.

**Combined product:**
- **Before you go:** screen Houston/LA listings for accessibility.
- **When you're there:** glasses guide you through the building's digital twin.

**Risks:** whether our key can read the venue scan; Floor 1 coverage; furniture and crowds differing from scan day. Hence a 5 photo smoke test (pass = 3 of 5).

## 8. Differentiation from openrouteservice and similar

openrouteservice's wheelchair profile routes along streets and sidewalks using OpenStreetMap tags. We cover what it doesn't:
1. **It stops at the front door.** We cover the inside, where GPS fails and OpenStreetMap is nearly empty.
2. **It answers "how do I get there"; we answer "should I go there / can I live there."**
3. **Measured data** (3D scans, 7.5 cm imagery) vs patchy crowdsourced tags.
4. **The last 50 m:** accessible parking stalls, access aisles, step-free entrances.
5. **Hands-free, eyes-free** spoken guidance vs a map on a screen.

**Best framing:** use openrouteservice for the street part of the trip and hand off at the curb. *"openrouteservice gets you to the curb; we take you from the parking spot to the bathroom."*

Google Maps' wheelchair routes and entrance info, and Wheelmap's crowdsourced ratings, get the same answer: they give a yes or no about a place, or a sidewalk route; we measure the inside and guide people through it.

## 9. Where things stand

- The plan, phases and risks are in [`PROJECT_CONTEXT.md`](../PROJECT_CONTEXT.md).
- Test scripts are in [`../scripts/`](../scripts/README.md): `phase0_check.py` (data questions) and `localize_test.py` (photo → scan position).
- **Next decision:** after Phase 0. If localization passes, build both halves; if it fails, drop the glasses and go all in on the housing finder.
