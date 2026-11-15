"""Small CoStar facts per Matterport model id, for the informational "building info" (stories, elevator).
Built once from the sponsor kit (data/costar/, never committed), cached in cache/finder/costar_facts.json
(git-ignored). Ids and values only, no text.

Fact record: {source: "commercial"|"residential", stories_total: int|None, floor_number: str|None,
              elevator: {passenger: "yes"|"no"|"conflict"|None, flag_true: bool}}
- Commercial: numStoriesAboveGrade; passenger elevator (type 1) state 1 = "yes", 2 = "no", both =
  "conflict". Read from `<block>.structural.elevators` and from `propertyApartment.elevators`
  (apartments keep the list directly on the block). Other types (freight, escalator, parking) are ignored.
- Residential: resoValues.structure.storiesTotal (the building, not the unit's own `stories`);
  property.address.floorNumber; resoValues.hasElevator true = flag_true. False is NOT evidence of absence.

Rebuild:  .venv/bin/python -m finder.costar_facts --rebuild
"""
import argparse
import json
import os
import sys
import time
from typing import Any

from finder.costar_text import KIT, _jsonl, _model_map

CACHE = "cache/finder/costar_facts.json"
_memo: dict[str, Any] = {}


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None


def _elevator_lists(p):
    """Every elevators[] list in a commercial record: `<block>.structural.elevators` (office, retail,
    industrial, flex) and `<block>.elevators` directly on the block (propertyApartment)."""
    for block in p.values():
        if isinstance(block, dict):
            yield block.get("elevators") or []
            if isinstance(block.get("structural"), dict):
                yield block["structural"].get("elevators") or []


def _commercial_fact(p):
    states = set()
    for lst in _elevator_lists(p):
        for e in lst:
            if isinstance(e, dict) and e.get("elevatorType") == 1 and e.get("elevatorState") in (1, 2):
                states.add(e["elevatorState"])
    # Conflicting passenger records stay a conflict ("sources disagree"), never resolved silently.
    passenger = "conflict" if states == {1, 2} else "yes" if 1 in states else "no" if 2 in states else None
    return {"source": "commercial", "stories_total": _int(p.get("numStoriesAboveGrade")),
            "floor_number": None, "elevator": {"passenger": passenger, "flag_true": False}}


def _residential_fact(l):
    reso = l.get("resoValues") or {}
    fl = ((l.get("property") or {}).get("address") or {}).get("floorNumber")
    return {"source": "residential",
            "stories_total": _int((reso.get("structure") or {}).get("storiesTotal")),
            "floor_number": str(fl).strip() if fl not in (None, "") else None,
            "elevator": {"passenger": None, "flag_true": reso.get("hasElevator") is True}}


def build_facts(kit=KIT, log=print):
    models: dict[str, list[Any]] = {}
    rmap = _model_map(f"{kit}/residential-listings.csv", "ListingId")
    for l in _jsonl(f"{kit}/data/residential-listings.jsonl"):
        for mid in rmap.get(str(l["id"]), []):
            models.setdefault(mid, []).append(_residential_fact(l))
    cmap = _model_map(f"{kit}/commercial-properties.csv", "PropertyId")
    for p in _jsonl(f"{kit}/data/commercial-property.jsonl"):  # ~190 MB, streamed
        for mid in cmap.get(str(p["id"]), []):
            models.setdefault(mid, []).append(_commercial_fact(p))
    return models


def load_facts(rebuild=False, path=CACHE, kit=KIT, log=print):
    """{model id: [fact, ...]}; built and cached on first use (or when rebuild=True)."""
    if not rebuild and path in _memo:
        return _memo[path]
    if rebuild or not os.path.exists(path):
        if not os.path.isdir(kit):
            raise RuntimeError(f"CoStar kit not found at {kit}/ (see data/README.md); cannot build the facts")
        log("Building CoStar facts (one time) ...")
        t0 = time.monotonic()
        facts = build_facts(kit, log)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(facts, f)
        log(f"  built in {time.monotonic() - t0:.1f}s at {path}")
    else:
        with open(path, encoding="utf-8") as f:
            facts = json.load(f)
    _memo[path] = facts
    return facts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    facts = load_facts(rebuild=args.rebuild)
    allf = [f for fs in facts.values() for f in fs]
    print(f"{len(facts)} Matterport models with CoStar facts ({len(allf)} fact records)")
    for src in ("commercial", "residential"):
        fs = [f for f in allf if f["source"] == src]
        print(f"  {src}: {len(fs)} records, stories {sum(f['stories_total'] is not None for f in fs)}, "
              f"floor number {sum(f['floor_number'] is not None for f in fs)}, "
              f"passenger yes {sum(f['elevator']['passenger'] == 'yes' for f in fs)}, "
              f"passenger no {sum(f['elevator']['passenger'] == 'no' for f in fs)}, "
              f"hasElevator true {sum(f['elevator']['flag_true'] for f in fs)}")


if __name__ == "__main__":
    sys.exit(main())
