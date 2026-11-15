"""Run: .venv/bin/python finder/test_checks.py  (made-up data only)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from finder.checks import check_door, check_hallway, check_turning, run_checks  # noqa: E402


def room(rid, label, w, d):
    return {"id": rid, "classifications": [{"label": label, "confidence": 0.9}],
            "dimensions": {"width": w, "depth": d}}


def floor(*widths):
    return [{"edges": [{"id": f"e{i}", "openings": [{"type": "doorway", "width": w}]}
                       for i, w in enumerate(widths)]}]


# hallway: 0.8 m = 31.5 in, 1.2 m = 47.2 in
r = check_hallway([room("a", "Hallway", 5.0, 1.2), room("b", "hallway", 0.8, 4.0)])
assert r["status"] == "fail" and r["value"] == 31.5 and r["evidence"] == ["b"], r
r = check_hallway([room("a", "Hallway", 5.0, 1.2)])
assert r["status"] == "pass" and r["value"] == 47.2 and r["evidence"] == ["a"], r
assert check_hallway([room("a", "Kitchen", 1, 1), room("b", "Hallway", None, None)])["status"] == "fail"
assert check_hallway([])["reason"] == "no data" and check_hallway([])["value"] is None

# door: 0.7 m = 27.6 in, 0.9 m = 35.4 in
r = check_door(floor(0.9, 0.7))
assert r["status"] == "fail" and r["value"] == 27.6 and r["evidence"] == ["e1"], r
r = check_door(floor(0.9))
assert r["status"] == "pass" and r["value"] == 35.4, r
f = [{"edges": [{"id": "w", "openings": [{"type": "window", "width": 0.3}]}, {"id": "x", "openings": []}]}]
r = check_door(f)
assert r["status"] == "fail" and r["reason"] == "no data" and r["value"] is None, r
assert check_door([])["reason"] == "no data"
# 0.05 m = 2.0 in is implausible: bad measurement; a real narrow door wins over it
r = check_door(floor(0.9, 0.05))
assert r["status"] == "fail" and r["reason"] == "bad measurement" and r["value"] == 2.0 and r["evidence"] == ["e1"], r
r = check_door(floor(0.7, 0.05))
assert r["status"] == "fail" and r["reason"] == "measured" and r["value"] == 27.6 and r["evidence"] == ["e0"], r
assert check_door(floor(0.9))["reason"] == "measured"

# turning: 1.6 m = 63.0 in, 1.2 m = 47.2 in
r = check_turning([room("a", "Bathroom", 1.2, 3), room("b", "Bathroom", 1.6, 2)])
assert r["status"] == "pass" and r["value"] == 63.0 and r["evidence"] == ["b"], r
r = check_turning([room("a", "Bathroom", 1.2, 3)])
assert r["status"] == "fail" and r["value"] == 47.2 and r["evidence"] == ["a"], r
r = check_turning([room("a", "Bedroom", 4, 4)])
assert r["status"] == "fail" and r["reason"] == "no data" and r["value"] is None, r

assert [c["check"] for c in run_checks({"rooms": [], "floors": []})] == ["hallway", "door", "turning"]
print("ok")
