"""Building info: how many stories and whether there is an elevator. INFORMATIONAL ONLY.
It is never a check: it does not affect pass/fail, ranking or eligibility. It is computed after the
ranked list is final, only for the buildings shown, and stored under rec["building_info"].

Stories cross-reference CoStar (numStoriesAboveGrade / storiesTotal) with Vexcel roof height.
Elevator status comes from CoStar only (Vexcel has no elevator data). Unknown is never "no".
"""
import math

from finder import needs

STORY_LO, STORY_HI = 4.0, 2.7   # metres per story: tallest and shortest plausible


def stories_range(h):
    return max(1, math.floor(h / STORY_LO)), max(1, math.ceil(h / STORY_HI))


def _rng(lo, hi):
    return f"{lo}" if lo == hi else f"{lo}–{hi}"


def _st(n):
    return f"{n} {'story' if n == 1 else 'stories'}"


def _vx_desc(vx, lo, hi):
    return f"Vexcel roof height {vx['height_m']} m (about {_rng(lo, hi)} stories)"


def combine_stories(facts, vexcel):
    costar = sorted({f["stories_total"] for f in facts if f.get("stories_total")})
    vx_ok = bool(vexcel) and vexcel.get("status") == "ok" and vexcel.get("height_m")
    lo = hi = None
    out = {"costar": costar, "vexcel": None}
    if vx_ok:
        lo, hi = stories_range(vexcel["height_m"])
        out["vexcel"] = {**vexcel, "lo": lo, "hi": hi}  # type: ignore[assignment]  # out is inferred from its first literal
    date = (vexcel or {}).get("photo_date") or ""
    photo = f" (photo {date[:7]})" if date else ""
    if len(costar) > 1:
        status = "disagree"
        text = "Sources disagree: CoStar records say " + " and ".join(map(str, costar)) + " stories"
        if vx_ok:
            text += f"; {_vx_desc(vexcel, lo, hi)}"
    elif costar and vx_ok:
        c = costar[0]
        if lo <= c <= hi:
            status = "agree"
            text = f"{_st(c)} (CoStar), consistent with Vexcel roof height {vexcel['height_m']} m{photo}"
        else:
            status = "disagree"
            text = f"Sources disagree: CoStar {_st(c)}; {_vx_desc(vexcel, lo, hi)}"
    elif costar:
        status = "costar_only"
        text = f"{_st(costar[0])} (CoStar); Vexcel height unavailable"
    elif vx_ok:
        status = "vexcel_only"
        text = f"about {_rng(lo, hi)} stories (Vexcel roof height {vexcel['height_m']} m; no CoStar record)"
    else:
        status, text = "unavailable", "Stories: information unavailable"
    out.update(status=status, text=text)  # type: ignore[call-overload]  # same
    return out


def combine_elevator(facts, text_mention=None):
    yes_ev, no_ev = [], []
    for f in facts:
        e = f.get("elevator") or {}
        if e.get("passenger") in ("yes", "conflict"):
            yes_ev.append("CoStar records a passenger elevator")
        elif e.get("flag_true"):
            yes_ev.append("CoStar listing marks an elevator")
        if e.get("passenger") in ("no", "conflict"):
            no_ev.append("CoStar records no passenger elevator")
    costar_yes = bool(yes_ev)
    if text_mention:
        yes_ev.append(f"listing text mentions \"{text_mention['phrase']}\" ({text_mention['source']})")
    yes_ev, no_ev = list(dict.fromkeys(yes_ev)), list(dict.fromkeys(no_ev))
    if yes_ev and no_ev:
        status, text = "disagree", "Sources disagree: " + "; ".join(yes_ev + no_ev)
    elif yes_ev:
        status = "confirmed" if costar_yes else "mentioned"
        text = "Elevator: " + "; ".join(yes_ev)
    elif no_ev:
        status, text = "none_recorded", no_ev[0]
    else:
        status, text = "unavailable", "Elevator: information unavailable"
    return {"status": status, "text": text, "evidence": yes_ev + no_ev}


def combine(facts, vexcel, text_mention=None):
    facts = facts or []
    st = combine_stories(facts, vexcel)
    el = combine_elevator(facts, text_mention)
    floors = [f["floor_number"] for f in facts if f.get("floor_number")]
    floor = floors[0] if floors else None
    vx = st["vexcel"]
    # Definite only when every available source says 2+ stories; otherwise "may".
    # When CoStar and Vexcel agree, the CoStar count (inside the Vexcel range) decides.
    multi = [c >= 2 for c in st["costar"]] + ([vx["lo"] >= 2] if vx and st["status"] != "agree" else [])
    maybe = any(c >= 2 for c in st["costar"]) or (vx and vx["hi"] >= 2)
    if multi and all(multi):
        need = "Units above the ground floor need an elevator."
    elif maybe:
        need = "May have upper floors; units above the ground floor would need an elevator."
    else:
        need = ""
    if need and floor:
        need += f" Listing says the unit is on floor {floor}."
    parts = [st["text"], el["text"]] + ([need] if need else [])
    return {"stories": st, "elevator": el, "elevator_need": need, "floor_number": floor,
            "message": ". ".join(p.rstrip(".") for p in parts) + "."}


def short(info):
    """Compact table cell."""
    s = info["stories"]
    c, v = s["costar"], s["vexcel"]
    st = {"agree": f"{c[0] if c else '?'} st ok", "disagree": "st: conflict",
          "costar_only": f"{c[0] if c else '?'} st (CoStar)",
          "vexcel_only": f"~{_rng(v['lo'], v['hi'])} st (Vexcel)" if v else "st: n/a",
          "unavailable": "st: n/a"}[s["status"]]
    el = {"confirmed": "elev: yes", "mentioned": "elev: listing", "none_recorded": "elev: none rec.",
          "disagree": "elev: conflict", "unavailable": "elev: n/a"}[info["elevator"]["status"]]
    return f"{st} | {el}"


def _unavailable(reason):
    return combine([], {"status": "unavailable", "reason": reason})


def _mention(sids, text_index):
    if not text_index:
        return None
    fields = []
    for sid in sids:
        for key in text_index["models"].get(sid, []):
            fields += text_index["records"][key]["fields"]
    hits = needs.find_matches("elevator", needs.reviewed_terms("elevator"), [], fields, limit=1)
    return hits[0] if hits else None


def annotate(ranked, facts=None, text_index=None, height_fn=None, log=print):
    """Set rec["building_info"] on each ranked building. Never raises for one record; never touches
    checks, order or anything else."""
    if height_fn is None:
        from finder.vexcel import building_height as height_fn
    for rec in ranked:
        try:
            sids = [u["candidate"]["sid"] for u in rec.get("units") or [rec]]
            fl = [f for sid in sids for f in (facts or {}).get(sid, [])]
            c = rec["candidate"]
            try:
                vx = height_fn(c["lat"], c["lon"])
            except Exception as e:  # noqa: BLE001 - informational only, must not break the run
                vx = {"status": "unavailable", "reason": f"Vexcel error: {e}"}
            try:
                mention = _mention(sids, text_index)
            except Exception:  # noqa: BLE001
                mention = None
            info = combine(fl, vx, mention)
        except Exception as e:  # noqa: BLE001
            log(f"  building info failed for one building: {e}")
            info = _unavailable(f"error: {e}")
        info["short"] = short(info)
        rec["building_info"] = info
    return ranked
