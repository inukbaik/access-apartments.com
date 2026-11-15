"""Extra-need tests with made-up buildings and made-up listing text (no LLM, no network, no real data).
Run from the repo root: .venv/bin/python finder/test_needs.py"""
import contextlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from finder import costar_text, needs as N  # noqa: E402
from finder.agent import answer, check_notes  # noqa: E402
from finder.tools import FOUND, UNAVAILABLE, ToolContext, call_tool, rank_with_extra  # noqa: E402

LAT, LON = 34.0242, -118.2991


def chk(name, status, reason, value, thr):
    return {"check": name, "status": status, "reason": reason, "value": value, "threshold": thr}


PASS = [chk("hallway", "pass", "measured", 40.0, 36), chk("door", "pass", "measured", 34.0, 32),
        chk("turning", "pass", "measured", 65.0, 60)]
FAIL1 = [chk("hallway", "pass", "measured", 40.0, 36), chk("door", "fail", "measured", 27.0, 32),
         chk("turning", "pass", "measured", 65.0, 60)]
FAIL2 = [chk("hallway", "pass", "measured", 40.0, 36), chk("door", "fail", "measured", 27.0, 32),
         chk("turning", "fail", "measured", 50.0, 60)]


def building(sid, name, checks, km, n_units=1):
    units = [{"candidate": {"sid": f"{sid}{i}", "name": f"{name} {i}", "dist_km": km}, "checks": checks,
              "error": None} for i in range(n_units)]
    return {**units[0], "units": units}


# Made-up text. Models s1.. link to records; s6 has no CoStar record at all.
INDEX = {
    "models": {"A0": ["r:1"], "B0": ["r:2"], "B1": ["r:3"], "C0": ["r:4"], "D0": ["r:5"], "E0": ["r:6"]},
    "records": {
        "r:1": {"fields": [["remarks", "Bright flat with a roll-in shower and wide halls."]]},
        "r:2": {"fields": [["remarks", "Big walk-in shower, tiled."], ["features: Bathroom", "Walk in shower"]]},
        "r:3": {"fields": [["highlights", "Grab Bar In Bathroom"]]},
        "r:4": {"fields": [["remarks", "Quiet street. Accessible wet room downstairs."]]},
        "r:5": {"fields": [["remarks", "There are no grab bars here."]]},
        "r:6": {"fields": [["listing flags", "has accessibility features"]]},
    },
}
RANKED = [building("A", "Alpha", PASS, 0.1), building("B", "Beta", PASS, 0.2, 2), building("C", "Gamma", PASS, 0.3),
          building("D", "Delta", PASS, 0.4), building("E", "Eps", PASS, 0.5), building("F", "Zeta", PASS, 0.6)]


def ctx_for(ranked=None, index=INDEX):
    ranked = ranked or RANKED
    c = ToolContext(screen=lambda *a: ranked, fixed=(LAT, LON, 1.5, 10), text_index=index)
    assert "error" not in call_tool(c, "search_area", {"lat": LAT, "lon": LON, "radius_km": 1, "limit": 5})
    return c


def search(c, need, terms, ids):
    return call_tool(c, "search_listing_text", {"need": need, "terms": terms, "building_ids": ids})


def status(c, need, bid):
    return c.extra.result(need, bid)["status"]


# 1. an accepted phrase is found, with phrase, source label and ~80 chars of context
c = ctx_for()
assert "error" not in call_tool(c, "set_extra_needs", {"needs": ["roll-in shower"], "reasons": ["power chair"]})
r = search(c, "roll-in shower", [], ["B1"])
ev = r["results"][0]
assert r["results"][0]["status"] == FOUND and ev["evidence"][0]["matched"] == "roll-in shower", r
assert ev["evidence"][0]["source"] == "remarks" and len(ev["evidence"][0]["context"]) <= 90
assert ev["evidence"][0]["label"] == "reviewed match"
# case, hyphen and space variants
assert N.find_matches("roll-in shower", N.reviewed_terms("roll-in shower"), [], [["x", "ROLL  IN   Shower!"]])
assert N.find_matches("roll-in shower", N.reviewed_terms("roll-in shower"), [], [["x", "a Zero-Threshold shower"]])
# whole phrase only
assert not N.find_matches("grab bars", N.reviewed_terms("grab bars"), [], [["x", "grab barstool"]])

# 2. "walk-in shower" is never a roll-in match: only that phrase in the text ...
r = search(c, "roll-in shower", [], ["B2"])
assert r["results"][0]["status"] == UNAVAILABLE and status(c, "roll-in shower", "B2") == UNAVAILABLE
# ... and when the agent passes it as a term (refused, with an explanation), or a part of it
c = ctx_for()
call_tool(c, "set_extra_needs", {"needs": ["roll-in shower"], "reasons": []})
r = search(c, "roll-in shower", ["walk-in shower", "step-in shower"], ["B2"])
assert r["results"][0]["status"] == UNAVAILABLE and len(r["refused_terms"]) == 2 and "look-alike" in r["refused_terms"][0]
r = search(c, "roll-in shower", ["shower"], ["B2"])  # "shower" sits inside the blocked phrase: dropped
assert r["results"][0]["status"] == UNAVAILABLE and "refused_terms" not in r
assert N.classify_terms("roll-in shower", ["Walk-In Shower"])[2]

# 3. a term outside the reviewed list is allowed and labelled
c = ctx_for()
call_tool(c, "set_extra_needs", {"needs": ["roll-in shower"], "reasons": []})
r = search(c, "roll-in shower", ["wet room"], ["B3"])
assert r["results"][0]["status"] == FOUND and r["results"][0]["evidence"][0]["label"] == "agent-suggested match", r
# an unknown need has no reviewed terms: everything is agent-suggested
call_tool(c, "set_extra_needs", {"needs": ["wet room"], "reasons": []})
r = search(c, "wet room", ["wet room"], ["B3"])
assert r["results"][0]["evidence"][0]["label"] == "agent-suggested match"
# a negated phrase does not count
c = ctx_for()
call_tool(c, "set_extra_needs", {"needs": ["grab bars"], "reasons": []})
assert search(c, "grab bars", [], ["B4"])["results"][0]["status"] == UNAVAILABLE

# 4. limits return {"stopped": ...} (not an error, not counted as an invalid call)
c = ctx_for()
r = call_tool(c, "set_extra_needs", {"needs": ["a", "b", "c", "d"], "reasons": []})
assert "stopped" in r and "error" not in r and not c.extra.needs
assert "error" not in call_tool(c, "set_extra_needs", {"needs": ["roll-in shower", "grab bars", "elevator"], "reasons": []})
assert "stopped" in call_tool(c, "set_extra_needs", {"needs": ["ramp"], "reasons": []})
c = ctx_for()
call_tool(c, "set_extra_needs", {"needs": ["roll-in shower"], "reasons": []})
assert "rounds_left" in search(c, "roll-in shower", [], ["B1"])
assert "rounds_left" in search(c, "roll-in shower", ["shower stall"], ["B1"])
r = search(c, "roll-in shower", ["x"], ["B1"])
assert "stopped" in r and "round" in r["stopped"] and "error" not in r and c.extra.rounds["roll-in shower"] == 2
c = ctx_for()
call_tool(c, "set_extra_needs", {"needs": ["roll-in shower"], "reasons": []})
r = search(c, "roll-in shower", list("abcdef"), ["B1"])
assert "stopped" in r and "term" in r["stopped"] and not c.extra.rounds
many = [building(f"S{n}", f"Name{n}", PASS, 0.1 * n) for n in range(1, 13)]
c = ctx_for(many)
call_tool(c, "set_extra_needs", {"needs": ["roll-in shower"], "reasons": []})
r = search(c, "roll-in shower", [], ["B1", "B11"])
assert "stopped" in r and "top-10" in r["stopped"] and "B11" in r["stopped"] and not c.extra.rounds
assert "stopped" not in search(c, "roll-in shower", [], ["B1", "B10"])
# malformed calls are errors
assert "error" in search(c, "elevator", [], ["B1"])           # need never set
assert "error" in search(c, "roll-in shower", [], ["B99"])    # unknown building
assert "error" in call_tool(c, "search_listing_text", {"need": "x"})

# 5. the boost never lifts a building with more failed core checks above one with fewer
mixed = [building("P", "Pass", PASS, 0.9), building("Q", "OneFail", FAIL1, 0.1), building("R", "TwoFail", FAIL2, 0.1),
         building("T", "PassToo", PASS, 0.5)]
idx = {"models": {"R0": ["r:1"], "Q0": ["r:1"], "P0": [], "T0": ["r:1"]},
       "records": {"r:1": {"fields": [["remarks", "roll-in shower and grab bars"]]}}}
c = ctx_for(mixed, idx)
call_tool(c, "set_extra_needs", {"needs": ["roll-in shower", "grab bars"], "reasons": []})
labels = lambda: rank_with_extra(c.ids, c.extra)[1]  # noqa: E731
base = labels()
search(c, "roll-in shower", [], ["B2", "B3", "B4"])
search(c, "grab bars", [], ["B2", "B3", "B4"])
after = labels()
fails = lambda b: sum(x["status"] == "fail" for x in c.ids[b]["checks"])  # noqa: E731
assert [fails(b) for b in after] == sorted(fails(b) for b in after), after
# within the zero-fail group the building with found extra needs (T = B4, farther than ... P no record) goes first
assert after[0] == "B4" and after.index("B4") < after.index("B1"), (base, after)
assert after.index("B2") < after.index("B3")  # one fail still above two fails
# within a group: more found first, then distance
assert c.extra.found_count("B4") == 2 and c.extra.found_count("B1") == 0

# 6. unsearched -> unavailable; no CoStar record -> unavailable with that reason
c = ctx_for()
call_tool(c, "set_extra_needs", {"needs": ["roll-in shower"], "reasons": []})
assert c.extra.result("roll-in shower", "B3") == {"status": UNAVAILABLE, "reason": "not searched", "evidence": []}
nr = building("Z", "NoRecord", PASS, 0.7)
c = ctx_for(RANKED[:1] + [nr])
call_tool(c, "set_extra_needs", {"needs": ["roll-in shower"], "reasons": []})
r = search(c, "roll-in shower", [], ["B1", "B2"])
assert r["results"][1]["status"] == UNAVAILABLE and r["results"][1]["reason"] == "no CoStar record"
# a building searches ALL its units' models: Beta's second unit (B1) has the grab bar
c = ctx_for()
call_tool(c, "set_extra_needs", {"needs": ["grab bars"], "reasons": []})
assert search(c, "grab bars", [], ["B2"])["results"][0]["status"] == FOUND

# 7. field names never match: the index keeps VALUES only
f = costar_text._residential_fields({"remarks": "Nice.", "resoValues": {"hasAccessibilityFeatures": False,
                                     "hasElevator": False}}, {"highlights": [{"text": "Pool"}], "sections": [], "features": []})
assert all("accessib" not in t.lower() and "elevator" not in t.lower() for _, t in f), f
f = costar_text._residential_fields({"remarks": "", "resoValues": {"hasAccessibilityFeatures": True, "hasElevator": True}}, None)
assert ["listing flags", "has accessibility features"] in f and ["listing flags", "has elevator"] in f, f
f = costar_text._commercial_fields({"notes": [{"value": "Corner office tower."}], "elevators": [{"x": 1}],
                                    "amenities": [7, 17], "attachments": [{"caption": "Lobby"}]})
assert f == [["notes", "Corner office tower."], ["photo caption", "Lobby"]], f
c = ctx_for()
call_tool(c, "set_extra_needs", {"needs": ["elevator", "wheelchair accessible"], "reasons": []})
assert search(c, "elevator", [], ["B1", "B2"])["results"][0]["status"] == UNAVAILABLE
assert search(c, "wheelchair accessible", [], ["B5"])["results"][0]["status"] == FOUND  # via the "has ..." flag text

# 8. detection from the request words (the no-model backup); look-alikes do not trigger
assert N.detect_needs("I use a power wheelchair and need a roll-in shower and grab bars") == ["roll-in shower", "grab bars"]
assert N.detect_needs("I want a walk-in shower") == []

# 9. whole runs through answer(): backup path, and a scripted model
def run(backend, request, ranked=None, **kw):
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(out):
        res = answer(request, LAT, LON, 1.5, 10, backend, out_dir=d, screen=lambda *a: ranked or RANKED,
                     text_index=INDEX, **kw)
        trace = json.load(open(os.path.join(d, "agent_trace.json")))
    return res, out.getvalue(), trace


res, out, trace = run(None, "power wheelchair, roll-in shower and grab bars")
assert "Extra needs: roll-in shower, grab bars — searched in listing text (not measured)" in out, out
assert "listing says ✓ (remarks)" in out and "unavailable" in out and "Evidence:" in out
assert '  1 roll-in shower: "roll-in shower" in remarks (reviewed match): Bright flat' in out, out
assert "No CoStar record:\n  6 roll-in shower: information unavailable (no CoStar record)" in out
assert trace["extra_needs"]["rounds"] == {"roll-in shower": 1, "grab bars": 1}
res, out, trace = run(None, "just a quiet flat")
assert "Extra needs" not in out and trace["extra_needs"]["needs"] == []


class Fake:
    model, base_url = "fake", "http://fake/v1"

    def __init__(self, script):
        self.script = list(script)

    def preflight(self, timeout=3):
        pass

    def chat(self, messages, tools, timeout=None):
        return self.script.pop(0) if self.script else ("", [])


def cl(name, args, i=0):
    return {"id": f"c{i}", "name": name, "arguments": json.dumps(args)}


S = ("", [cl("search_area", {"lat": LAT, "lon": LON, "radius_km": 1.5, "limit": 10})])
NEED = ("", [cl("set_extra_needs", {"needs": ["roll-in shower"], "reasons": ["power chair"]})])
fb = Fake([NEED, S,
           ("", [cl("search_listing_text", {"need": "roll-in shower", "terms": [], "building_ids": ["B1", "B2"]})]),
           ("", [cl("search_listing_text", {"need": "roll-in shower", "terms": ["curb-free"], "building_ids": ["B1", "B2"]})]),
           ("", [cl("search_listing_text", {"need": "roll-in shower", "terms": ["x"], "building_ids": ["B1"]})]),   # stopped
           ("", [cl("search_listing_text", {"need": "roll-in shower", "terms": ["y"], "building_ids": ["B3"]})]),   # stopped
           ("", [cl("finish", {"building_ids": ["B1"], "notes": "B1 has a roll-in shower per the listing text."})])])
res, out, trace = run(fb, "I need a roll-in shower")
assert res.finished, out  # two stopped results in a row did not trigger the invalid-call fallback
assert "Agent notes (not a verdict)" in out and "listing says" in out
assert trace["extra_needs"]["rounds"] == {"roll-in shower": 2}
# notes that claim a need for a building without evidence are withheld
fb = Fake([NEED, S, ("", [cl("search_listing_text", {"need": "roll-in shower", "terms": [], "building_ids": ["B1", "B2"]})]),
           ("", [cl("finish", {"building_ids": ["B2"], "notes": "B2 has a roll-in shower."})])])
res, out, trace = run(fb, "I need a roll-in shower")
assert res.finished and "Agent notes withheld" in out and trace["notes_withheld"], out
ids = {f"B{n}": r for n, r in enumerate(RANKED, 1)}
c = ctx_for()
call_tool(c, "set_extra_needs", {"needs": ["roll-in shower"], "reasons": []})
search(c, "roll-in shower", [], ["B1", "B2"])
assert check_notes("B1 has a roll-in shower.", ids, ["B1"], extra=c.extra)[0] is True
assert check_notes("B2 has a roll-in shower.", ids, ["B2"], extra=c.extra)[0] is False
assert check_notes("Roll-in showers are not measured; B2 is unknown.", ids, ["B2"], extra=c.extra)[0] is True
assert check_notes("B2 roll-in shower: information unavailable.", ids, ["B2"], extra=c.extra)[0] is True

# claims of an extra need that no building had are withheld per sentence
c2 = ctx_for()
call_tool(c2, "set_extra_needs", {"needs": ["step-free entry", "grab bars"], "reasons": []})
search(c2, "step-free entry", [], ["B1", "B3"])
search(c2, "grab bars", [], ["B1", "B3"])
VAGUE = "Extra needs like step-free entry and grab bars are noted in listing text but not measured."
assert check_notes(VAGUE, ids, ["B1"], extra=c2.extra) == (False, "")
ok, shown = check_notes("B1 is a fine start. " + VAGUE, ids, ["B1"], extra=c2.extra)
assert ok and "noted in listing" not in shown and "Agent note withheld: claimed an extra need" in shown, shown
keep = "Grab bars were not found in any listing text."
assert check_notes(keep, ids, ["B1"], extra=c2.extra) == (True, keep)
# grab bars WERE found for B2: a claim for B2 is kept
c3 = ctx_for()
call_tool(c3, "set_extra_needs", {"needs": ["grab bars"], "reasons": []})
search(c3, "grab bars", [], ["B2"])
claim = "B2 has grab bars in the listing text."
assert check_notes(claim, ids, ["B2"], extra=c3.extra) == (True, claim)

print("ok")
