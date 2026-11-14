"""Agent tests with a scripted FakeBackend and made-up buildings (no LLM, no network).
Run from the repo root: .venv/bin/python finder/test_agent.py"""
import contextlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from finder.agent import answer, check_notes  # noqa: E402
from finder.llm import LLMError, strip_think  # noqa: E402
from finder.screen import passes_all, print_table, sort_key  # noqa: E402
from finder.tools import ToolContext, call_tool  # noqa: E402


def chk(name, status, reason, value, thr):
    return {"check": name, "status": status, "reason": reason, "value": value, "threshold": thr}


PASS = [chk("hallway", "pass", "measured", 40.0, 36), chk("door", "pass", "measured", 34.0, 32),
        chk("turning", "pass", "measured", 65.0, 60)]
NODATA = [chk("hallway", "pass", "measured", 40.0, 36), chk("door", "fail", "no data", None, 32),
          chk("turning", "pass", "measured", 65.0, 60)]
BAD = [chk("hallway", "pass", "measured", 40.0, 36), chk("door", "fail", "measured", 27.0, 32),
       chk("turning", "fail", "measured", 50.0, 60)]
NODATA2 = [chk("hallway", "fail", "no data", None, 36), chk("door", "fail", "no data", None, 32),
           chk("turning", "pass", "measured", 65.0, 60)]
LAT, LON = 34.0242, -118.2991  # the user's point (inside the LA box)


def unit(sid, name, checks, km):
    return {"candidate": {"sid": sid, "name": name, "dist_km": km}, "checks": checks, "error": None}


def building(units):
    units = sorted(units, key=sort_key)  # like screen_area: best unit first
    return {**units[0], "units": units}


def make_ranked(with_inspectable=True, alpha_units=1):
    alpha = [unit("a1", "Alpha Court", PASS, 0.1)]
    if alpha_units > 1:
        alpha = [unit("a1", "Alpha Court 1", PASS, 0.1), unit("a2", "Alpha Court 2", PASS, 0.2)]
    return [building(alpha),
            building([unit("b1", "Beta House", NODATA, 0.2), unit("b2", "Beta House 2", NODATA2, 0.2)]
                     if with_inspectable else [unit("b1", "Beta House", NODATA, 0.2)]),
            building([unit("c1", "Gamma Hall", BAD, 0.3)])]


class FakeBackend:
    model, base_url = "fake", "http://fake/v1"

    def __init__(self, script, preflight_error=None):
        self.script, self.calls, self.preflight_error = list(script), 0, preflight_error
        self.seen = []  # (last user message, tool names) per chat call

    def preflight(self, timeout=3):
        if self.preflight_error:
            raise LLMError(self.preflight_error)

    def chat(self, messages, tools, timeout=None):
        self.calls += 1
        last_user = [m["content"] for m in messages if m["role"] == "user"][-1]
        self.seen.append((last_user, [t["function"]["name"] for t in tools]))
        item = self.script.pop(0) if self.script else ("", [])
        if isinstance(item, Exception):
            raise item
        return item


def call(name, args, i=0):
    return {"id": f"c{i}", "name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}


def search(radius=1.5, limit=10, lat=LAT, lon=LON):
    return ("", [call("search_area", {"lat": lat, "lon": lon, "radius_km": radius, "limit": limit})])


SEARCH = search()
REQ = ("", [call("set_requirements", {"checks": ["hallway", "door", "turning"], "reasons": ["power wheelchair"]})])


def fin(ids, notes):
    return ("", [call("finish", {"building_ids": ids, "notes": notes})])


def run(backend, ranked=None, screen=None, **kw):
    ranked = ranked if ranked is not None else make_ranked()
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(out):
        res = answer("need a quiet flat", LAT, LON, 1.5, 10, backend, out_dir=d,
                     screen=screen or (lambda *a: ranked), **kw)
        trace = json.load(open(os.path.join(d, "agent_trace.json")))
    return res, out.getvalue(), trace


def table_of(ranked, labels=None):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_table(ranked, labels)
    return buf.getvalue()


EXPECT = table_of(make_ranked())             # numbered rows: used when the agent never searched
EXPECT_L = table_of(make_ranked(), ["B1", "B2", "B3"])  # labelled rows: after an agent search


def new_ctx(screen=None):
    return ToolContext(screen=screen or (lambda *a: make_ranked()), fixed=(LAT, LON, 1.5, 10))


# strip_think
assert strip_think("<think>hmm\nmore</think>\nHello") == "Hello"
assert strip_think("plain") == "plain"

# tools: errors are dicts, never exceptions
ctx = new_ctx()
S = {"lat": LAT, "lon": LON, "radius_km": 1, "limit": 5}
assert "error" in call_tool(ctx, "nope", {})
assert "error" in call_tool(ctx, "search_area", {"lat": "x"})
assert "error" in call_tool(ctx, "inspect_building", {"building_id": "B1"})  # before search
r = call_tool(ctx, "search_area", S)
assert len(r["buildings"]) == 3 and "clamped" not in r and r["passing_required_total"] == 1
assert "error" in call_tool(ctx, "inspect_building", {"building_id": "B99"})
ins = call_tool(ctx, "inspect_building", {"building_id": "b2"})
assert len(ins["units"]) == 2 and ins["recommended_unit"] is None and "reason" in ins["recommended_unit_reason"] + "reason"
assert "error" in call_tool(ctx, "finish", {"building_ids": ["B77"], "notes": ""})
assert ctx.to_inspect() == ["B2"]

# A. set_requirements: dropping a core check restores it; unknown check -> error dict
ctx = new_ctx()
r = call_tool(ctx, "set_requirements", {"checks": ["hallway"], "reasons": ["narrow flat"]})
assert r["required"] == ["hallway", "door", "turning"] and "core checks are always required" in r["note"]
assert ctx.req_note == "core checks are always required" and ctx.req_reasons == ["narrow flat"]
r = call_tool(ctx, "set_requirements", {"checks": ["roll-in shower"], "reasons": []})
assert "error" in r and "unknown check" in r["error"] and ctx.required == ["hallway", "door", "turning"]
# the registry hook: a registered check can be required, and it decides pass/fail through the hook
from finder import tools as T  # noqa: E402
T.OPTIONAL_CHECKS["entrance"] = lambda u: {"status": "pass" if u["candidate"]["sid"] == "a1" else "fail"}
try:
    r = call_tool(ctx, "set_requirements", {"checks": ["entrance"], "reasons": ["step-free entrance needed"]})
    assert r["required"] == ["hallway", "door", "turning", "entrance"] and "entrance" in ctx.added
    assert ctx.added["entrance"] == "step-free entrance needed"
    call_tool(ctx, "search_area", S)
    assert [ctx.passes(x) for x in ctx.ids.values()] == [True, False, False]
finally:
    del T.OPTIONAL_CHECKS["entrance"]

# B. search_area bounds: out of area, too far from the user's point -> error dicts; clamps are reported
ctx = new_ctx()
assert "outside the supported areas" in call_tool(ctx, "search_area", {**S, "lat": 40.7, "lon": -74.0})["error"]
assert "limit is 10 km" in call_tool(ctx, "search_area", {**S, "lat": 34.4})["error"]
assert not ctx.ids and not ctx.searches
r = call_tool(ctx, "search_area", {**S, "radius_km": 9, "limit": 100})
assert r["clamped"] == {"radius_km": {"asked": 9, "used": 5.0}, "limit": {"asked": 100, "used": 20}}, r
r = call_tool(new_ctx(), "search_area", {**S, "radius_km": 0.1, "limit": 1})
assert r["clamped"]["radius_km"]["used"] == 0.5 and r["clamped"]["limit"]["used"] == 5
# Houston is inside the bounds when the user searched there
hx = ToolContext(screen=lambda *a: make_ranked(), fixed=(29.76, -95.37, 2, 10))
assert "error" not in call_tool(hx, "search_area", {"lat": 29.77, "lon": -95.36, "radius_km": 1, "limit": 5})

# C. fetch cap: 80 models in total, then a cap error
ctx = new_ctx()
for n in range(4):  # limit 20 would fetch 60 > 80 - 0 is fine once; use limit 5 (20 each)
    r = call_tool(ctx, "search_area", {**S, "radius_km": 1 + n * 0.5})
    assert "error" not in r, r
assert ctx.fetches == 80
r = call_tool(ctx, "search_area", {**S, "radius_km": 4})
assert "fetch cap" in r["error"]
ctx = new_ctx()
call_tool(ctx, "search_area", {**S, "limit": 20})  # 60
assert "Use limit 5" in call_tool(ctx, "search_area", {**S, "limit": 10, "radius_km": 2})["error"]

# D. two searches merged and deduped by building (shared unit sid)
def two(lat, lon, r, n):
    if r < 2:
        return make_ranked()[:2]
    wide = make_ranked(alpha_units=2)
    extra = building([unit("d1", "Delta Tower", PASS, 1.8)])
    return wide + [extra]
ctx = new_ctx(two)
r1 = call_tool(ctx, "search_area", {**S, "radius_km": 1.5})
r2 = call_tool(ctx, "search_area", {**S, "radius_km": 3})
assert len(r1["buildings"]) == 2 and r2["new_buildings"] == 2 and r2["total_buildings_seen"] == 4, r2
assert len(ctx.ids["B1"]["units"]) == 2  # Alpha gained a unit from the wider search
ranked, labels = ctx.ranked_all()
assert len(ranked) == 4 and labels[:2] == ["B1", "B4"] and labels[-1] == "B3", labels
assert [s_["radius_km"] for s_ in ctx.searches] == [1.5, 3]

# 1. normal run: requirements -> search -> inspect -> finish with notes. No auto-finish: the model is
#    asked again after inspecting (it used to finish without a model call). Table = deterministic ranking.
fb = FakeBackend([REQ, SEARCH, ("", [call("inspect_building", {"building_id": "B2"})]),
                  fin(["B1", "B2"], "B1 passes all required checks. B2 is missing door data. A roll-in shower is not measured.")])
res, out, trace = run(fb)
assert res.finished and fb.calls == 4 and res.reason == "finished", (res.reason, out)
assert EXPECT_L in out and "unavailable" not in out and trace["outcome"] == "finished"
assert [s_["tool"] for s_ in trace["steps"]] == ["set_requirements", "search_area", "inspect_building", "finish"]
assert "Agent notes (not a verdict)" in out and "roll-in shower is not measured" in out
assert "B2 Beta House: does not pass all required checks" in out
assert "B1 Alpha Court: passes all required checks. Visit unit: Alpha Court" in out
assert "Requirements: hallway, door, turning" in out and "power wheelchair" in out
assert "Searched: 1.5 km; inspected B2; 1 of 3 pass" in out, out
assert trace["recommended"] == {"B2": None} and trace["searches"][0]["radius_km"] == 1.5

# 1b. the visit unit comes from code even when the model's notes name another unit
fb = FakeBackend([REQ, SEARCH, ("", [call("inspect_building", {"building_id": "B1"})]),
                  fin(["B1"], "Try Alpha Court 2 first.")])
res, out, trace = run(fb, make_ranked(alpha_units=2))
assert "Visit unit: Alpha Court 1" in out and "Visit unit: Alpha Court 2" not in out.split("Shortlist")[1].split("Agent notes")[0]
assert trace["recommended"] == {"B1": "Alpha Court 1"}
ctx = new_ctx(lambda *a: make_ranked(alpha_units=2))
call_tool(ctx, "search_area", S)
assert call_tool(ctx, "inspect_building", {"building_id": "B1"})["recommended_unit"] == "Alpha Court 1"

# 2. notes claiming a failing building passes are withheld
fb = FakeBackend([SEARCH, fin(["B3"], "Gamma Hall passes all checks.")])
res, out, trace = run(fb)
assert res.finished and "Agent notes withheld: contradicted measurements." in out
assert "Gamma Hall passes" not in out, out
assert trace["notes_withheld"] and EXPECT_L in out
ids = {f"B{n}": r for n, r in enumerate(make_ranked(), 1)}
assert check_notes("B3 is accessible.", ids)[0] is False
assert check_notes("B3 does not pass; B1 passes.", ids)[0] is True
assert check_notes("Everything is accessible.", ids, ["B3"])[0] is False

# 3. step limit -> banner + table with what was gathered (B2 is inspectable)
fb = FakeBackend([SEARCH, ("", [call("inspect_building", {"building_id": "B1"})]),
                  ("", [call("inspect_building", {"building_id": "B3"})])])
out = io.StringIO()
with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(out):
    answer("x", LAT, LON, 1.5, 10, fb, max_steps=3, out_dir=d, screen=lambda *a: make_ranked())
out = out.getvalue()
assert "AI agent unavailable (reason: step limit of 3 reached without finish) \u2014 showing measurement-based results." in out
assert EXPECT_L in out and "inspected B1, B3" in out and fb.calls == 3

# 3b. last step: the model is told, and only finish is offered; missing finish -> fallback keeps merged results
fb = FakeBackend([search(1.5), search(3), ("", [call("inspect_building", {"building_id": "B1"})])])
res, out, trace = run(fb, screen=two, max_steps=3)
assert fb.seen[0][0].startswith("need a quiet") and "Last step" not in fb.seen[1][0]
assert fb.seen[2][0] == "Last step: call finish now with your notes." and fb.seen[2][1] == ["finish"]
assert not res.finished and "step limit of 3" in out and trace["outcome"] == "fallback"
assert "Delta Tower" in out and "Searched: 1.5 km \u2192 3 km; inspected B1; 2 of 4 pass" in out, out
# ... and a model that does finish on the last step is honoured
fb = FakeBackend([SEARCH, REQ, fin(["B1"], "B1 is the best match.")])
res, out, trace = run(fb, max_steps=3)
assert res.finished and "B1 is the best match." in out

# 4. two invalid tool calls in a row -> fallback
fb = FakeBackend([("", [call("bogus", {})]), ("", [call("search_area", "{not json")])])
res, out, trace = run(fb)
assert not res.finished and "2 consecutive invalid tool calls" in out and EXPECT in out
assert trace["outcome"] == "fallback" and "invalid" in trace["reason"]

# 5. repeated identical call -> fallback
fb = FakeBackend([SEARCH, ("", [call("inspect_building", {"building_id": "B1"})]), SEARCH])
res, out, trace = run(fb)
assert not res.finished and "repeated identical tool call" in out and EXPECT_L in out

# 6. LLMError on the first call -> fallback
fb = FakeBackend([LLMError("LLM call timed out after 45s")])
res, out, trace = run(fb)
assert not res.finished and "timed out after 45s" in out and EXPECT in out and fb.calls == 1

# 7. preflight failure -> fallback with no chat call
fb = FakeBackend([SEARCH], preflight_error="LLM server not reachable at http://x/v1: ConnectionError")
res, out, trace = run(fb)
assert fb.calls == 0 and "preflight" in out and EXPECT in out and trace["steps"] == []

# 8. nothing left to inspect: NO auto-finish; the model is asked again and writes its notes
fb = FakeBackend([SEARCH, fin([], "B1 passes all required checks.")])
res, out, trace = run(fb, make_ranked(with_inspectable=False))
assert res.finished and fb.calls == 2 and res.reason == "finished" and "early finish" not in out
assert "B1 passes all required checks." in out

# 8b. a turn with no tool call is nudged once; the model then finishes
fb = FakeBackend([SEARCH, ("I think B1 is good.", []), fin(["B1"], "B1 is good.")])
res, out, trace = run(fb)
assert res.finished and fb.calls == 3 and fb.seen[2][0] == "You called no tool. Call finish with your notes."

# 9. no model at all
res, out, trace = run(None)
assert res is None and "--no-llm" in out and EXPECT in out and trace["outcome"] == "no_llm"

# 10. a model that never calls finish and returns text only: one nudge, then fallback
fb = FakeBackend([("hello", []), ("still talking", [])])
res, out, trace = run(fb)
assert not res.finished and EXPECT in out and fb.calls == 2

print("ok")
