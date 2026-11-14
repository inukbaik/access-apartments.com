"""Agent loop for the listing screener. Any LLM backend (see llm.py) plans and calls our tools;
our code does all the measuring and all the ranking. The model never decides pass/fail.

Fails fast and always falls back to the deterministic result (screen_area) instead of an error.
"""
import json
import os
import re
import time

from finder.llm import LLMError
from finder.screen import passes_all, print_table, screen_area
from finder.tools import CORE_CHECKS, ToolContext, call_tool, openai_tools, recommended_unit

SYSTEM_PROMPT = """You help screen rental listings for a wheelchair user. You plan and call tools; \
our code measures everything.
Rules:
- You never decide pass or fail. Only the tool results do. Never say a building passes or is \
accessible unless the tool results say it passes all required checks.
- Only hallway width (36 in), doorway width (32 in) and turning space (60 in) are measured. Anything \
else the user asks for (for example a roll-in shower) is NOT measured: say so in your notes.
Steps:
1. Call set_requirements first: checks = the checks this user needs (hallway, door and turning are \
always required), reasons = one short string per need.
2. Call search_area. Start from the point and radius the user message gives. Radius is 0.5 to 5 km, \
limit 5 to 20. The point must stay near the user's point.
3. If fewer than 3 buildings pass all required checks, consider widening the radius once or twice \
(call search_area again with a larger radius; results are merged).
4. Call inspect_building for buildings whose best unit fails with "no data" or "bad measurement": \
another unit of the same building may have the missing measurement. It returns recommended_unit, \
computed by code.
5. Always end with finish: building_ids = buildings worth looking at first, notes = 1 to 3 short \
sentences for the user. Never end with plain text.
Answer with tool calls only."""

CLAIM = re.compile(r"\b(pass|passes|passed|accessible|meets?|compliant|suitable)\b", re.I)
NEGATION = re.compile(r"\b(not|no|none|never|fails?|failed|failing|cannot|without|unknown|n't)\b|n't", re.I)


class AgentResult:
    def __init__(self):
        self.finished = False
        self.reason = ""          # why we fell back, or how the run ended
        self.notes = ""
        self.finish_ids = []
        self.steps = []
        self.ctx = None


def check_notes(notes, ids, shortlist=(), passes=passes_all):
    """(ok, shown_notes). Withhold notes that claim a building passes/is accessible when our checks
    say it does not. `ids`: {building_id: ranked record}. Conservative: a claim sentence naming a
    non-passing building (by id or name), or naming no building while the shortlist holds one, is withheld."""
    failing = {bid: r for bid, r in ids.items() if not passes(r)}
    short_fail = any(b in failing for b in shortlist)
    for sent in re.split(r"(?<=[.!?\n])\s+", notes or ""):
        if not CLAIM.search(sent) or NEGATION.search(sent):
            continue
        low = sent.lower()
        for bid, r in failing.items():
            name = str(r["candidate"]["name"]).strip().lower()
            if re.search(rf"\b{bid.lower()}\b", low) or (len(name) >= 4 and name in low):
                return False, ""
        if short_fail and not any(re.search(rf"\b{b.lower()}\b", low) for b in ids):
            return False, ""
    return True, notes


def _summary(name, result):
    if "error" in result:
        return "ERROR: " + result["error"][:100]
    if name == "search_area":
        c = f", clamped {'/'.join(result['clamped'])}" if result.get("clamped") else ""
        return f"{len(result['buildings'])} buildings ({result['new_buildings']} new, {result['total_buildings_seen']} seen){c}"
    if name == "set_requirements":
        return "required: " + ", ".join(result["required"])
    if name == "inspect_building":
        return f"{result['building_id']}: {len(result['units'])} units, visit {result['recommended_unit']}"
    return "ok"


def _argtext(args):
    if not isinstance(args, dict):
        return str(args)[:60]
    # notes are shown only after our contradiction check, never in the live line
    return ", ".join(f"{k}={json.dumps(v)}" for k, v in args.items() if k != "notes")[:90]


def run_agent(backend, request, ctx, max_steps=14, time_budget=120, call_timeout=45, log=print):
    """Run the loop. Returns AgentResult (finished True/False; reason says why not). Whatever was
    searched before a failure stays in ctx, so the caller can still show the merged results."""
    res = AgentResult()
    res.ctx = ctx
    lat, lon, radius_km, limit = ctx.fixed
    t0 = time.monotonic()

    def fallback(reason):
        res.reason = reason
        log(f"  agent stopped: {reason}")
        return res

    try:
        backend.preflight()
    except LLMError as e:
        return fallback(f"preflight: {e}")

    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{request}\nThe user's search point: lat={lat}, lon={lon}, "
                                            f"radius_km={radius_km}, limit={limit}. Start from it."}]
    tools = openai_tools()
    seen, invalid, nudged = set(), 0, False

    for step in range(1, max_steps + 1):
        remaining = time_budget - (time.monotonic() - t0)
        if remaining <= 0:
            return fallback(f"time budget of {time_budget:g}s used up")
        step_tools = tools
        if max_steps - step + 1 <= 1:  # last step: only finish is possible
            messages.append({"role": "user", "content": "Last step: call finish now with your notes."})
            step_tools = openai_tools(only=("finish",))
        t1 = time.monotonic()
        try:
            text, calls = backend.chat(messages, step_tools, timeout=min(call_timeout, remaining))
        except LLMError as e:
            return fallback(str(e))
        llm_s = time.monotonic() - t1
        if text:
            log(f"  model: {' '.join(text.split())[:110]}")
        messages.append({"role": "assistant", "content": text or None, "tool_calls": [
            {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
            for c in calls] or None})
        if not messages[-1]["tool_calls"]:
            del messages[-1]["tool_calls"]

        if not calls:
            res.steps.append({"step": step, "tool": None, "text": text[:300], "llm_s": round(llm_s, 2),
                              "result": "no tool call"})
            log(f"[step {step}] (no tool call) llm {llm_s:.1f}s")
            if nudged:
                return fallback("model stopped without calling finish (after one reminder)")
            nudged = True
            messages.append({"role": "user", "content": "You called no tool. Call finish with your notes."})
            continue

        for c in calls:
            t2 = time.monotonic()
            try:
                args = json.loads(c["arguments"] or "{}")
                result = None
            except ValueError:
                args, result = c["arguments"], {"error": "arguments are not valid JSON"}
            key = (c["name"], json.dumps(args, sort_keys=True) if result is None else c["arguments"])
            if key in seen:
                res.steps.append({"step": step, "tool": c["name"], "args": args, "result": "repeated call",
                                  "llm_s": round(llm_s, 2)})
                log(f"[step {step}] {c['name']}({_argtext(args)}) -> repeated identical call")
                return fallback("repeated identical tool call")
            seen.add(key)
            if result is None:
                result = call_tool(ctx, c["name"], args)
            tool_s = time.monotonic() - t2
            summ = _summary(c["name"], result)
            log(f"[step {step}] {c['name']}({_argtext(args)}) -> {summ}  (llm {llm_s:.1f}s, tool {tool_s:.1f}s)")
            res.steps.append({"step": step, "tool": c["name"], "args": args, "result": summ,
                              "llm_s": round(llm_s, 2), "tool_s": round(tool_s, 2)})
            llm_s = 0.0  # one LLM call may carry several tool calls: count it once
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result)})
            invalid = invalid + 1 if "error" in result else 0
            if c["name"] == "set_requirements" and "error" not in result:
                log("  " + requirements_line(ctx))
            if c["name"] == "finish" and "error" not in result:
                res.finished, res.reason = True, "finished"
                res.notes, res.finish_ids = ctx.notes, ctx.finish_ids
                return res
            if invalid >= 2:
                return fallback("2 consecutive invalid tool calls")

    return fallback(f"step limit of {max_steps} reached without finish")


def requirements_line(ctx):
    line = "Requirements: " + ", ".join(CORE_CHECKS)
    if ctx.added:
        line += " (+" + ", ".join(ctx.added) + ")"
    if ctx.req_note:
        line += f" [{ctx.req_note}]"
    if ctx.req_reasons:
        line += " \u2014 " + "; ".join(ctx.req_reasons)
    return line[:400]


def _radius_text(ctx):
    out = []
    for s_ in ctx.searches:
        t = f"{s_['radius_km']:g} km"
        if not out or out[-1] != t:
            out.append(t)
    return " \u2192 ".join(out)


def answer(request, lat, lon, radius_km, limit, backend=None, refresh=False, max_steps=14, time_budget=120,
           call_timeout=45, out_dir="out/finder", screen=None, log=print):
    """Run the agent (if backend) and print the final result. Never raises for LLM trouble;
    the table always comes from our own checks. Returns the AgentResult (or None with no backend)."""
    started = time.monotonic()
    ctx = ToolContext(screen=screen, refresh=refresh, fixed=(lat, lon, radius_km, limit))
    res = None
    if backend is None:
        reason = "AI agent off (--no-llm)"
    else:
        log(f"Agent: {backend.model} at {backend.base_url}")
        res = run_agent(backend, request, ctx, max_steps, time_budget, call_timeout, log)
        reason = None if res.finished else f"AI agent unavailable (reason: {res.reason})"

    labels = None
    if ctx.ranked is None:  # the model never searched (or no model): the deterministic pipeline
        if screen:
            ranked = screen(lat, lon, radius_km, limit)
        else:
            ranked = screen_area(lat, lon, radius_km, limit, refresh, out_dir=out_dir,
                                 log=lambda m: log(m) if "candidates within" in m else None)
        passes = passes_all
    else:
        ranked, labels = ctx.ranked_all()
        passes = ctx.passes
    ids = dict(zip(labels, ranked)) if labels else {f"B{n}": r for n, r in enumerate(ranked, 1)}

    if reason:
        print(f"\n{reason} \u2014 showing measurement-based results.")
    if labels:
        print("\n" + requirements_line(ctx))
    print_table(ranked, labels, passes if labels else None)

    withheld = False
    if res and res.finished:
        if res.finish_ids:
            parts = []
            for b in res.finish_ids:
                if b not in ids:
                    continue
                u = recommended_unit(ids[b], ctx.required)
                if passes(ids[b]) and u:
                    parts.append(f"{b} {ids[b]['candidate']['name']}: passes all required checks. "
                                 f"Visit unit: {u['candidate']['name']}")
                else:
                    parts.append(f"{b} {ids[b]['candidate']['name']}: does not pass all required checks")
            print("\nShortlist (statuses from our checks):\n  " + "\n  ".join(parts))
        if res.notes:
            ok, shown = check_notes(res.notes, ids, res.finish_ids, passes)
            if ok:
                print("\nAgent notes (not a verdict):\n  " + shown)
            else:
                withheld = True
                print("\nAgent notes withheld: contradicted measurements.")
    if labels:
        insp = ", ".join(ctx.inspected) or "none"
        print(f"\nSearched: {_radius_text(ctx)}; inspected {insp}; "
              f"{sum(passes(r) for r in ranked)} of {len(ranked)} pass")

    os.makedirs(out_dir, exist_ok=True)
    trace = {"request": request, "model": getattr(backend, "model", None),
             "base_url": getattr(backend, "base_url", None),
             "outcome": "no_llm" if backend is None else ("finished" if res.finished else "fallback"),
             "reason": reason or res.reason,
             "requirements": {"required": ctx.required, "added": ctx.added, "reasons": ctx.req_reasons,
                              "note": ctx.req_note},
             "searches": ctx.searches, "fetches": ctx.fetches, "inspected": ctx.inspected,
             "recommended": ctx.recommended, "notes": res.notes if res else "", "notes_withheld": withheld,
             "elapsed_s": round(time.monotonic() - started, 2), "steps": res.steps if res else []}
    with open(os.path.join(out_dir, "agent_trace.json"), "w") as f:
        json.dump(trace, f, indent=2)
    return res
