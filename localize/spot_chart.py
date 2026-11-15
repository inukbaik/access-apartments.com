"""Chart of every scan spot: floor maps with spot numbers, scan pictures, and how each spot did on
the saved phone walks. Writes out/spot_chart.html (git-ignored: it embeds the venue's scan images).

    python -m localize.spot_chart
"""
import base64
import io
import json
from collections import Counter
from pathlib import Path

from localize.graph import WalkGraph
from localize.index import DEFAULT_EMBED, DEFAULT_MODEL, load
from localize.server import FRAMES_DIR, reference_view

OUT = Path("out/spot_chart.html")

# What a spot is, from looking at its scan pictures and the phone walks. Fill in more as we learn.
NOTES = {
    "28": "Entrance arcade: gothic arches, glass doors",
    "27": "Entrance hall at the atrium edge",
    "0": "Atrium floor (tables)", "1": "Atrium floor, center", "2": "Atrium floor near the stairs",
    "3": "Atrium floor", "4": "Atrium floor", "5": "Atrium floor", "6": "Atrium floor, arches behind",
    "7": "Atrium floor near the stairs", "33": "Atrium floor", "34": "Atrium floor, art glass above",
    "35": "Atrium main staircase (Floor 2)",
    "23": "Atrium edge by the stairs",
    "32": "Floor 2 elevator",
    "21": "Glass doors with poster",
    "16": "Hallway along the atrium railing", "15": "Hallway along the atrium railing",
    "19": "Hallway overlooking the atrium",
    "14": "Hallway with exit sign and dark doors",
    "13": "Hallway along the atrium railing",
    "31": "Wood niche with bench",
    "25": "Wood-panel hallway with directory sign",
    "18": "Frosted-glass hallway (same x/y as 64 on Floor 3)",
    "40": "Glass meeting room", "41": "Glass meeting room", "42": "Glass meeting room (lectern)",
    "43": "Glass meeting room by the atrium",
    "50": "Art-glass wall", "51": "Next to the art-glass wall",
    "49": "Overlook of the atrium stairs",
    "47": "Floor 3 elevator (above 32)",
    "36": "Atrium overlook by the glass box",
    "45": "Wood wall with exit sign",
    "38": "White counter by a window",
    "65": "Hallway near a glass stairwell door",
    "64": "Hallway with exit sign (same x/y as 18 on Floor 2)",
    "61": "Above spot 13",
}


def walk_results():
    """label -> Counter of statuses across all saved walks (best guess label for 'unknown')."""
    res = {}
    for f in FRAMES_DIR.glob("*/*.json"):
        r = json.loads(f.read_text())
        res.setdefault(r["best_guess"]["label"], Counter())[r["status"]] += 1
    return res


def strip(model_id, pano_id):
    imgs = []
    for h in (0, 90, 180, 270):
        jpg = reference_view(model_id, pano_id, h)
        imgs.append(f'<img src="data:image/jpeg;base64,{base64.b64encode(_small(jpg)).decode()}" '
                    f'alt="heading {h}" title="heading {h}">' if jpg else "<span>no image</span>")
    return "".join(imgs)


def _small(jpg):
    from PIL import Image
    img = Image.open(io.BytesIO(jpg))
    img.thumbnail((180, 180))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    return buf.getvalue()


def verdict(c):
    if not c:
        return "untested", "Not walked yet"
    good = c["ok"] + c["held"]
    if good and good >= c["unknown"]:
        return "good", f"Matched ({c['ok']} ok, {c['held']} held, {c['unknown']} not sure)"
    if good:
        return "mixed", f"Mixed ({c['ok']} ok, {c['held']} held, {c['unknown']} not sure)"
    return "unsure", f"Only 'not sure' guesses ({c['unknown']})"


def floor_svg(index, graph, floor, results):
    ii = [i for i, f in enumerate(index.floor) if f == floor]
    xs, ys = index.pos[ii, 0], index.pos[ii, 1]
    pad, scale = 2.0, 30
    x0, y1 = xs.min() - pad, ys.max() + pad
    w, h = (xs.max() - xs.min() + 2 * pad) * scale, (ys.max() - ys.min() + 2 * pad) * scale
    px = lambda i: ((index.pos[i, 0] - x0) * scale, (y1 - index.pos[i, 1]) * scale)  # north up
    parts = [f'<svg viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="{floor} map">']
    for i in ii:
        for j in graph.adj[i]:
            if j > i:
                (ax, ay), (bx, by) = px(i), px(j)
                parts.append(f'<line x1="{ax:.0f}" y1="{ay:.0f}" x2="{bx:.0f}" y2="{by:.0f}" class="edge"/>')
    for i in ii:
        p = index.panos[i]
        cls, _ = verdict(results.get(p["label"]))
        x, y = px(i)
        parts.append(f'<a href="#spot-{p["label"]}"><title>{p["label"]}: {NOTES.get(p["label"], "")}</title>'
                     f'<circle cx="{x:.0f}" cy="{y:.0f}" r="15" class="dot {cls}"/>'
                     f'<text x="{x:.0f}" y="{y + 5:.0f}">{p["label"]}</text></a>')
    parts.append("</svg>")
    return "".join(parts)


def main():
    index = load(DEFAULT_MODEL, DEFAULT_EMBED)
    graph = WalkGraph(index)
    results = walk_results()
    model_id = index.meta["model_id"]
    floors = sorted(set(index.floor))

    maps = "".join(f"<section><h2>{f}</h2>{floor_svg(index, graph, f, results)}</section>" for f in floors)
    rows = []
    order = sorted(range(len(index.panos)), key=lambda i: (index.floor[i], int(index.panos[i]["label"])))
    for i in order:
        p = index.panos[i]
        cls, text = verdict(results.get(p["label"]))
        rows.append(f'<tr id="spot-{p["label"]}"><td class="num">{p["label"]}</td><td>{p["floor"]}</td>'
                    f'<td>{NOTES.get(p["label"], "<span class=muted>see pictures</span>")}</td>'
                    f'<td><span class="badge {cls}">{text}</span></td><td class="strip">{strip(model_id, p["id"])}</td></tr>')

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(PAGE.format(name=index.meta["name"], maps=maps, rows="".join(rows)))
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Scan Spot Chart</title>
<style>
:root {{ --bg:#fff; --fg:#111; --muted:#666; --line:#ccc; --good:#2e9e4f; --mixed:#e0a526; --unsure:#d0503c; --untested:#9aa3ad; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141414; --fg:#eee; --muted:#999; --line:#444; }} }}
body {{ margin:0; padding:16px; background:var(--bg); color:var(--fg); font:15px/1.4 system-ui, sans-serif; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:17px; margin:8px 0; }}
.muted {{ color:var(--muted); }}
.maps {{ display:flex; flex-wrap:wrap; gap:16px; }} .maps section {{ flex:1 1 420px; min-width:0; }}
svg {{ width:100%; height:auto; border:1px solid var(--line); border-radius:8px; }}
.edge {{ stroke:var(--line); stroke-width:2; }}
.dot {{ stroke:#0006; stroke-width:1; }} .dot.good {{ fill:var(--good); }} .dot.mixed {{ fill:var(--mixed); }}
.dot.unsure {{ fill:var(--unsure); }} .dot.untested {{ fill:var(--untested); }}
svg text {{ font:bold 13px system-ui; fill:#fff; text-anchor:middle; pointer-events:none; }}
.legend span {{ display:inline-block; margin-right:14px; }} .legend i {{ display:inline-block; width:12px; height:12px; border-radius:50%; margin-right:4px; vertical-align:-1px; }}
.table-wrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; margin-top:16px; }}
td, th {{ border-bottom:1px solid var(--line); padding:6px; text-align:left; vertical-align:middle; }}
td.num {{ font-weight:700; font-size:18px; }}
.strip img {{ width:110px; height:110px; object-fit:cover; margin-right:3px; border-radius:4px; }}
.badge {{ padding:2px 8px; border-radius:10px; color:#fff; font-size:13px; white-space:nowrap; }}
.badge.good {{ background:var(--good); }} .badge.mixed {{ background:var(--mixed); }}
.badge.unsure {{ background:var(--unsure); }} .badge.untested {{ background:var(--untested); }}
tr:target {{ outline:3px solid var(--mixed); }}
</style></head><body>
<h1>Scan spots: {name}</h1>
<p class="muted">Each number is a Matterport scan position. Lines are walking links (same floor, at most 8 m).
Map: x/y from the scan, top = scan +y (not necessarily north). Tap a spot to jump to its pictures.
Pictures are 4 directions from the scan (headings 0/90/180/270). Walk results count every saved phone frame whose best guess was that spot.</p>
<p class="legend"><span><i style="background:var(--good)"></i>matched on a walk</span><span><i style="background:var(--mixed)"></i>mixed</span>
<span><i style="background:var(--unsure)"></i>only "not sure"</span><span><i style="background:var(--untested)"></i>not walked yet</span></p>
<div class="maps">{maps}</div>
<div class="table-wrap"><table><thead><tr><th>Spot</th><th>Floor</th><th>What it is</th><th>Phone walks</th><th>Scan pictures</th></tr></thead>
<tbody>{rows}</tbody></table></div>
</body></html>"""


if __name__ == "__main__":
    main()
