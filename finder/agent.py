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
from finder.tools import ToolContext, call_tool, openai_tools

SYSTEM_PROMPT = """You help screen rental listings for a wheelchair user. You plan and call tools; \
our code measures everything.
Rules:
- You never decide pass or fail. Only the tool results do. Never say a building passes or is \
accessible unless all three checks (hallway, door, turning) say pass.
- Only hallway width (36 in), doorway width (32 in) and turning space (60 in) are measured. Anything \
else the user asks for (for example a roll-in shower) is NOT measured: say so in your notes.
- Call search_area once with the exact arguments the user gives.
- Then call inspect_building for buildings whose best unit fails with "no data" or "bad measurement": \
another unit of the same building may have the missing measurement.
- Call finish when done: building_ids = buildings worth looking at first, notes = 1 to 3 short \
sentences for the user.
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


def check_notes(notes, ids, shortlist=()):
    """(ok, shown_notes). Withhold notes that claim a building passes/is accessible when our checks
    say it does not. `ids`: {building_id: ranked record}. Conservative: a claim sentence naming a
    non-passing building (by id or name), or naming no building while the shortlist holds one, is withheld."""
    failing = {bid: r for bid, r in ids.items() if not passes_all(r)}
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
        return f"{len(result['buildings'])} buildings"
    if name == "inspect_building":
        return f"{result['building_id']}: {len(result['units'])} units"
    return "ok"


def _argtext(args):
    if not isinstance(args, dict):
        return str(args)[:60]
    # notes are shown only after our contradiction check, never in the live line
    return ", ".join(f"{k}={json.dumps(v)}" for k, v in args.items() if k != "notes")[:90]


def run_agent(backend, request, ctx, max_steps=12, time_budget=120, call_timeout=45, log=print):
    """Run the loop. Returns AgentResult (finished True/False; reason says why not)."""
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
                {"role": "user", "content": f"{request}\nSearch with exactly: lat={lat}, lon={lon}, "
                                            f"radius_km={radius_km}, limit={limit}"}]
    tools = openai_tools()
    seen, invalid = set(), 0

    for step in range(1, max_steps + 1):
        remaining = time_budget - (time.monotonic() - t0)
        if remaining <= 0:
            return fallback(f"time budget of {time_budget:g}s used up")
        t1 = time.monotonic()
        try:
            text, calls = backend.chat(messages, tools, timeout=min(call_timeout, remaining))
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
            invalid += 1
            res.steps.append({"step": step, "tool": None, "text": text[:300], "llm_s": round(llm_s, 2),
                              "result": "no tool call"})
            log(f"[step {step}] (no tool call) llm {llm_s:.1f}s")
            if invalid >= 2:
                return fallback("2 consecutive invalid tool calls")
            messages.append({"role": "user", "content": "Call a tool. Call finish when you are done."})
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
            if c["name"] == "finish" and "error" not in result:
                res.finished, res.reason = True, "finished"
                res.notes, res.finish_ids = ctx.notes, ctx.finish_ids
                return res
            if invalid >= 2:
                return fallback("2 consecutive invalid tool calls")

        # Early finish without asking the model again: nothing (left) to inspect.
        if ctx.ranked is not None and not [b for b in ctx.to_inspect() if b not in ctx.inspected]:
            why = "nothing to inspect" if not ctx.inspected else "every building worth inspecting was inspected"
            log(f"[auto] {why}: finishing without another model call")
            res.steps.append({"step": step, "tool": "(auto finish)", "result": why})
            res.finished, res.reason = True, f"early finish: {why}"
            return res

    return fallback(f"step limit of {max_steps} reached without finish")


def answer(request, lat, lon, radius_km, limit, backend=None, refresh=False, max_steps=12, time_budget=120,
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

    if ctx.ranked is None:  # the model never searched (or no model): the deterministic pipeline
        if screen:
            ranked = screen(lat, lon, radius_km, limit)
        else:
            ranked = screen_area(lat, lon, radius_km, limit, refresh, out_dir=out_dir,
                                 log=lambda m: log(m) if "candidates within" in m else None)
    else:
        ranked = ctx.ranked
    ids = {f"B{n}": r for n, r in enumerate(ranked, 1)}

    if reason:
        print(f"\n{reason} — showing measurement-based results.")
    print_table(ranked)

    withheld = False
    if res and res.finished:
        if res.finish_ids:
            parts = [f"{b} {ids[b]['candidate']['name']} ({'passes all checks' if passes_all(ids[b]) else 'does not pass all checks'})"
                     for b in res.finish_ids if b in ids]
            print("\nAgent shortlist (statuses from our checks):\n  " + "\n  ".join(parts))
        if res.notes:
            ok, shown = check_notes(res.notes, ids, res.finish_ids)
            if ok:
                print("\nAgent notes (not a verdict):\n  " + shown)
            else:
                withheld = True
                print("\nAgent notes withheld: contradicted measurements.")
    if ctx.inspected:
        stopped = "" if res and res.finished else " before stopping"
        print(f"\nInspected by the agent{stopped}: {', '.join(ctx.inspected)}")

    os.makedirs(out_dir, exist_ok=True)
    trace = {"request": request, "model": getattr(backend, "model", None),
             "base_url": getattr(backend, "base_url", None),
             "outcome": "no_llm" if backend is None else ("finished" if res.finished else "fallback"),
             "reason": reason or res.reason, "notes": res.notes if res else "", "notes_withheld": withheld,
             "elapsed_s": round(time.monotonic() - started, 2), "steps": res.steps if res else []}
    with open(os.path.join(out_dir, "agent_trace.json"), "w") as f:
        json.dump(trace, f, indent=2)
    return res
