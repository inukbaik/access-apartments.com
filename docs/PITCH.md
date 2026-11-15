# Pitch: 3 minutes, then 3 minutes of questions

Setup before the judges arrive: `.venv/bin/python -m finder.web --warm --no-llm`, open
http://localhost:8800, run the "Los Angeles: USC / W 36th St" search once. Keep a second tab on
"Houston: Aldine". If the wifi dies, searches and homes already opened still load from the cache.

## The one idea to get across

A scan already knows how wide every door is. We read it, we fail anything we can't measure, and we
show you the door.

## Script

| Time | Who shows what | Say |
|---|---|---|
| 0:00 to 0:25 | No screen | "A listing never tells you if a wheelchair fits through the bathroom door. You find out at the viewing. But the listing's 3D scan already knows." |
| 0:25 to 0:45 | Page, USC search loaded | "You say what you need and where. We measure every scanned home nearby: hallways 36 inches, doorways 32, a 60 inch turning circle in a bathroom. 4 of these 10 pass. Anything the scan can't measure is a fail, and it says so: 'no data'." |
| 0:45 to 1:15 | Click the first home (fits) | "This is the floor plan, drawn from the scan. Every gap is a doorway with its width. Below: the building is 4 stories by CoStar's record, and Vexcel's roof height agrees. No elevator on record, and we say 'unavailable', not 'no'." |
| 1:15 to 1:50 | Scroll the list to the 8th row, "7BR, 7BA" at 1299 W 36th St; click it, then a red label | "This one fails. Red doorways are under 32 inches. Click one and you see that door, in a photo rendered from the scan. Grey ones are closets; we don't count them. You don't have to trust us: you can look." |
| 1:50 to 2:20 | Second tab, Houston Aldine, first home | "These listings mention step-free entry. The scan still flags doorways. Here: this 29 inch one is the door to the garage. A person sees in five seconds whether that matters to them. That is the point of the evidence." |
| 2:20 to 2:45 | Back to no screen, or the README numbers | "We ran 800 random listings in LA and Houston. 12 pass everything. Doors are the bottleneck: 16 percent pass where doors are mapped. And three in four scans are missing data for at least one check." |
| 2:45 to 3:00 | | "An AI agent takes the request in plain words, but it can't change a verdict; only measurements can. Next: the entrance, from Vexcel's aerial images." |

If something breaks: keep talking over the USC results already on screen. Do not re-run a search.
Only tick the AI agent box if a judge asks to see it, and only on the USC search (about 25 s).

## Questions to expect

**Where is the AI?** A local model (qwen3 on Ollama) reads the request, chooses the checks, and
searches the listing text for needs a scan can't measure. It never decides pass or fail; notes that
contradict the measurements are withheld. We kept it local so CoStar's data never left the laptop.

**How accurate are the measurements?** They are the scan's own mapped openings and room sizes. We
have not checked them against a tape measure. Hallway and bathroom sizes are bounding boxes, and
door widths can include the frame, so a pass means "worth a visit", not a guarantee. The page says
this next to each number.

**Is 1.5% real, or just missing data?** Both, and we separate them. 590 of 800 scans lack data for
at least one check. Of the 206 with all three measured, 12 pass. Where doors are mapped, 16% pass.

**Why fail on missing data? Isn't that unfair to the listing?** The cost of a wrong "pass" is a
wasted trip for someone for whom trips are hard. The cost of a wrong "fail" is one missed listing,
and the page shows why it failed.

**A home with four floors passes?** Yes, today. We don't check stairs or the entrance. The page
says so on any multi-floor scan, and shows stories and elevator as information. It is the first
thing we would add.

**Why these thresholds?** They are the ADA figures: 32 in clear door width, 36 in route width, 60
in turning circle. The user's needs could change them; the agent's first step sets requirements.

**What about closets?** The scan labels rooms. A doorway into a closet or pantry isn't counted.
A doorway into a room with no label still counts, because we can't tell.

**How does the doorway photo work?** We know where the doorway and each panorama are on the floor
plan. We pick the nearest panorama with a clear line of sight and render a camera view toward the
doorway from its cube-map images.

**How does it use CoStar's layers?** Matterport: geometry and panoramas. CoStar records: listing
text, stories, elevators. Vexcel: roof height to cross-check stories. Each source is named where
it is used.

**What if the scan data is wrong or the API changes?** Every reply from Matterport, Vexcel and the
model is checked for type and shape before we use it. A bad reply fails with the name of the field,
that listing goes last with the error shown, and nothing bad is cached. In our caches: 121 of 5,091
mapped doorways are under 20 in, which we report as "bad measurement" instead of trusting.

**Does it scale?** Each listing is one API call and pure functions; results are cached. The 800
listing survey ran in a few minutes.

**What happened to the glasses?** We tested matching a glasses photo to a spot in a scanned
building. About 4 of 6 matched. Not reliable enough to put on someone's face, so we cut it.

## Things not to claim

- Not "these homes are accessible". Say "these pass the three measured checks".
- Not "the Houston listings lie". Their fails are a garage door, unlabelled small rooms and
  hallways the scan didn't label. Say "the scan can't confirm it, and here is what to look at".
- Not "validated". Nothing was measured by hand.

## Backup video (optional, 2 minutes max)

1. Start the server as above and load the USC search.
2. Press Cmd+Shift+5, choose "Record Selected Portion", drag over the browser window, and turn on
   the microphone under Options.
3. Press Record and go through 0:25 to 2:20 of the script. Press the stop button in the menu bar.
4. Upload the .mov from the Desktop to YouTube as "Unlisted" and paste the link into Devpost.
