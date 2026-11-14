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
from finder.screen import passes_all, print_table  # noqa: E402
from finder.tools import ToolContext, call_tool  # noqa: E402


def chk(name, status, reason, value, thr):
    return {"check": name, "status": status, "reason": reason, "value": value, "threshold": thr}


PASS = [chk("hallway", "pass", "measured", 40.0, 36), chk("door", "pass", "measured", 34.0, 32),
        chk("turning", "pass", "measured", 65.0, 60)]
NODATA = [chk("hallway", "pass", "measured", 40.0, 36), chk("door", "fail", "no data", None, 32),
          chk("turning", "pass", "measured", 65.0, 60)]
BAD = [chk("hallway", "pass", "measured", 40.0, 36), chk("door", "fail", "measured", 27.0, 32),
       chk("turning", "pass", "measured", 65.0, 60)]


def unit(sid, name, checks, km):
    return {"candidate": {"sid": sid, "name": name, "dist_km": km}, "checks": checks, "error": None}


def building(units):
    return {**units[0], "units": units}


def make_ranked(with_inspectable=True):
    ranked = [building([unit("a1", "Alpha Court", PASS, 0.1)]),
              building([unit("b1", "Beta House", NODATA, 0.2), unit("b2", "Beta House 2", PASS, 0.2)]
                       if with_inspectable else [unit("b1", "Beta House", NODATA, 0.2)]),
              building([unit("c1", "Gamma Hall", BAD, 0.3)])]
    return ranked


class FakeBackend:
    model, base_url = "fake", "http://fake/v1"

    def __init__(self, script, preflight_error=None):
        self.script, self.calls, self.preflight_error = list(script), 0, preflight_error

    def preflight(self, timeout=3):
        if self.preflight_error:
            raise LLMError(self.preflight_error)

    def chat(self, messages, tools, timeout=None):
        self.calls += 1
        item = self.script.pop(0) if self.script else ("", [])
        if isinstance(item, Exception):
            raise item
        return item


def call(name, args, i=0):
    return {"id": f"c{i}", "name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}


SEARCH = ("", [call("search_area", {"lat": 1.0, "lon": 2.0, "radius_km": 1.5, "limit": 10})])


def run(backend, ranked=None):
    ranked = ranked if ranked is not None else make_ranked()
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(out):
        res = answer("need a roll-in shower", 1.0, 2.0, 1.5, 10, backend, out_dir=d,
                     screen=lambda *a: ranked)
        trace = json.load(open(os.path.join(d, "agent_trace.json")))
    return res, out.getvalue(), trace


def table_of(ranked):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_table(ranked)
    return buf.getvalue()


EXPECT = table_of(make_ranked())

# strip_think
assert strip_think("<think>hmm\nmore</think>\nHello") == "Hello"
assert strip_think("plain") == "plain"

# tools: errors are dicts, never exceptions
ctx = ToolContext(screen=lambda *a: make_ranked())
assert "error" in call_tool(ctx, "nope", {})
assert "error" in call_tool(ctx, "search_area", {"lat": "x"})
assert "error" in call_tool(ctx, "inspect_building", {"building_id": "B1"})  # before search
assert len(call_tool(ctx, "search_area", {"lat": 1, "lon": 2, "radius_km": 1, "limit": 5})["buildings"]) == 3
assert "error" in call_tool(ctx, "inspect_building", {"building_id": "B99"})
assert len(call_tool(ctx, "inspect_building", {"building_id": "b2"})["units"]) == 2
assert "error" in call_tool(ctx, "finish", {"building_ids": ["B77"], "notes": ""})
assert ctx.to_inspect() == ["B2"]

# 1. normal run: search -> inspect -> early finish (everything worth inspecting was inspected,
#    so the model is not asked again); the table equals the deterministic one
fb = FakeBackend([SEARCH, ("", [call("inspect_building", {"building_id": "B2"})]), ("", [])])
res, out, trace = run(fb)
assert res.finished and fb.calls == 2 and "early finish" in res.reason, (res.reason, out)
assert EXPECT in out and "unavailable" not in out and trace["outcome"] == "finished"
assert [s["tool"] for s in trace["steps"]] == ["search_area", "inspect_building", "(auto finish)"]

# 1b. the model finishes itself with notes: shown under their own heading, statuses from our checks
fb = FakeBackend([SEARCH, ("", [call("finish", {"building_ids": ["B1", "B2"], "notes": "B1 passes all three checks. B2 needs a visit."})])])
res, out, trace = run(fb)
assert res.finished and fb.calls == 2 and EXPECT in out
assert "Agent notes (not a verdict)" in out and "B2 Beta House (does not pass all checks)" in out

# 2. notes claiming a failing building passes are withheld
fb = FakeBackend([SEARCH, ("", [call("finish", {"building_ids": ["B3"], "notes": "Gamma Hall passes all checks."})])])
res, out, trace = run(fb)
assert res.finished and "Agent notes withheld: contradicted measurements." in out
assert "Gamma Hall passes" not in out, out
assert trace["notes_withheld"] and EXPECT in out
ids = {f"B{n}": r for n, r in enumerate(make_ranked(), 1)}
assert check_notes("B3 is accessible.", ids)[0] is False
assert check_notes("B3 does not pass; B1 passes.", ids)[0] is True
assert check_notes("Everything is accessible.", ids, ["B3"])[0] is False

# 3. step limit -> banner + table (B2 is inspectable, so there is no early finish)
fb = FakeBackend([SEARCH, ("", [call("inspect_building", {"building_id": "B1"})]),
                  ("", [call("inspect_building", {"building_id": "B3"})])])
out = io.StringIO()
with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(out):
    answer("x", 1.0, 2.0, 1.5, 10, fb, max_steps=2, out_dir=d, screen=lambda *a: make_ranked())
out = out.getvalue()
assert "AI agent unavailable (reason: step limit of 2 reached without finish) \u2014 showing measurement-based results." in out
assert EXPECT in out and "Inspected by the agent before stopping: B1" in out and fb.calls == 2

# 4. two invalid tool calls in a row -> fallback
fb = FakeBackend([("", [call("bogus", {})]), ("", [call("search_area", "{not json")])])
res, out, trace = run(fb)
assert not res.finished and "2 consecutive invalid tool calls" in out and EXPECT in out
assert trace["outcome"] == "fallback" and "invalid" in trace["reason"]

# 5. repeated identical call -> fallback
fb = FakeBackend([SEARCH, ("", [call("inspect_building", {"building_id": "B1"})]), SEARCH])
res, out, trace = run(fb)
assert not res.finished and "repeated identical tool call" in out and EXPECT in out

# 6. LLMError on the first call -> fallback
fb = FakeBackend([LLMError("LLM call timed out after 45s")])
res, out, trace = run(fb)
assert not res.finished and "timed out after 45s" in out and EXPECT in out and fb.calls == 1

# 7. preflight failure -> fallback with no chat call
fb = FakeBackend([SEARCH], preflight_error="LLM server not reachable at http://x/v1: ConnectionError")
res, out, trace = run(fb)
assert fb.calls == 0 and "preflight" in out and EXPECT in out and trace["steps"] == []

# 8. nothing to inspect -> early finish, no extra chat call
fb = FakeBackend([SEARCH, ("", [call("finish", {"building_ids": [], "notes": "should not be asked"})])])
res, out, trace = run(fb, make_ranked(with_inspectable=False))
assert res.finished and fb.calls == 1 and "early finish" in res.reason, (fb.calls, res.reason)
assert table_of(make_ranked(False)) in out and "unavailable" not in out

# 9. no model at all
res, out, trace = run(None)
assert res is None and "--no-llm" in out and EXPECT in out and trace["outcome"] == "no_llm"

# 10. a model that never calls finish and returns text only
fb = FakeBackend([("hello", []), ("still talking", [])])
res, out, trace = run(fb)
assert not res.finished and EXPECT in out

print("ok")
