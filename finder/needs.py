"""Reviewed catalog of extra needs searched in CoStar listing text (not measured).

For each need: accepted phrases (a match is "listing says"), blocked look-alikes (never a match,
even if the agent supplies them), and aliases used to spot the need in a user's request.
Matching is case-insensitive on whole phrases (word boundaries); a hyphen and a space are the same.
A phrase right after "no", "not", "without", "non" or "lacks" does not count (negation guard).
"""
import re

CATALOG = {
    "roll-in shower": {
        "accepted": ["roll-in shower", "roll in shower", "curbless shower", "zero-threshold shower",
                     "zero threshold shower", "barrier-free shower"],
        "blocked": ["walk-in shower", "walk in shower", "step-in shower"],
        "aliases": ["rollin shower", "roll-in", "roll in", "curbless", "zero-entry shower",
                    "barrier-free shower", "wheelchair shower"],
    },
    "grab bars": {
        "accepted": ["grab bar", "grab rail", "grab handle", "safety bar"],
        "blocked": [],
        "aliases": ["grab bars", "grab rails", "grabbars", "handrails in the bathroom"],
    },
    "ramp / step-free entry": {
        "accepted": ["wheelchair ramp", "entry ramp", "ramped entry", "ramp access", "step-free entry",
                     "step free entry", "no-step entry", "no step entry", "zero-step entry",
                     "zero step entry", "zero step front entry", "step-free access"],
        "blocked": ["boat ramp", "loading ramp", "garage ramp", "parking ramp", "dock ramp", "skate ramp"],
        "aliases": ["ramp", "ramps", "step-free", "step free", "no steps", "no stairs", "zero-step",
                    "zero step", "stairs-free"],
    },
    "elevator": {
        "accepted": ["elevator"],
        "blocked": ["freight elevator", "service elevator", "elevator shaft"],
        "aliases": ["elevators", "lift"],
    },
    "wheelchair accessible": {
        "accepted": ["wheelchair accessible", "wheelchair access", "handicap accessible",
                     "handicapped accessible", "ada accessible", "ada compliant", "ada friendly",
                     "accessibility features", "disabled access"],
        "blocked": [],
        "aliases": ["wheelchair-friendly", "accessible home", "accessible unit"],
    },
}

_NEG = re.compile(r"\b(?:no|not|without|non|lacks?|lacking)\W+(?:\w+\W+)?$", re.I)


def normalize(s):
    """Lower-case, hyphens and runs of spaces become one space."""
    return " ".join(re.split(r"[\s\-]+", str(s).lower().strip())).strip()


def phrase_regex(phrase):
    words = [re.escape(w) for w in normalize(phrase).split()]
    return re.compile(r"(?<![A-Za-z0-9])" + r"[\s\-]+".join(words) + r"s?(?![A-Za-z0-9])", re.I)


def resolve_need(name):
    """(catalog key or None, display name). Matches the key, an accepted phrase or an alias exactly
    (after normalizing, ignoring a plural s)."""
    n = normalize(name)
    for key, c in CATALOG.items():
        names = [key, *c["accepted"], *c["aliases"]] + [key.split(" / ")[0]]
        if any(n == normalize(x) or n.rstrip("s") == normalize(x).rstrip("s") for x in names):
            return key, key
    return None, n[:40]


def detect_needs(text):
    """Catalog needs named in a request (for the backup path that runs without a model)."""
    found = []
    for key, c in CATALOG.items():
        spans = [m.span() for b in c["blocked"] for m in phrase_regex(b).finditer(text)]
        hit = any(not any(a < m.end() and m.start() < z for a, z in spans)
                  for p in [key.split(" / ")[0], *c["accepted"], *c["aliases"]]
                  for m in phrase_regex(p).finditer(text))
        if hit:
            found.append(key)
    return found


def reviewed_terms(key):
    return list(CATALOG[key]["accepted"]) if key in CATALOG else []


def blocked_terms(key):
    return list(CATALOG[key]["blocked"]) if key in CATALOG else []


def classify_terms(key, terms):
    """(reviewed, suggested, refused). reviewed: always searched (the need's accepted phrases);
    suggested: the agent's other terms; refused: [{term, why}] for blocked look-alikes."""
    acc = {normalize(t) for t in reviewed_terms(key)}
    blk = {normalize(t) for t in blocked_terms(key)}
    suggested, refused, seen = [], [], set()
    for t in terms:
        n = normalize(t)
        if not n or n in seen:
            continue
        seen.add(n)
        if n in blk:
            refused.append({"term": t, "why": f"'{t}' is a look-alike that does not mean {key}; "
                                              "it never counts as a match"})
        elif n not in acc:
            suggested.append(n)
    return reviewed_terms(key), suggested, refused


def _context(text, s, e, width=80):
    pad = max(0, (width - (e - s)) // 2)
    a, b = max(0, s - pad), min(len(text), e + pad)
    return ("..." if a else "") + text[a:b] + ("..." if b < len(text) else "")


def find_matches(key, reviewed, suggested, fields, limit=3):
    """Matches of the terms in fields [[source label, text], ...]. Reviewed phrases come first.
    A match inside a blocked look-alike or right after a negation is dropped. Each match:
    {phrase, source, context, reviewed}. At most one per (source, text)."""
    blocked = [phrase_regex(b) for b in blocked_terms(key)]
    out = []
    done = set()
    for terms, is_rev in ((reviewed, True), (suggested, False)):
        for term in terms:
            if normalize(term) in done:  # "roll-in shower" and "roll in shower" are one phrase
                continue
            done.add(normalize(term))
            rx = phrase_regex(term)
            for label, text in fields:
                spans = [m.span() for b in blocked for m in b.finditer(text)]
                for m in rx.finditer(text):
                    if any(a < m.end() and m.start() < z for a, z in spans):
                        continue
                    if _NEG.search(text[max(0, m.start() - 20):m.start()]):
                        continue
                    out.append({"phrase": m.group(0), "source": label,
                                "context": _context(text, m.start(), m.end()), "reviewed": is_rev})
                    break
                if len(out) >= limit:
                    return out
    return out
