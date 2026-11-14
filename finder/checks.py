"""Accessibility checks. Pure functions: model data in, result dicts out. No API calls."""
M_TO_IN = 39.3701
HALL_MIN_IN = 36.0
DOOR_MIN_IN = 32.0
TURN_MIN_IN = 60.0  # 1.524 m turning circle
DOOR_PLAUSIBLE_MIN_IN = 20.0  # narrower "doorways" are bad measurements


def _result(check, status, reason, value, threshold, evidence, note):
    """status: pass | fail. reason: measured | no data | bad measurement."""
    return {"check": check, "status": status, "reason": reason, "value": value,
            "threshold": threshold, "unit": "in", "evidence": evidence, "note": note}


def _label(room):
    cls = room.get("classifications") or []
    return (cls[0].get("label") or "").lower() if cls else ""


def _narrow_in(room):
    dims = room.get("dimensions") or {}
    vals = [v for v in (dims.get("width"), dims.get("depth")) if v]
    return min(vals) * M_TO_IN if vals else None


def _measured(rooms, label):
    out = []
    for r in rooms or []:
        if _label(r) == label:
            side = _narrow_in(r)
            if side is not None:
                out.append((r.get("id"), side))
    return out


def check_hallway(rooms):
    note = "Width is the room bounding box, not a measured clear width."
    m = _measured(rooms, "hallway")
    if not m:
        return _result("hallway", "fail", "no data", None, HALL_MIN_IN, [], note)
    bad = [(i, w) for i, w in m if w < HALL_MIN_IN]
    low = round(min(w for _, w in m), 1)
    if bad:
        return _result("hallway", "fail", "measured", low, HALL_MIN_IN, [i for i, _ in bad], note)
    return _result("hallway", "pass", "measured", low, HALL_MIN_IN, [i for i, _ in m], note)


def check_door(floors):
    note = "Doorways are sparsely mapped; width may include the frame."
    m = []
    for floor in floors or []:
        for edge in floor.get("edges") or []:
            for op in edge.get("openings") or []:
                if op.get("type") == "doorway" and op.get("width"):
                    m.append((edge.get("id"), op["width"] * M_TO_IN))
    if not m:
        return _result("door", "fail", "no data", None, DOOR_MIN_IN, [], note)
    ok = [(i, w) for i, w in m if w >= DOOR_PLAUSIBLE_MIN_IN]
    junk = [(i, w) for i, w in m if w < DOOR_PLAUSIBLE_MIN_IN]
    bad = [(i, w) for i, w in ok if w < DOOR_MIN_IN]
    if bad:
        return _result("door", "fail", "measured", round(min(w for _, w in ok), 1), DOOR_MIN_IN,
                       sorted({i for i, _ in bad}), note)
    if junk:
        return _result("door", "fail", "bad measurement", round(min(w for _, w in junk), 1),
                       DOOR_MIN_IN, sorted({i for i, _ in junk}), note)
    return _result("door", "pass", "measured", round(min(w for _, w in ok), 1), DOOR_MIN_IN,
                   sorted({i for i, _ in ok}), note)


def check_turning(rooms):
    note = "Narrow side of the room bounding box vs a 60 in turning circle."
    m = _measured(rooms, "bathroom")
    if not m:
        return _result("turning", "fail", "no data", None, TURN_MIN_IN, [], note)
    best = round(max(w for _, w in m), 1)
    good = [i for i, w in m if w >= TURN_MIN_IN]
    if good:
        return _result("turning", "pass", "measured", best, TURN_MIN_IN, good, note)
    return _result("turning", "fail", "measured", best, TURN_MIN_IN, [i for i, _ in m], note)


def run_checks(model):
    return [check_hallway(model.get("rooms")), check_door(model.get("floors")),
            check_turning(model.get("rooms"))]
