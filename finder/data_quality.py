"""Data-quality report for what is already on disk. Read-only, no network, totals only.

    .venv/bin/python -m finder.data_quality              # counts only
    .venv/bin/python -m finder.data_quality --show-ids   # also list Matterport model ids that fail the schema

Covers: screening cache, evidence cache, Vexcel cache, data/models_index.csv, CoStar facts cache.
It never prints names, addresses or sponsor records. Exit code is 0 whenever the report completes.
"""
import argparse
import csv
import glob
import json
import os
from collections import Counter
from typing import Any

from pydantic import BaseModel

from finder import evidence, matterport
from finder.checks import DOOR_PLAUSIBLE_MIN_IN, M_TO_IN
from finder.costar_facts import CACHE as COSTAR_CACHE
from finder.schemas import DataError, EvidenceModel, HeightResult, ScreenModel, validate

INDEX = "data/models_index.csv"
VEXCEL_DIR = "cache/finder/vexcel"
FACT_KEYS = {"source", "stories_total", "floor_number", "elevator"}


def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _field_path(msg: str) -> str:
    """'<what>: a.b.c: reason; ...' -> the first field path with list indexes replaced by '*'."""
    parts = msg.split(": ")
    path = parts[1] if len(parts) > 1 else "?"
    return ".".join("*" if p.isdigit() else p for p in path.split("."))


def scan_json(files: list[str], schema: type[BaseModel]) -> tuple[list[Any], Counter[str], list[str]]:
    """Returns (valid parsed objects, failure counts by field path, ids of failing files)."""
    good: list[Any] = []
    paths: Counter[str] = Counter()
    bad: list[str] = []
    for p in files:
        sid = os.path.basename(p)[:-5]
        try:
            data = _load(p)
            validate(schema, data, sid)
        except DataError as e:
            paths[_field_path(str(e))] += 1
            bad.append(sid)
        except (OSError, ValueError) as e:
            paths[f"(unreadable file: {type(e).__name__})"] += 1
            bad.append(sid)
        else:
            good.append(data)
    return good, paths, bad


def _print_failures(paths: Counter[str], bad: list[str], show_ids: bool) -> None:
    for path, n in paths.most_common(5):
        print(f"    {n:5d}  {path}")
    if show_ids and bad:
        print("    failing ids: " + ", ".join(sorted(bad)))


def _w(room: dict[str, Any], key: str) -> Any:
    return (room.get("dimensions") or {}).get(key)


def report_screening(show_ids: bool) -> None:
    files = sorted(p for p in glob.glob(os.path.join(matterport.CACHE_DIR, "*.json"))
                   if os.path.basename(p) != os.path.basename(COSTAR_CACHE))  # the facts file is not a model
    print(f"Screening cache ({matterport.CACHE_DIR}/*.json): {len(files)} files")
    if not files:
        return
    good, paths, bad = scan_json(files, ScreenModel)
    print(f"  valid {len(good)}, invalid {len(bad)}")
    _print_failures(paths, bad, show_ids)
    no_rooms = sum(not m.get("rooms") for m in good)
    rooms = [r for m in good for r in m.get("rooms") or []]
    no_class = sum(not r.get("classifications") for r in rooms)
    no_size = sum(_w(r, "width") is None or _w(r, "depth") is None for r in rooms)
    openings = [o for m in good for fl in m.get("floors") or [] for e in fl.get("edges") or []
                for o in e.get("openings") or []]
    doors = [o for o in openings if o.get("type") == "doorway"]
    no_w = sum(o.get("width") is None for o in doors)
    narrow = sum(o.get("width") is not None and o["width"] * M_TO_IN < DOOR_PLAUSIBLE_MIN_IN for o in doors)
    print("  coverage (valid files only):")
    print(f"    models with zero rooms: {no_rooms}")
    print(f"    rooms: {len(rooms)}; without a classification: {no_class}; missing width or depth: {no_size}")
    print(f"    doorway openings: {len(doors)}; missing width: {no_w}; "
          f"under {DOOR_PLAUSIBLE_MIN_IN:g} in ({DOOR_PLAUSIBLE_MIN_IN / M_TO_IN:.3f} m): {narrow}")


def report_evidence(show_ids: bool) -> None:
    files = sorted(glob.glob(os.path.join(evidence.CACHE, "*.json")))
    if not files:
        print(f"Evidence cache ({evidence.CACHE}): none")
        return
    good, paths, bad = scan_json(files, EvidenceModel)
    print(f"Evidence cache ({evidence.CACHE}/*.json): {len(files)} files, valid {len(good)}, invalid {len(bad)}")
    _print_failures(paths, bad, show_ids)


def report_vexcel(show_ids: bool) -> None:
    files = sorted(glob.glob(os.path.join(VEXCEL_DIR, "*.json")))
    print(f"Vexcel cache ({VEXCEL_DIR}/*.json): {len(files)} files")
    if not files:
        return
    good, paths, bad = scan_json(files, HeightResult)
    print(f"  valid {len(good)}, invalid {len(bad)}")
    _print_failures(paths, bad, False)
    print("  by status: " + ", ".join(f"{k} {n}" for k, n in sorted(Counter(g["status"] for g in good).items())))
    reasons = Counter(g["reason"] or "(none)" for g in good)
    for reason, n in reasons.most_common():
        print(f"    {n:5d}  {reason}")


def _num(v: str | None) -> float | None:
    try:
        x = float(v) if v not in (None, "") else None
    except ValueError:
        return None
    return x if x is not None and x == x and abs(x) != float("inf") else None


def report_index() -> None:
    if not os.path.exists(INDEX):
        print(f"Index ({INDEX}): not present")
        return
    rows = missing_ll = out_of_range = missing_sid = dup = 0
    seen: set[str] = set()
    with open(INDEX, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows += 1
            lat, lon = _num(row.get("lat")), _num(row.get("lon"))
            if lat is None or lon is None:
                missing_ll += 1
            elif not (-90 <= lat <= 90 and -180 <= lon <= 180):
                out_of_range += 1
            sid = (row.get("sid") or "").strip()
            if not sid:
                missing_sid += 1
            elif sid in seen:
                dup += 1
            seen.add(sid)
    print(f"Index ({INDEX}): {rows} rows")
    print(f"  missing or non-numeric lat/lon: {missing_ll}; lat/lon out of range: {out_of_range}; "
          f"missing sid: {missing_sid}; duplicate sid: {dup}")


def _fact_ok(f: Any) -> bool:
    """Same types as the fact record documented in finder/costar_facts.py."""
    if not isinstance(f, dict) or set(f) != FACT_KEYS or f["source"] not in ("commercial", "residential"):
        return False
    st, fl, el = f["stories_total"], f["floor_number"], f["elevator"]
    return (
        (st is None or (isinstance(st, int) and not isinstance(st, bool)))
        and (fl is None or isinstance(fl, str))
        and isinstance(el, dict)
        and el.get("passenger") in ("yes", "no", "conflict", None)
        and isinstance(el.get("flag_true"), bool)
    )


def report_costar() -> None:
    if not os.path.exists(COSTAR_CACHE):
        print(f"CoStar facts ({COSTAR_CACHE}): not present")
        return
    try:
        facts = _load(COSTAR_CACHE)
    except (OSError, ValueError) as e:
        print(f"CoStar facts ({COSTAR_CACHE}): unreadable ({type(e).__name__})")
        return
    if not isinstance(facts, dict) or not all(isinstance(v, list) for v in facts.values()):
        print(f"CoStar facts ({COSTAR_CACHE}): unexpected top-level shape (expected {{model id: [fact, ...]}})")
        return
    allf = [f for fs in facts.values() for f in fs]
    src = Counter(f.get("source", "?") if isinstance(f, dict) else "(not an object)" for f in allf)
    bad = sum(not _fact_ok(f) for f in allf)
    print(f"CoStar facts ({COSTAR_CACHE}): {len(facts)} models, {len(allf)} records")
    print("  by source: " + ", ".join(f"{k} {n}" for k, n in sorted(src.items())))
    print(f"  records whose types do not match the documented fact record: {bad}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show-ids", action="store_true", help="list Matterport model ids that fail the schema")
    a = ap.parse_args()
    report_screening(a.show_ids)
    report_evidence(a.show_ids)
    report_vexcel(a.show_ids)
    report_index()
    report_costar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
