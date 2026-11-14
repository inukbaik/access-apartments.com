"""Agent tools, defined once as data (name, description, JSON schema, Python function) so they
can later be exposed through MCP as well. The functions never raise: bad arguments, unknown
building ids and failures come back as {"error": "..."} so the agent loop stays in control.

A tool function takes (ctx, **args). `ctx` is a ToolContext holding the run's state.
"""
from finder.screen import passes_all, screen_area

MAX_UNITS = 12  # units listed by inspect_building (token cost)
CHECK_NAMES = ("hallway", "door", "turning")


class ToolContext:
    """State of one agent run. `screen` is injectable so tests need no network."""

    def __init__(self, screen=None, refresh=False, fixed=None):
        self.fixed = fixed       # (lat, lon, radius_km, limit): the user's search; the model cannot change it
        self.screen = screen or (lambda lat, lon, r, n: screen_area(lat, lon, r, n, refresh, log=lambda *_: None))
        self.ranked = None       # last search_area result (full records)
        self.ids = {}            # building_id -> ranked record
        self.inspected = []      # building_ids looked at with inspect_building
        self.finish_ids = None   # set by finish
        self.notes = ""

    def to_inspect(self):
        """Buildings worth a look: the best unit fails with "no data" or "bad measurement" and the
        building has other units that may hold the missing data."""
        return [bid for bid, r in self.ids.items() if needs_inspection(r)]


def needs_inspection(r):
    if r.get("error") or len(r["units"]) < 2:
        return False
    return any(c["status"] == "fail" and c["reason"] in ("no data", "bad measurement") for c in r["checks"])


def check_text(c):
    if c["status"] == "pass":
        return f"pass {c['value']}in"
    if c["reason"] == "no data":
        return "fail: no data"
    if c["reason"] == "bad measurement":
        return f"fail: bad measurement ({c['value']}in)"
    return f"fail: {c['value']}in, needs {c['threshold']:g}"


def _checks(rec):
    if rec.get("error"):
        return {"error": str(rec["error"])[:80]}
    return {c["check"]: check_text(c) for c in rec["checks"]}


def search_area(ctx, lat, lon, radius_km, limit):
    if ctx.fixed:
        lat, lon, radius_km, limit = ctx.fixed
    ranked = ctx.screen(lat, lon, radius_km, limit)
    ctx.ranked = ranked
    ctx.ids = {f"B{n}": r for n, r in enumerate(ranked, 1)}
    return {"buildings": [
        {"building_id": bid, "name": str(r["candidate"]["name"])[:40], "dist_km": r["candidate"]["dist_km"],
         "units": len(r["units"]), "best_unit_checks": _checks(r)}
        for bid, r in ctx.ids.items()]}


def inspect_building(ctx, building_id):
    if not ctx.ids:
        return {"error": "call search_area first"}
    key = str(building_id).strip().upper()
    r = ctx.ids.get(key)
    if r is None:
        return {"error": f"unknown building_id {building_id!r}; valid: {', '.join(ctx.ids)}"}
    if key not in ctx.inspected:
        ctx.inspected.append(key)
    units = [{"name": str(u["candidate"]["name"])[:40], "checks": _checks(u)} for u in r["units"][:MAX_UNITS]]
    out = {"building_id": key, "units": units}
    if len(r["units"]) > MAX_UNITS:
        out["more_units_not_shown"] = len(r["units"]) - MAX_UNITS
    return out


def finish(ctx, building_ids, notes):
    if not ctx.ids:
        return {"error": "call search_area first"}
    ids = [str(b).strip().upper() for b in building_ids]
    bad = [b for b in ids if b not in ctx.ids]
    if bad:
        return {"error": f"unknown building_id {bad}; valid: {', '.join(ctx.ids)}"}
    ctx.finish_ids = ids
    ctx.notes = str(notes).strip()
    return {"ok": True}


TOOLS = [
    {"name": "search_area",
     "description": "Screen listings near a point. Returns buildings ranked by measured accessibility "
                    "(best unit of each building) with hallway, door and turning-space check results.",
     "parameters": {"type": "object", "properties": {
         "lat": {"type": "number"}, "lon": {"type": "number"},
         "radius_km": {"type": "number", "description": "search radius, 0 to 10 km"},
         "limit": {"type": "integer", "description": "max buildings, 1 to 30"}},
         "required": ["lat", "lon", "radius_km", "limit"]},
     "fn": search_area},
    {"name": "inspect_building",
     "description": "List every unit of one building with its checks. Use it when the best unit fails "
                    "with 'no data' or 'bad measurement': another unit may have the missing measurement.",
     "parameters": {"type": "object", "properties": {"building_id": {"type": "string", "description": "e.g. B3"}},
                    "required": ["building_id"]},
     "fn": inspect_building},
    {"name": "finish",
     "description": "End the run. building_ids: the buildings you recommend looking at first. "
                    "notes: a short plain explanation for the user.",
     "parameters": {"type": "object", "properties": {
         "building_ids": {"type": "array", "items": {"type": "string"}},
         "notes": {"type": "string"}},
         "required": ["building_ids", "notes"]},
     "fn": finish},
]
BY_NAME = {t["name"]: t for t in TOOLS}

_TYPES = {"number": (int, float), "integer": (int,), "string": (str,), "array": (list,)}


def _validate(schema, args):
    if not isinstance(args, dict):
        return "arguments must be a JSON object"
    for k in schema.get("required", []):
        if k not in args:
            return f"missing argument {k!r}"
    for k, v in args.items():
        spec = schema["properties"].get(k)
        if spec is None:
            return f"unexpected argument {k!r}"
        ok = _TYPES[spec["type"]]
        if isinstance(v, bool) or not isinstance(v, ok):
            return f"argument {k!r} must be of type {spec['type']}"
        if spec["type"] == "array" and not all(isinstance(x, str) for x in v):
            return f"argument {k!r} must be a list of strings"
    return None


def call_tool(ctx, name, args):
    """Run a tool by name. Always returns a dict; failures are {"error": ...}."""
    tool = BY_NAME.get(name)
    if tool is None:
        return {"error": f"unknown tool {name!r}; tools: {', '.join(BY_NAME)}"}
    err = _validate(tool["parameters"], args)
    if err:
        return {"error": err}
    if name == "search_area":
        if not (-90 <= args["lat"] <= 90 and -180 <= args["lon"] <= 180):
            return {"error": "lat/lon out of range"}
        if not (0 < args["radius_km"] <= 10) or not (1 <= args["limit"] <= 30):
            return {"error": "radius_km must be in (0, 10] and limit in 1..30"}
    try:
        return tool["fn"](ctx, **args)
    except (Exception, SystemExit) as e:  # SystemExit: load_candidates exits when the index is missing
        return {"error": f"{name} failed: {e}"[:300]}


def openai_tools():
    """The tools in the OpenAI /chat/completions `tools` format."""
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["parameters"]}} for t in TOOLS]
