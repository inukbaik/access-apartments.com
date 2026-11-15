# Devpost draft: Accessible Spaces

Draft for the Devpost form. Track: CoStar "Inside and Out: AI for the Built World".
Numbers come from `finder.survey` and the demo searches run on Sun Nov 15.

**Tagline:** Find a home you can get around in: every listing measured from its own 3D scan.

## Inspiration

A listing almost never says whether a wheelchair fits through the bathroom door. People find out by
travelling to the viewing. The answer is already in the data: many listings have a Matterport scan,
and the scan knows how wide each doorway is. Nobody reads it for this.

## What it does

You say what you need and where you want to live. Accessible Spaces measures every scanned listing
nearby and ranks the buildings.

- **Three measured checks.** Hallway at least 36 in, every doorway at least 32 in, and a bathroom
  with room for a 60 in turning circle.
- **Uncertainty means failure.** A check passes only when the scan has the measurement and it meets
  the threshold. Missing data fails as "no data"; an implausible value fails as "bad measurement".
  We never present a guess as a fact.
- **Evidence for every verdict.** Click a home to see its floor plan drawn from the scan, with every
  doorway labelled with its width, and a photo of each doorway rendered from the nearest panorama.
  You can see the door that failed and decide for yourself whether it matters.
- **Needs a scan can't measure.** For a roll-in shower, grab bars or step-free entry, it searches
  the CoStar listing text and reports "listing says" (with the quote) or "information unavailable".
  These never count as a pass or a fail.
- **The building.** Stories from CoStar records, cross-checked against Vexcel roof height, and the
  elevator status from CoStar. Information only: it never changes the ranking.
- **Plain-language requests.** A local LLM turns "I use a power wheelchair and need step-free
  entry" into tool calls. Our code does all the measuring; the model cannot change a verdict.

## How we built it

- **Matterport Model API (GraphQL):** rooms with their classifications and sizes, wall edges with
  door openings, room boundaries, and panoramas with their positions.
- **Checks** are pure functions over that data (`finder/checks.py`). Doorways into a room the scan
  classifies as a closet or pantry are shown but not counted.
- **Doorway photos:** for each doorway we pick the nearest panorama with a clear line of sight,
  then render a normal camera view from its cube-map faces, aimed at the doorway.
- **CoStar records kit:** listing text for the extra needs (a reviewed phrase catalog, so "walk-in
  shower" never counts as a roll-in shower), stories and elevator records.
- **Vexcel:** roof height of the building footprint at the listing's coordinates.
- **Agent:** any OpenAI-compatible server. We ran `qwen3:8b` on Ollama, so sponsor data stayed on
  the laptop. If the model is slow or wrong, the page shows the measured results without it.
- **Data validation:** everything from outside (Matterport, Vexcel, the LLM server) is checked for
  type and shape with pydantic before use. Bad data fails loudly with the field that was wrong and
  is never cached. The code is type-checked with mypy, and a report (`finder.data_quality`) counts
  what the caches are missing.
- **Web page:** Python standard library server and one HTML file, no framework.

## Challenges we ran into

- **Most scans have a gap.** In 590 of 800 listings the scan lacks the data for at least one
  check. We had to decide what missing data means, and chose failure.
- **Aiming the camera.** Our first doorway photos pointed at walls and windows: we had the
  panorama rotation the wrong way round. It looked right on panoramas facing "north" and wrong
  everywhere else. We found it by drawing where the scan's windows should appear on the image.
- **Closet doors.** A 24 in closet door failed whole homes. The scan says which room each doorway
  borders, so closets and pantries are now left out.
- **One row per building.** Units of one building arrive as separate scans with differently
  written addresses; we parse and group them.
- **A small model as an agent.** It spent its step budget, then sent the last call in the wrong
  shape. The loop now accepts that, and always falls back to the measured results.

## Accomplishments that we're proud of

- Every number on the page can be traced to a doorway you can look at.
- The model plans the search but cannot pass a home that our measurements fail. Notes that
  contradict the measurements are withheld.
- It runs on real sponsor data for two cities, not on a hand-picked example.
- It fails loudly. Missing data, an implausible value, a malformed API reply and a slow model each
  produce a named reason on screen instead of a silent guess.

## What we learned

In 800 random home listings in Los Angeles and Houston, **12 pass all three checks (1.5%)**.

- Doors are the bottleneck: where doorway widths exist (412 listings), 16% pass. Hallways pass
  in 79% of the listings that have one measured, bathroom turning space in 65%.
- Of the 206 listings where all three could be measured, 12 pass.
- So the result is two findings: narrow interior doors are common, and most scans are not yet
  labelled well enough to say.

## What's next for access-apartments.com

- **The entrance.** We do not check steps at the door. Vexcel oblique images could.
- **Stairs inside a home.** A home with several floors can pass today; the page says that stairs
  are not checked.
- **Clear widths.** Hallway and bathroom sizes are room bounding boxes, and door widths can
  include the frame. A pass means "worth a visit", not a certificate. Measuring from the scan's
  mesh would fix this.
- **Validation** against a tape measure in a few scanned homes.
- We also tested finding your position inside a scanned building from a phone or Ray-Ban Meta
  glasses photo (about 5 of 7 phone photos matched the right spot). It was not reliable enough to
  demo; it is the next part.

## Built with

Python, Matterport Model API (GraphQL), Vexcel API, CoStar records kit, Ollama (qwen3:8b), pydantic,
mypy, NumPy, Pillow, usaddress, HTML, CSS, JavaScript.

## Links

- Repo: https://github.com/inukbaik/hack-p-thon
- Video: (add link)

## Other form fields

**Elevator pitch:** Find a home you can get around in: every listing measured for wheelchair access
from its own 3D scan.

**Did you implement a generative AI model or API?** Yes. A local large language model, `qwen3:8b`
on Ollama, through its OpenAI-compatible API.

- **How.** The model is the planning layer. It reads a request in plain words and calls our tools:
  set the checks, search the area, inspect a building, search the listing text for needs a scan
  can't measure, and finish with a short note. Our code does all the measuring and ranking.
- **Guardrails.** The model never decides pass or fail and cannot drop a check. Its notes are
  withheld if they contradict the measurements or the listing text. If it is slow, unreachable or
  makes bad tool calls, the page shows the measured results without it.
- **Why.** People describe access needs in their own words. We ran the model locally so the
  sponsor's data never left the laptop, and kept verdicts out of its hands because a wrong "pass"
  sends someone to a home they can't use.

**Technology feedback:**

- **Matterport Model API.** Room classifications, door openings with widths, room boundaries and
  panorama positions were enough to measure doorways and draw floor plans without the mesh. The
  panorama rotation and cube-map face conventions are not documented clearly, signed image links
  expire within minutes, and coverage is uneven: in our 800-listing sample 71% of scans had no room
  labelled hallway and 47% had no mapped doorway. Schema introspection worked well.
- **CoStar records kit.** Listing text, stories and elevator fields joined cleanly to the scans.
  Commercial amenities come only as ids with no catalog of names. Addresses of units in one
  building are written in many ways.
- **Vexcel API.** Roof height per footprint was a useful cross-check on story counts. 23 of our 60
  lookups were unusable (no footprint, no property data, or an implausible height).
- **Ollama with qwen3:8b.** Tool calling worked and the data stayed local. A model this small
  needs guardrails; runs took 25 to 50 seconds.
