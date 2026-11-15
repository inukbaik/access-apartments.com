"""Survey behind the README figures: 800 random home listings (seed 0) with coordinates and rooms.

    .venv/bin/python -m finder.survey out/survey.json     # about 800 Matterport calls on a cold cache

Prints how many pass each check, and the door check with and without the closet rule."""
import csv, json, random, sys, collections
from concurrent.futures import ThreadPoolExecutor
from finder.candidates import NOT_A_HOME, _float
from finder.checks import run_checks, check_door
from finder.matterport import fetch_model
rows = [r for r in csv.DictReader(open("data/models_index.csv", encoding="utf-8"))
        if _float(r.get("lat")) is not None and _float(r.get("room_count")) not in (0, None) and not NOT_A_HOME.match((r.get("name") or "").strip())]
print("eligible", len(rows), collections.Counter(r.get("city") for r in rows).most_common(6), flush=True)
random.seed(0); sample = random.sample(rows, 800)
def one(r):
    for attempt in range(3):
        try:
            m = fetch_model(r["sid"]); break
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:120]
    else:
        return {"sid": r["sid"], "error": err}
    new = run_checks(m); old = check_door(m.get("floors"))
    return {"sid": r["sid"], "city": r.get("city"), "new": [(c["status"], c["reason"]) for c in new], "old_door": (old["status"], old["reason"]),
            "skipped": "not counted" in new[1]["note"]}
with ThreadPoolExecutor(8) as ex:
    out = list(ex.map(one, sample))
json.dump(out, open(sys.argv[1], "w"))
ok = [o for o in out if "error" not in o]; n = len(ok)
print("loaded", n, "errors", len(out) - n, [o["error"] for o in out if "error" in o][:2])
def pct(k): return f"{k} ({100*k/n:.1f}%)"
print("door pass, old rule:", pct(sum(o["old_door"][0] == "pass" for o in ok)))
print("door pass, new rule:", pct(sum(o["new"][1][0] == "pass" for o in ok)))
print("door no data (new):", pct(sum(o["new"][1][1] == "no data" for o in ok)), " door measured fail:", pct(sum(o["new"][1] == ("fail","measured") for o in ok)), " bad meas:", pct(sum(o["new"][1][1]=="bad measurement" for o in ok)))
print("listings with a closet/pantry door skipped:", pct(sum(o["skipped"] for o in ok)))
print("hallway pass:", pct(sum(o["new"][0][0] == "pass" for o in ok)), " no data:", pct(sum(o["new"][0][1]=="no data" for o in ok)))
print("turning pass:", pct(sum(o["new"][2][0] == "pass" for o in ok)), " no data:", pct(sum(o["new"][2][1]=="no data" for o in ok)))
print("pass all three, new:", pct(sum(all(c[0] == "pass" for c in o["new"]) for o in ok)), " old:", pct(sum(o["new"][0][0]=="pass" and o["new"][2][0]=="pass" and o["old_door"][0]=="pass" for o in ok)))
