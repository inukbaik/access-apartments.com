"""Building info tests with made-up data (no network, no kit files).
Run from the repo root: .venv/bin/python finder/test_building_info.py"""
import copy
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from finder import building_info as B, vexcel as V  # noqa: E402
from finder.screen import passes_all, sort_key  # noqa: E402


def fact(src="commercial", stories=None, floor=None, passenger=None, flag=False):
    return {"source": src, "stories_total": stories, "floor_number": floor,
            "elevator": {"passenger": passenger, "flag_true": flag}}


def vx(h, date="2026-07-01"):
    return {"status": "ok", "height_m": h, "photo_date": date, "collection": None, "reason": ""}


NOVX = {"status": "unavailable", "reason": "x"}

# --- elevator rules
E = lambda facts, mention=None: B.combine_elevator(facts, mention)["status"]  # noqa: E731
assert E([fact("residential", flag=False)]) == "unavailable"       # false is not evidence
assert E([fact(passenger=None)]) == "unavailable"                  # freight-only / unknown are dropped at build
assert E([]) == "unavailable"
assert E([fact(passenger="no")]) == "none_recorded"
assert "CoStar" in B.combine_elevator([fact(passenger="no")])["text"]
assert E([fact(passenger="yes")]) == "confirmed"
assert E([fact("residential", flag=True)]) == "confirmed"
assert E([fact(passenger="yes"), fact(passenger="no")]) == "disagree"
m = {"phrase": "elevator", "source": "remarks"}
assert E([], m) == "mentioned"
assert E([fact(passenger="no")], m) == "disagree"
assert E([fact(passenger="yes")], m) == "confirmed"

# --- height -> range
assert B.stories_range(14.3) == (3, 6)
assert B.stories_range(3.0) == (1, 2)
assert B.stories_range(20.5) == (5, 8)

# --- stories cross-reference
S = lambda facts, v: B.combine_stories(facts, v)  # noqa: E731
r = S([fact(stories=4)], vx(14.3))
assert r["status"] == "agree" and "4 stories (CoStar), consistent with Vexcel roof height 14.3 m" in r["text"]
r = S([fact(stories=56)], vx(20.5))
assert r["status"] == "disagree" and "CoStar 56 stories" in r["text"] and "5–8" in r["text"]
r = S([fact(stories=3), fact("residential", stories=5)], vx(14.3))
assert r["status"] == "disagree" and r["costar"] == [3, 5]
assert S([fact(stories=3), fact(stories=5)], NOVX)["status"] == "disagree"
r = S([fact(stories=4)], NOVX)
assert r["status"] == "costar_only" and "Vexcel height unavailable" in r["text"]
r = S([], vx(14.3))
assert r["status"] == "vexcel_only" and "no CoStar record" in r["text"] and "3–6" in r["text"]
r = S([], NOVX)
assert r["status"] == "unavailable" and r["text"] == "Stories: information unavailable"

# --- elevator-need message
c = B.combine([fact(stories=4, floor="3")], vx(14.3))
assert "need an elevator" in c["elevator_need"] and "floor 3" in c["elevator_need"]
c = B.combine([fact(stories=1)], vx(3.0))
assert c["elevator_need"] == "" or "May have" in c["elevator_need"]   # hi=2 from 3.0 m is "may"
c = B.combine([fact(stories=1)], NOVX)
assert c["elevator_need"] == ""
c = B.combine([], vx(3.0))
assert c["elevator_need"].startswith("May have upper floors")
c = B.combine([], NOVX)
assert c["message"].startswith("Stories: information unavailable")

# --- point in polygon
SQ = "POLYGON((0 0, 0.001 0, 0.001 0.001, 0 0.001, 0 0))"
assert V.contains(SQ, 0.0005, 0.0005) and not V.contains(SQ, 0.0005, 0.002)
HOLE = "POLYGON((0 0, 0.01 0, 0.01 0.01, 0 0.01, 0 0), (0.004 0.004, 0.006 0.004, 0.006 0.006, 0.004 0.006, 0.004 0.004))"
assert V.contains(HOLE, 0.001, 0.001) and not V.contains(HOLE, 0.005, 0.005)
MP = "MULTIPOLYGON(((0 0, 0.001 0, 0.001 0.001, 0 0.001, 0 0)), ((0.01 0.01, 0.011 0.01, 0.011 0.011, 0.01 0.011, 0.01 0.01)))"
assert V.contains(MP, 0.0105, 0.0105) and V.contains(MP, 0.0005, 0.0005) and not V.contains(MP, 0.005, 0.005)


def feature(ortho, date, structs):
    """Flat dotted keys, as the real API returns them."""
    return {"properties": {"metadata.is-ortho-image": ortho, "metadata.ortho-date-estimate": date,
                           "structures": [{"footprint.wkt": w, "roof-characteristics.height": h}
                                          for w, h in structs]}}


# --- select_height
resp = {"features": [feature(True, "2024-01-01", [(SQ, 5.0)]), feature(True, "2026-07-01", [(SQ, 14.3)]),
                     feature(False, "2027-01-01", [(SQ, 99.0)])]}
r = V.select_height(resp, 0.0005, 0.0005)
assert r["status"] == "ok" and r["height_m"] == 14.3 and r["photo_date"] == "2026-07-01"
r = V.select_height(resp, 0.5, 0.5)      # point outside every footprint: no fallback to nearest
assert r["status"] == "unavailable" and "footprint" in r["reason"]
assert V.select_height({"features": [feature(False, "2026-01-01", [(SQ, 9.0)])]}, 0.0005, 0.0005)["status"] == "unavailable"
for h in (None, 2.0, 301.0):
    assert V.select_height({"features": [feature(True, "2026-01-01", [(SQ, h)])]}, 0.0005, 0.0005)["status"] == "unavailable"
assert V.select_height({}, 0, 0)["status"] == "unavailable"

nested = {"features": [{"properties": {"metadata": {"is-ortho-image": True, "ortho-date-estimate": "2026-01-01"},
                                         "structures": [{"footprint": {"wkt": SQ}, "roof-characteristics": {"height": 9.0}}]}}]}
assert V.select_height(nested, 0.0005, 0.0005)["height_m"] == 9.0

# --- stopper: one network failure, then no second call
import requests  # noqa: E402
import tempfile  # noqa: E402

calls: list[Any] = []


def boom(*a, **k):
    calls.append(1)
    raise requests.ConnectionError("down")


orig_get, orig_key, orig_dir = requests.get, V._key, V.CACHE_DIR
requests.get, V._key, V.CACHE_DIR = boom, (lambda: "fake"), tempfile.mkdtemp()
V._state["down"] = False
try:
    a = V.building_height(1.0, 2.0)
    b = V.building_height(3.0, 4.0)
    assert a["status"] == b["status"] == "unavailable" and a["reason"] == "Vexcel unreachable"
    assert len(calls) == 1, calls
    V._state["down"] = False
    V._key = lambda: None
    assert "no VEXCEL_API_KEY" in V.building_height(5.0, 6.0)["reason"]
finally:
    requests.get, V._key, V.CACHE_DIR = orig_get, orig_key, orig_dir
    V._state["down"] = False


# --- ranking invariance
def chk(status):
    return {"check": "x", "status": status, "reason": "measured", "value": 40, "threshold": 36}


def bld(sid, status, km, units=1):
    us = [{"candidate": {"sid": f"{sid}{i}", "name": sid, "dist_km": km, "lat": 1.0, "lon": 2.0},
           "checks": [chk(status)], "error": None} for i in range(units)]
    return {**us[0], "units": us}


ranked = [bld("A", "pass", 0.1), bld("B", "fail", 0.2, 2), bld("C", "pass", 0.3)]
before = copy.deepcopy(ranked)
facts = {"A0": [fact(stories=4)], "B1": [fact(passenger="no")]}


def stub(lat, lon):
    return vx(14.3)


def bad(lat, lon):
    raise RuntimeError("boom")


B.annotate(ranked, facts, None, stub)
assert [r["candidate"]["sid"] for r in ranked] == [r["candidate"]["sid"] for r in before]
assert [passes_all(r) for r in ranked] == [passes_all(r) for r in before]
assert [sort_key(r) for r in ranked] == [sort_key(r) for r in before]
for r, o in zip(ranked, before):
    assert r["checks"] == o["checks"] and [u["checks"] for u in r["units"]] == [u["checks"] for u in o["units"]]
    assert "building_info" in r and "building_info" not in r["units"][0]["checks"]
assert ranked[0]["building_info"]["stories"]["status"] == "agree"
assert ranked[1]["building_info"]["elevator"]["status"] == "none_recorded"   # found via unit B1
assert ranked[2]["building_info"]["stories"]["status"] == "vexcel_only"
B.annotate(ranked, facts, None, bad)    # a failing source never raises
assert ranked[0]["building_info"]["stories"]["status"] == "costar_only"

# --- review fixes: apartment elevator list location, conflicting records, "may" when sources disagree
from finder.costar_facts import _commercial_fact  # noqa: E402
apt = {"numStoriesAboveGrade": 3, "propertyApartment": {"elevators": [{"elevatorType": 1, "elevatorState": 1}]}}
assert _commercial_fact(apt)["elevator"]["passenger"] == "yes"            # propertyApartment.elevators is read
apt_other = {"propertyApartment": {"elevators": [{"elevatorType": 2, "elevatorState": 2}, {"elevatorType": 4, "elevatorState": 2}]}}
assert _commercial_fact(apt_other)["elevator"]["passenger"] is None        # freight/parking "no" says nothing about passenger
both = {"propertyApartment": {"elevators": [{"elevatorType": 1, "elevatorState": 1}],
                              "structural": {"elevators": [{"elevatorType": 1, "elevatorState": 2}]}}}
f = _commercial_fact(both)
assert f["elevator"]["passenger"] == "conflict"
assert B.combine([f], None)["elevator"]["status"] == "disagree"
one_story = {"source": "commercial", "stories_total": 1, "floor_number": None, "elevator": {"passenger": None, "flag_true": False}}
c = B.combine([one_story], {"status": "ok", "height_m": 11.4, "photo_date": "2026-07-03"})
assert c["stories"]["status"] == "disagree" and c["elevator_need"].startswith("May have"), c["elevator_need"]
two = dict(one_story, stories_total=2)
c = B.combine([two], {"status": "ok", "height_m": 7.4, "photo_date": "2025-12-01"})   # Vexcel 1-3, agrees
assert c["stories"]["status"] == "agree" and c["elevator_need"].startswith("Units above"), c["elevator_need"]
print("ok")
