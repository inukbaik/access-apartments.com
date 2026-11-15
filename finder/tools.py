"""Agent tools, defined once as data (name, description, JSON schema, Python function) so they
can later be exposed through MCP as well. The functions never raise: bad arguments, unknown
building ids and failures come back as {"error": "..."} so the agent loop stays in control.

A tool function takes (ctx, **args). `ctx` is a ToolContext holding the run's state.
Verdicts (pass/fail) come only from checks.py results; the model chooses what to look at.
"""
import math
import re

from finder import needs as N
from finder.screen import screen_area, sort_key

MAX_UNITS = 12  # units listed by inspect_building (token cost)
CORE_CHECKS = ("hallway", "door", "turning")  # always required
CHECK_NAMES = CORE_CHECKS
# Registry hook for future checks: name -> fn(unit_record) -> {"status": "pass"|"fail", ...}.
# Register a name here and the model may require it through set_requirements (5a adds "entrance").
OPTIONAL_CHECKS = {}  # type: ignore[var-annotated]  # empty registry
# Bounds the model cannot move.
RADIUS_RANGE, LIMIT_RANGE, MAX_FROM_ORIGIN_KM = (0.5, 5.0), (5, 20), 10.0
AREAS = {"LA": (33.5, 34.5, -119.0, -117.5), "Houston": (29.0, 30.5, -96.0, -94.8)}  # lat0 lat1 lon0 lon1
FETCH_CAP = 80
# Stoppers for extra needs (searched in CoStar listing text; never measured).
MAX_NEEDS, MAX_ROUNDS, MAX_TERMS, TOP_N = 3, 2, 5, 10
FOUND, UNAVAILABLE = "listing says", "information unavailable"


def allowed_checks():
    return list(CORE_CHECKS) + sorted(OPTIONAL_CHECKS)


def unit_passes(u, required):
    """True when this unit record passes every required check (core results from checks.py,
    optional ones from the registry)."""
    if u.get("error"):
        return False
    by = {c["check"]: c for c in u["checks"]}
    for name in required:
        if name in OPTIONAL_CHECKS:
            if OPTIONAL_CHECKS[name](u).get("status") != "pass":
                return False
        elif name not in by or by[name]["status"] != "pass":
            return False
    return True


def recommended_unit(rec, required):
    """The unit to visit: the best-ranked unit passing all required checks, or None. Computed by code."""
    for u in rec.get("units") or [rec]:
        if unit_passes(u, required):
            return u
    return None


class ExtraNeeds:
    """Extra needs and their search results. The text index is injectable (tests) or loaded lazily
    from the cache. Results: results[need][building_id] = {status, reason, evidence}."""

    def __init__(self, index=None):
        self._index = index
        self.needs = []        # need names (catalog key, or the user's words for an unknown need)
        self.reasons = []
        self.rounds = {}       # need -> search rounds used
        self.results = {}      # need -> {building_id: result}
        self.refused = []      # refused look-alike terms, for the trace
        self.error = ""        # why the text index could not be used, if so

    @property
    def index(self):
        if self._index is None:
            from finder.costar_text import load_index
            self._index = load_index()
        return self._index

    def add(self, names, reasons=()):
        """Add needs. Returns (names added, None) or (None, stop message) when over the limit."""
        resolved = list(dict.fromkeys(N.resolve_need(n)[1] for n in names if str(n).strip()))
        new = [n for n in resolved if n not in self.needs]
        if len(self.needs) + len(new) > MAX_NEEDS:
            return None, (f"extra-need limit: at most {MAX_NEEDS} extra needs per run; already set: "
                          f"{', '.join(self.needs) or 'none'}. Do not add more.")
        self.needs += new
        self.reasons += [str(r).strip()[:150] for r in reasons if str(r).strip()]
        return resolved, None

    def found_count(self, bid):
        return sum(self.results.get(n, {}).get(bid, {}).get("status") == FOUND for n in self.needs)

    def result(self, need, bid):
        r = self.results.get(need, {}).get(bid)
        return r or {"status": UNAVAILABLE, "reason": "not searched", "evidence": []}

    def _building(self, rec, need, key, reviewed, suggested):
        idx = self.index
        recs = []
        for u in rec.get("units") or [rec]:
            for rk in idx["models"].get(u["candidate"]["sid"], []):
                if rk not in recs:
                    recs.append(rk)
        if not recs:
            return {"status": UNAVAILABLE, "reason": "no CoStar record", "evidence": []}
        ev = []
        for rk in recs:
            for m in N.find_matches(key, reviewed, suggested, idx["records"][rk]["fields"]):
                ev.append({**m, "label": "reviewed match" if m["reviewed"] else "agent-suggested match",
                           "record": rk})
        ev = ev[:3]
        if ev:
            return {"status": FOUND, "reason": "", "evidence": ev}
        return {"status": UNAVAILABLE, "reason": "not found in listing text", "evidence": []}

    def search(self, ids, bids, need, terms):
        """One search round (no limit checks: callers check). Returns (results by building, refused)."""
        key, _ = N.resolve_need(need)
        reviewed, suggested, refused = N.classify_terms(key, terms)
        out = {}
        for bid in bids:
            r = self._building(ids[bid], need, key, reviewed, suggested)
            old = self.results.setdefault(need, {}).get(bid)
            if old and old["status"] == FOUND:  # a found stays found; add any new evidence
                if r["status"] == FOUND:
                    old["evidence"] = (old["evidence"] + [e for e in r["evidence"] if e not in old["evidence"]])[:3]
                r = old
            self.results[need][bid] = r
            out[bid] = r
        self.rounds[need] = self.rounds.get(need, 0) + 1
        self.refused += refused
        return out, refused


def top_ids(ids, n=TOP_N):
    """The top n building ids by the code ranking of the measurements alone (no extra-need boost)."""
    return [b for b, _ in sorted(ids.items(), key=lambda kv: sort_key(kv[1]))][:n]


def rank_with_extra(ids, extra=None):
    """([records], [building ids]), best first: the measurement ranking key (error, fails, no-data
    count), then more extra needs found, then distance. A building with more failed core checks never
    moves above one with fewer."""
    def key(kv):
        k = sort_key(kv[1])
        return k[:3] + (-(extra.found_count(kv[0]) if extra else 0),) + k[3:]
    order = sorted(ids.items(), key=key)
    return [r for _, r in order], [b for b, _ in order]


class ToolContext:
    """State of one agent run. `screen` is injectable so tests need no network."""

    def __init__(self, screen=None, refresh=False, fixed=None, text_index=None):
        self.fixed = fixed       # (lat, lon, radius_km, limit): the user's CLI search; bounds are measured from it
        self._cands = None       # candidates fetched by the last default-screen call
        self.screen = screen or (lambda lat, lon, r, n: screen_area(lat, lon, r, n, refresh, log=self._note))
        self.ids = {}            # building_id -> merged record (all searches); ids are stable
        self.searches = []       # one dict per successful search_area
        self.fetches = 0         # candidates fetched so far (cap FETCH_CAP)
        self.inspected = []      # building_ids looked at with inspect_building
        self.recommended = {}    # building_id -> unit name chosen by code (None if no unit passes)
        self.required = list(CORE_CHECKS)
        self.added = {}          # optional check name -> the model's reason
        self.req_reasons = []
        self.req_note = ""
        self.req_set = False
        self.finish_ids = None
        self.notes = ""
        self.extra = ExtraNeeds(text_index)

    def _note(self, msg):
        m = re.match(r"(\d+) candidates within", msg)
        if m:
            self._cands = int(m.group(1))

    @property
    def ranked(self):
        """None before any search; otherwise every building seen, best first."""
        return self.ranked_all()[0] if self.ids else None

    def ranked_all(self):
        """([records best first], [building ids in the same order])."""
        return rank_with_extra(self.ids, self.extra)

    def passes(self, rec):
        return recommended_unit(rec, self.required) is not None

    def to_inspect(self):
        return [bid for bid, r in self.ids.items() if needs_inspection(r)]

    def merge(self, ranked):
        """Merge one search's buildings. A building sharing any unit (sid) with a known one is the
        same building. Returns (building ids of this search, number of new buildings)."""
        out, new = [], 0
        for rec in ranked:
            sids = {u["candidate"]["sid"] for u in rec["units"]}
            bid = next((b for b, old in self.ids.items()
                        if sids & {u["candidate"]["sid"] for u in old["units"]}), None)
            if bid is None:
                bid, new = f"B{len(self.ids) + 1}", new + 1
                self.ids[bid] = rec
            else:
                units = {u["candidate"]["sid"]: u for u in self.ids[bid]["units"]}
                units.update({u["candidate"]["sid"]: u for u in rec["units"]})
                units = sorted(units.values(), key=sort_key)  # type: ignore[assignment]  # units rebound from dict to list
                self.ids[bid] = {**units[0], "units": units}
            out.append(bid)
        return out, new


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


def set_requirements(ctx, checks, reasons):
    allowed = allowed_checks()
    names = [str(c).strip().lower() for c in checks]
    bad = [c for c in names if c not in allowed]
    if bad:
        return {"error": f"unknown check {bad}; available checks: {', '.join(allowed)}. Needs that no check "
                         "measures (e.g. a roll-in shower) go in reasons and in your final notes."}
    req = list(CORE_CHECKS) + [c for c in names if c not in CORE_CHECKS]
    req = list(dict.fromkeys(req))
    restored = [c for c in CORE_CHECKS if c not in names]
    reasons = [str(r).strip()[:150] for r in reasons if str(r).strip()]
    ctx.required = req
    ctx.req_reasons = reasons
    ctx.req_set = True
    ctx.added = {}
    for c in req:
        if c not in CORE_CHECKS:
            hit = [r for r in reasons if c in r.lower()]
            ctx.added[c] = hit[0] if hit else "; ".join(reasons)
    ctx.req_note = "core checks are always required" if restored else ""
    out = {"ok": True, "required": req}
    if ctx.req_note:
        out["note"] = ctx.req_note + f" (added back: {', '.join(restored)})"
    return out


def set_extra_needs(ctx, needs, reasons):
    names, stop = ctx.extra.add(needs, reasons)
    if stop:
        return {"stopped": stop}
    out = {}
    for n in names:
        key, _ = N.resolve_need(n)
        out[n] = {"reviewed_terms": N.reviewed_terms(key) or "none (any term you give is agent-suggested)",
                  "blocked_look_alikes": N.blocked_terms(key)}
    return {"ok": True, "extra_needs": ctx.extra.needs, "terms": out,
            "note": "Extra needs are searched in listing text, not measured. Then call search_listing_text."}


def search_listing_text(ctx, need, terms, building_ids):
    ex = ctx.extra
    _, name = N.resolve_need(need)
    if name not in ex.needs:
        return {"error": f"{need!r} is not one of the extra needs; call set_extra_needs first. "
                         f"Current: {', '.join(ex.needs) or 'none'}"}
    if not ctx.ids:
        return {"error": "call search_area first"}
    keys = [str(b).strip().upper() for b in building_ids]
    bad = [b for b in keys if b not in ctx.ids]
    if bad or not keys:
        return {"error": f"unknown building_id {bad}; valid: {', '.join(ctx.ids)}" if bad
                else "building_ids is empty"}
    if ex.rounds.get(name, 0) >= MAX_ROUNDS:
        return {"stopped": f"search-round limit: {MAX_ROUNDS} rounds already used for '{name}'. "
                           "Do not search it again; call finish."}
    if len(terms) > MAX_TERMS:
        return {"stopped": f"term limit: at most {MAX_TERMS} terms per round, you sent {len(terms)}. "
                           "Send fewer terms."}
    top = top_ids(ctx.ids)
    outside = [b for b in keys if b not in top]
    if outside:
        return {"stopped": f"top-{TOP_N} limit: only the current top {TOP_N} buildings can be searched "
                           f"({', '.join(top)}); not allowed: {', '.join(outside)}."}
    res, refused = ex.search(ctx.ids, list(dict.fromkeys(keys)), name, terms)
    out = {"need": name, "round": ex.rounds[name], "rounds_left": MAX_ROUNDS - ex.rounds[name],
           "results": [{"building_id": b, "status": r["status"],
                        **({"reason": r["reason"]} if r["reason"] else {}),
                        **({"evidence": [{"matched": e["phrase"], "source": e["source"], "context": e["context"],
                                          "label": e["label"]} for e in r["evidence"][:2]]}
                           if r["evidence"] else {})}
                       for b, r in res.items()]}
    if refused:
        out["refused_terms"] = [r["why"] for r in refused]
    return out


def _in_area(lat, lon):
    return any(a <= lat <= b and c <= lon <= d for a, b, c, d in AREAS.values())


def search_area(ctx, lat, lon, radius_km, limit):
    from finder.candidates import haversine_km
    vals = (lat, lon, radius_km)
    if not all(math.isfinite(v) for v in vals):
        return {"error": "lat, lon and radius_km must be finite numbers"}
    if not _in_area(lat, lon):
        return {"error": "point is outside the supported areas: Los Angeles (lat 33.5 to 34.5, lon -119 to -117.5) "
                         "and Houston (lat 29 to 30.5, lon -96 to -94.8)"}
    if ctx.fixed:
        d = haversine_km(ctx.fixed[0], ctx.fixed[1], lat, lon)
        if d > MAX_FROM_ORIGIN_KM:
            return {"error": f"point is {d:.1f} km from the user's search point; the limit is {MAX_FROM_ORIGIN_KM:g} km"}
    clamped = {}
    r_used = min(max(radius_km, RADIUS_RANGE[0]), RADIUS_RANGE[1])
    l_used = min(max(limit, LIMIT_RANGE[0]), LIMIT_RANGE[1])
    if r_used != radius_km:
        clamped["radius_km"] = {"asked": radius_km, "used": r_used}
    if l_used != limit:
        clamped["limit"] = {"asked": limit, "used": l_used}
    pool = min(l_used * 4, 60)  # screen_area fetches up to this many candidates
    left = FETCH_CAP - ctx.fetches
    if pool > left:
        if left < LIMIT_RANGE[0] * 4:
            return {"error": f"fetch cap reached: {FETCH_CAP} models fetched in total, {ctx.fetches} used. "
                             "No more searches; inspect or finish."}
        return {"error": f"fetch cap: {FETCH_CAP} models in total, {ctx.fetches} used; limit {l_used} could "
                         f"fetch {pool}. Use limit {left // 4} or less."}
    ctx._cands = None
    ranked = ctx.screen(lat, lon, r_used, l_used)
    ctx.fetches += ctx._cands if ctx._cands is not None else pool
    ids, new = ctx.merge(ranked)
    ctx.searches.append({"lat": lat, "lon": lon, "radius_km": r_used, "limit": l_used, "new": new})
    out = {"buildings": [
        {"building_id": bid, "name": str(ctx.ids[bid]["candidate"]["name"])[:40],
         "dist_km": ctx.ids[bid]["candidate"]["dist_km"], "units": len(ctx.ids[bid]["units"]),
         "passes_required": ctx.passes(ctx.ids[bid]), "best_unit_checks": _checks(ctx.ids[bid])}
        for bid in ids],
        "new_buildings": new, "total_buildings_seen": len(ctx.ids),
        "passing_required_total": sum(ctx.passes(r) for r in ctx.ids.values()),
        "fetches_used": ctx.fetches, "fetch_cap": FETCH_CAP}
    if clamped:
        out["clamped"] = clamped
    return out


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
    rec = recommended_unit(r, ctx.required)
    ctx.recommended[key] = str(rec["candidate"]["name"]) if rec else None
    out = {"building_id": key, "units": units,
           "recommended_unit": ctx.recommended[key]}
    if rec is None:
        out["recommended_unit_reason"] = "no unit passes all required checks"
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
    {"name": "set_requirements",
     "description": "Call this first. checks: the checks this user needs, from the available names (hallway, "
                    "door, turning). Those three are ALWAYS required even if you leave them out. reasons: one "
                    "short string per need, e.g. 'power wheelchair -> hallway 36 in'. Needs no check measures "
                    "(shower type, etc.) go in reasons only.",
     "parameters": {"type": "object", "properties": {
         "checks": {"type": "array", "items": {"type": "string"}},
         "reasons": {"type": "array", "items": {"type": "string"}}},
         "required": ["checks", "reasons"]},
     "fn": set_requirements},
    {"name": "set_extra_needs",
     "description": "Call after set_requirements. Extra needs the user mentions that no check measures "
                    "(roll-in shower, grab bars, ramp / step-free entry, elevator, wheelchair accessible). "
                    "They are searched in CoStar listing text and reported as 'listing says' or "
                    "'information unavailable'; they are never measured and never decide pass/fail. "
                    "At most 3. needs: short names. reasons: one short string per need.",
     "parameters": {"type": "object", "properties": {
         "needs": {"type": "array", "items": {"type": "string"}},
         "reasons": {"type": "array", "items": {"type": "string"}}},
         "required": ["needs", "reasons"]},
     "fn": set_extra_needs},
    {"name": "search_listing_text",
     "description": "Search CoStar listing text for one extra need in some buildings. Reviewed terms for "
                    "known needs are always searched; terms adds your own (at most 5; matches from them are "
                    "labelled agent-suggested; look-alikes such as 'walk-in shower' are refused). Only the "
                    "current top 10 buildings; at most 2 rounds per need. If nothing is found, retry once "
                    "with other terms, then stop.",
     "parameters": {"type": "object", "properties": {
         "need": {"type": "string"},
         "terms": {"type": "array", "items": {"type": "string"}},
         "building_ids": {"type": "array", "items": {"type": "string"}}},
         "required": ["need", "terms", "building_ids"]},
     "fn": search_listing_text},
    {"name": "search_area",
     "description": "Screen listings near a point (Los Angeles or Houston, within 10 km of the user's point). "
                    "Returns buildings ranked by measured accessibility. radius_km is clamped to 0.5-5 and "
                    "limit to 5-20. Results of several searches are merged; at most 80 models are fetched in total.",
     "parameters": {"type": "object", "properties": {
         "lat": {"type": "number"}, "lon": {"type": "number"},
         "radius_km": {"type": "number", "description": "search radius, 0.5 to 5 km"},
         "limit": {"type": "integer", "description": "max buildings, 5 to 20"}},
         "required": ["lat", "lon", "radius_km", "limit"]},
     "fn": search_area},
    {"name": "inspect_building",
     "description": "List every unit of one building with its checks and a recommended_unit (computed by "
                    "code). Use it when the best unit fails with 'no data' or 'bad measurement'.",
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
        if spec["type"] == "array" and not all(isinstance(x, str) for x in v):  # type: ignore[union-attr]  # v checked as array by spec
            return f"argument {k!r} must be a list of strings"
    return None


def call_tool(ctx, name, args):
    """Run a tool by name. Always returns a dict; failures are {"error": ...}."""
    tool = BY_NAME.get(name)
    if tool is None:
        return {"error": f"unknown tool {name!r}; tools: {', '.join(BY_NAME)}"}  # type: ignore[arg-type]  # BY_NAME keys are str
    err = _validate(tool["parameters"], args)
    if err:
        return {"error": err}
    try:
        return tool["fn"](ctx, **args)  # type: ignore[operator]  # tool["fn"] is callable
    except (Exception, SystemExit) as e:  # SystemExit: load_candidates exits when the index is missing
        return {"error": f"{name} failed: {e}"[:300]}


def openai_tools(only=None):
    """The tools in the OpenAI /chat/completions `tools` format (optionally only the named ones)."""
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["parameters"]}}
            for t in TOOLS if only is None or t["name"] in only]
