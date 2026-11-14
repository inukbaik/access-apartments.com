#!/usr/bin/env python3
"""Phase 0 data checks for the accessible spaces project.

Answers the go / no go questions from PROJECT_CONTEXT.md:
  1. Does our key work, and how many models does it see?
  2. Does the wall graph expose door openings (so we can get door widths)?
  3. Can our key read the Rabinowitz Hall venue scan?
  4. What is actually in models_index.csv (how many "commercial" models are apartments)?
  5. On a sample of models: hallway widths, bathroom turning space, and which edge types show up.

Usage:
  python scripts/phase0_check.py
  python scripts/phase0_check.py --index data/models_index.csv --sample 40 --venue P3S6VUTP3qB

Writes a full JSON report to out/phase0_report.json.
"""
import argparse
import csv
import json
import os
import random
import re
from collections import Counter

from mp_common import TYPE_REF, graph, unwrap_type

M_TO_IN = 39.3701
HALL_MIN_IN = 36.0  # ADA continuous accessible route width
DOOR_MIN_IN = 32.0  # ADA door clear width
TURN_DIAM_M = 1.524  # 60 in wheelchair turning circle


def section(title):
    print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)


# ---------------------------------------------------------------- 1. key check
def check_key(report):
    section("1. Key check")
    data, errors = graph(
        "{ rootFolder { name modelCountSummary(includeModelsInSubfolders: true) "
        "subfolders { results { id name modelCountSummary(includeModelsInSubfolders: true) } } } }"
    )
    if errors:
        print("Errors:", errors)
    root = (data or {}).get("rootFolder") or {}
    print(f"Folder '{root.get('name')}' holds {root.get('modelCountSummary')} models")
    for sub in (root.get("subfolders") or {}).get("results", []):
        print(f"  {sub['name']:<22} {sub['modelCountSummary']:>7}  (folder {sub['id']})")
    report["key_check"] = root


# ------------------------------------------------------- 2. openings in schema
def introspect_type(name):
    data, _ = graph(f'{{ __type(name: "{name}") {{ name fields {{ name {TYPE_REF} }} }} }}')
    return (data or {}).get("__type")


def check_openings(report):
    section("2. Do wall edges expose door openings?")
    result = {"edge_fields": None, "opening_type": None, "opening_fields": None, "door_like_types": []}

    edge = introspect_type("Edge")
    if not edge:
        print("Could not introspect type 'Edge' (introspection may be disabled). Check in the Model Playground.")
        report["openings"] = result
        return None

    fields = {f["name"]: unwrap_type(f["type"]) for f in edge["fields"]}
    result["edge_fields"] = sorted(fields)
    print("Edge fields:", ", ".join(sorted(fields)))

    data, _ = graph("{ __schema { types { name } } }")
    names = [t["name"] for t in ((data or {}).get("__schema") or {}).get("types", [])]
    result["door_like_types"] = [n for n in names if re.search(r"open|door|portal", n, re.I)]
    print("Schema types that look door related:", result["door_like_types"] or "none")

    openings_selection = None
    if "openings" in fields:
        type_name, _ = fields["openings"]
        result["opening_type"] = type_name
        otype = introspect_type(type_name) if type_name else None
        if otype:
            scalar_fields = []
            for f in otype["fields"]:
                _, kind = unwrap_type(f["type"])
                if kind in ("SCALAR", "ENUM"):
                    scalar_fields.append(f["name"])
            result["opening_fields"] = scalar_fields
            print(f"YES: Edge.openings -> {type_name} with scalar fields: {scalar_fields}")
            if scalar_fields:
                openings_selection = "openings { " + " ".join(scalar_fields) + " }"
        else:
            print(f"Edge.openings exists (type {type_name}) but its fields could not be read.")
    else:
        print("NO 'openings' field on Edge. Door widths must come from panoramas or the point cloud.")

    report["openings"] = result
    return openings_selection


# ------------------------------------------------------------ 3. venue access
def check_venue(report, venue_id):
    section(f"3. Venue scan access ({venue_id})")
    data, errors = graph(
        """query V($id: ID!) { model(id: $id) {
             id name visibility floors { id label } rooms { id } panoLocations { id }
           } }""",
        {"id": venue_id},
    )
    model = (data or {}).get("model")
    if not model:
        print("NOT reachable with our key.", errors or "")
        print("Next step: ask in #costar-group to add it to the HackPrinceton folder.")
        print("Fallback: python scripts/localize_test.py --ref-dir <screenshots of the public tour>")
        report["venue"] = {"reachable": False, "errors": errors}
        return
    floors = [f["label"] for f in model.get("floors") or []]
    print(f"Reachable: '{model['name']}' ({model.get('visibility')})")
    print(f"  floors: {floors}")
    print(f"  rooms: {len(model.get('rooms') or [])}, panoramas: {len(model.get('panoLocations') or [])}")
    report["venue"] = {"reachable": True, "name": model["name"], "floors": floors,
                       "rooms": len(model.get("rooms") or []),
                       "panos": len(model.get("panoLocations") or [])}


# ------------------------------------------------------------- 4. index stats
def pick(row, *candidates):
    lower = {k.lower(): k for k in row}
    for c in candidates:
        if c in lower:
            return lower[c]
    return None


def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def check_index(report, path):
    section(f"4. models_index.csv ({path})")
    if not path or not os.path.exists(path):
        print("Index not found. Download models_index.csv from the hackathon site into data/ (see data/README.md).")
        report["index"] = None
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("Index is empty.")
        return []
    cols = list(rows[0].keys())
    print("Columns:", cols)

    c_sid = pick(rows[0], "sid", "model_id", "id")
    c_name = pick(rows[0], "name", "title")
    c_seg = pick(rows[0], "segment")
    c_rooms = pick(rows[0], "room_count", "rooms")
    c_splat = pick(rows[0], "splat", "has_splat")

    seg = Counter(r.get(c_seg, "?") for r in rows) if c_seg else Counter()
    bedroom_pattern = re.compile(r"\b\d+\s*BR\b", re.I)
    commercial = [r for r in rows if c_seg and r.get(c_seg, "").lower() == "commercial"]
    commercial_apts = [r for r in commercial if c_name and bedroom_pattern.search(r.get(c_name, ""))]
    with_rooms = [r for r in rows if c_rooms and to_int(r.get(c_rooms)) > 0]
    splats = [r for r in rows if c_splat and str(r.get(c_splat, "")).lower() in ("yes", "true", "1")]

    print(f"Total models: {len(rows)}")
    print(f"By segment: {dict(seg)}")
    if commercial:
        pct = 100 * len(commercial_apts) / len(commercial)
        print(f"'Commercial' models whose name looks like an apartment (e.g. '2BR'): "
              f"{len(commercial_apts)} of {len(commercial)} ({pct:.0f}%)")
    print(f"Models with room data: {len(with_rooms)}")
    print(f"Models with a splat: {len(splats)}")

    report["index"] = {
        "columns": cols, "total": len(rows), "by_segment": dict(seg),
        "commercial_named_like_apartments": len(commercial_apts),
        "with_rooms": len(with_rooms), "with_splat": len(splats),
    }
    return [{"sid": r.get(c_sid), "name": r.get(c_name), "segment": r.get(c_seg)}
            for r in with_rooms if c_sid and r.get(c_sid)]


# ------------------------------------------------ 5. sample accessibility data
def rooms_query(openings_selection):
    edge_extra = f" {openings_selection}" if openings_selection else ""
    return f"""query Rooms($id: ID!) {{ model(id: $id) {{
      id name
      floors {{ id label edges {{ id type thickness{edge_extra} }} }}
      rooms {{ id classifications {{ label confidence }}
              dimensions(units: metric) {{ areaFloor width depth height }} }}
    }} }}"""


def room_label(room):
    cls = room.get("classifications") or []
    return cls[0]["label"] if cls else "(unlabelled)"


def narrow_side(dims):
    vals = [v for v in (dims.get("width"), dims.get("depth")) if v]
    return min(vals) if vals else None


def check_sample(report, candidates, n, openings_selection, seed):
    section(f"5. Accessibility signals on {n} sampled models")
    if not candidates:
        print("No candidates (need models_index.csv with room counts).")
        return
    random.Random(seed).shuffle(candidates)
    by_seg = {}
    for c in candidates:
        by_seg.setdefault(c.get("segment") or "?", []).append(c)
    sample, i = [], 0
    while len(sample) < n and any(by_seg.values()):  # round robin across segments
        seg = list(by_seg)[i % len(by_seg)]
        if by_seg[seg]:
            sample.append(by_seg[seg].pop())
        i += 1

    edge_types, label_counts = Counter(), Counter()
    hall_widths_in, bath_results, opening_examples, per_model = [], [], [], []
    query = rooms_query(openings_selection)

    for idx, c in enumerate(sample, 1):
        data, errors = graph(query, {"id": c["sid"]})
        model = (data or {}).get("model")
        if not model:
            print(f"  [{idx}/{len(sample)}] {c['sid']}: no data {errors or ''}")
            continue
        summary = {"sid": c["sid"], "name": model.get("name"), "segment": c.get("segment"),
                   "halls_in": [], "baths": []}
        for floor in model.get("floors") or []:
            for e in floor.get("edges") or []:
                edge_types[e.get("type")] += 1
                if e.get("openings"):
                    opening_examples.append({"sid": c["sid"], "edge": e["id"], "openings": e["openings"]})
        for room in model.get("rooms") or []:
            label = room_label(room)
            label_counts[label] += 1
            dims = room.get("dimensions") or {}
            side = narrow_side(dims)
            if side is None:
                continue
            if label.lower() == "hallway":
                w = round(side * M_TO_IN, 1)
                hall_widths_in.append(w)
                summary["halls_in"].append(w)
            elif label.lower() == "bathroom":
                fits = side >= TURN_DIAM_M
                bath_results.append(fits)
                summary["baths"].append({"narrow_m": round(side, 2), "fits_60in_circle": fits})
        per_model.append(summary)
        print(f"  [{idx}/{len(sample)}] {c['sid']} {str(model.get('name'))[:32]:<32} "
              f"halls(in)={summary['halls_in']} baths={[b['narrow_m'] for b in summary['baths']]}")

    print("\nEdge types seen:", dict(edge_types))
    print("Room labels seen (top 15):", dict(label_counts.most_common(15)))
    if hall_widths_in:
        ok = sum(w >= HALL_MIN_IN for w in hall_widths_in)
        print(f"Hallways measured: {len(hall_widths_in)}; >= {HALL_MIN_IN:.0f} in: {ok} "
              f"({100 * ok / len(hall_widths_in):.0f}%)  min {min(hall_widths_in)} in, max {max(hall_widths_in)} in")
    else:
        print("No hallway dimensions found in the sample.")
    if bath_results:
        print(f"Bathrooms measured: {len(bath_results)}; narrow side >= 60 in: {sum(bath_results)}")
    print(f"Edges with opening data: {len(opening_examples)}")
    for ex in opening_examples[:3]:
        print("  example:", json.dumps(ex)[:300])

    report["sample"] = {
        "edge_types": dict(edge_types), "room_labels": dict(label_counts),
        "hallway_widths_in": hall_widths_in, "bathrooms_fit_turning_circle": bath_results,
        "opening_examples": opening_examples[:20], "models": per_model,
    }


# ----------------------------------------------------------------- verdict
def verdict(report):
    section("Verdict")
    o = report.get("openings") or {}
    s = report.get("sample") or {}
    door_data = bool(s.get("opening_examples")) or bool(o.get("opening_fields"))
    non_wall = [t for t in (s.get("edge_types") or {}) if t and t != "wall"]
    print(f"Door openings in API:   {'YES' if door_data else 'NO'}"
          f"{'  (non wall edge types: ' + ', '.join(non_wall) + ')' if non_wall else ''}")
    print(f"Hallway widths:         {'YES' if s.get('hallway_widths_in') else 'NOT IN SAMPLE'}")
    print(f"Bathroom dimensions:    {'YES' if s.get('bathrooms_fit_turning_circle') else 'NOT IN SAMPLE'}")
    v = report.get("venue") or {}
    print(f"Venue scan reachable:   {'YES' if v.get('reachable') else 'NO (ask #costar-group / use --ref-dir)'}")
    if not door_data:
        print("-> Plan door widths from panoramas (vision) or the point cloud, or report them as unknown.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", default="data/models_index.csv", help="path to models_index.csv")
    ap.add_argument("--sample", type=int, default=25, help="models to sample for step 5")
    ap.add_argument("--venue", default="P3S6VUTP3qB", help="Matterport id of the venue scan")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="out/phase0_report.json")
    args = ap.parse_args()

    report = {}
    check_key(report)
    openings_selection = check_openings(report)
    check_venue(report, args.venue)
    candidates = check_index(report, args.index)
    check_sample(report, candidates, args.sample, openings_selection, args.seed)
    verdict(report)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report: {args.out}")


if __name__ == "__main__":
    main()
