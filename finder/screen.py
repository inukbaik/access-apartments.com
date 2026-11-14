"""Screen listings near a point for accessibility. Run from the repo root:
  .venv/bin/python -m finder.screen --lat 34.0636 --lon -118.2999
"""
import argparse
import json
import os

from finder.buildings import group_buildings
from finder.candidates import load_candidates
from finder.checks import run_checks
from finder.matterport import FetchError, fetch_model


def cell(chk):
    if chk["reason"] == "no data":
        return "fail (no data)"
    if chk["reason"] == "bad measurement":
        return f"fail (bad {chk['value']}in)"
    return f"{chk['status']} {chk['value']}in"


def sort_key(r):
    if r.get("error"):
        return (1, 0, 0, r["candidate"]["dist_km"])
    ch = r["checks"]
    fails = sum(c["status"] == "fail" for c in ch)
    nodata = sum(c["reason"] == "no data" for c in ch)
    return (0, fails, nodata, r["candidate"]["dist_km"])


def passes_all(r):
    return not r.get("error") and all(c["status"] == "pass" for c in r["checks"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--radius-km", type=float, default=2)
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--index", default="data/models_index.csv")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and re-fetch")
    ap.add_argument("--out-dir", default="out/finder")
    args = ap.parse_args()

    pool = min(args.limit * 4, 60)
    cands = load_candidates(args.index, args.lat, args.lon, args.radius_km, pool)
    print(f"{len(cands)} candidates within {args.radius_km} km (pool {pool})")
    os.makedirs(args.out_dir, exist_ok=True)

    results = []
    for i, c in enumerate(cands, 1):
        print(f"[{i}/{len(cands)}] fetching {c['sid']} {str(c['name'])[:40]}")
        rec = {"candidate": c, "checks": [], "error": None}
        try:
            rec["checks"] = run_checks(fetch_model(c["sid"], args.refresh))
        except FetchError as e:
            rec["error"] = str(e)
            print(f"  ERROR: {e}")
        with open(os.path.join(args.out_dir, f"{c['sid']}.json"), "w") as f:
            json.dump(rec, f, indent=2)
        results.append(rec)

    results.sort(key=sort_key)

    # One listing per building: best-ranked unit first, the rest kept as units.
    by_id = {id(r["candidate"]): r for r in results}
    groups = group_buildings([r["candidate"] for r in results])
    ranked = []
    for g in groups:
        units = sorted((by_id[id(c)] for c in g), key=sort_key)
        ranked.append({**units[0], "units": units})
    ranked.sort(key=sort_key)
    ranked = ranked[:args.limit]
    with open(os.path.join(args.out_dir, "ranked.json"), "w") as f:
        json.dump(ranked, f, indent=2)

    print(f"\n{'#':>2}  {'name':<32} {'km':>5} {'units':>7}  {'hallway':<16} {'door':<18} {'turning':<16}")
    for n, r in enumerate(ranked, 1):
        c = r["candidate"]
        name = str(c["name"])[:32]
        extra = len(r["units"]) - 1
        u = f"+{extra}" if extra else ""
        if r["error"]:
            print(f"{n:>2}  {name:<32} {c['dist_km']:>5.2f} {u:>7}  ERROR: {r['error'][:60]}")
            continue
        h, d, t = (cell(x) for x in r["checks"])
        print(f"{n:>2}  {name:<32} {c['dist_km']:>5.2f} {u:>7}  {h:<16} {d:<18} {t:<16}")
    npass = sum(passes_all(r) for r in ranked)
    print(f"\n{npass} of {len(ranked)} buildings pass all checks")
    print(f"Wrote {len(results)} files + ranked.json to {args.out_dir}/")


if __name__ == "__main__":
    main()
