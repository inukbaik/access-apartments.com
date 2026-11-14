"""Searchable CoStar listing text, keyed by Matterport model id. Built once from the sponsor data kit
(data/costar/, never committed) and cached in cache/finder/costar_text.json (git-ignored).

Only VALUES are stored (remarks, feature lines, notes, captions), never JSON field names: matching
raw JSON would falsely hit key names such as "hasAccessibilityFeatures". Each text keeps a source
label such as "remarks" or "features: Bathroom" so evidence can say where a phrase came from.

Amenities: commercial `amenities` are integer ids and the kit ships no catalog of names (see
data/costar/concepts/apartments.md), so they are skipped.

Rebuild:  .venv/bin/python -m finder.costar_text --rebuild-text-index
"""
import argparse
import csv
import json
import os
import re
import sys
import time

KIT = "data/costar"
CACHE = "cache/finder/costar_text.json"
MAX_TEXT = 6000       # characters kept per text value
_memo = {}


def _clean(v):
    return re.sub(r"\s+", " ", v).strip()[:MAX_TEXT] if isinstance(v, str) else ""


class _Fields:
    """Collects (label, text) pairs, dropping empty and duplicate texts."""

    def __init__(self):
        self.items, self._seen = [], set()

    def add(self, label, value):
        t = _clean(value)
        if len(t) >= 3 and t.lower() not in self._seen:
            self._seen.add(t.lower())
            self.items.append([label, t])


def _model_map(path, key_col):
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mid = (row.get("MatterportModelId") or "").strip()
            if mid:
                out.setdefault(row[key_col].strip(), []).append(mid)
    return out


def _jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _residential_fields(listing, feats):
    f = _Fields()
    f.add("remarks", listing.get("remarks"))
    flags = {}
    for block in ("resoValues", "costarFeatureValues"):  # the flags live in resoValues in this kit
        for k, v in (listing.get(block) or {}).items():
            if v is True:
                flags[k] = True
    for k in sorted(flags):
        if k.startswith("has"):  # hasAccessibilityFeatures -> "has accessibility features"
            f.add("listing flags", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", k).lower())
    if feats:
        for h in feats.get("highlights") or []:
            f.add("highlights", h.get("text") if isinstance(h, dict) else h)
        for sec in feats.get("sections") or []:
            label = "features: " + (sec.get("subcategory") or sec.get("category") or "other")
            for line in sec.get("lines") or []:
                f.add(label, line)
        for ft in feats.get("features") or []:
            f.add("features: " + (ft.get("subcategory1") or ft.get("category") or "other"), ft.get("name"))
    return f.items


def _commercial_fields(p):
    f = _Fields()
    for n in p.get("notes") or []:
        f.add("notes", n.get("value"))
    f.add("photo caption", (p.get("primaryPhoto") or {}).get("caption"))
    for a in p.get("attachments") or []:
        f.add("photo caption", a.get("caption"))
    apt = p.get("propertyApartment") or {}
    for m in apt.get("models") or []:
        f.add("apartment model", m.get("modelName"))
        f.add("apartment model", m.get("modelDescription"))
        for a in m.get("attachments") or []:
            f.add("photo caption", a.get("caption"))
        for u in m.get("units") or []:
            f.add("unit description", u.get("unitDescription"))
            for a in u.get("attachments") or []:
                f.add("photo caption", a.get("caption"))
    for u in apt.get("units") or []:
        f.add("unit description", u.get("unitDescription"))
        for a in u.get("attachments") or []:
            f.add("photo caption", a.get("caption"))
    return f.items


def build_index(kit=KIT, log=print):
    t0 = time.monotonic()
    models, records = {}, {}
    # Residential: ListingId -> model ids; text from the listing and its features record.
    rmap = _model_map(f"{kit}/residential-listings.csv", "ListingId")
    feats = {str(r["id"]): r for r in _jsonl(f"{kit}/data/residential-listing-features.jsonl")}
    for l in _jsonl(f"{kit}/data/residential-listings.jsonl"):
        lid = str(l["id"])
        if lid not in rmap:
            continue
        key = f"r:{lid}"
        records[key] = {"kind": "residential", "id": lid, "fields": _residential_fields(l, feats.get(lid))}
        for mid in rmap[lid]:
            models.setdefault(mid, []).append(key)
    log(f"  residential: {sum(k.startswith('r:') for k in records)} records")
    # Commercial: PropertyId -> model ids; streamed (the file is ~190 MB).
    cmap = _model_map(f"{kit}/commercial-properties.csv", "PropertyId")
    for p in _jsonl(f"{kit}/data/commercial-property.jsonl"):
        pid = str(p["id"])
        if pid not in cmap:
            continue
        key = f"c:{pid}"
        records[key] = {"kind": "commercial", "id": pid, "fields": _commercial_fields(p)}
        for mid in cmap[pid]:
            models.setdefault(mid, []).append(key)
    log(f"  commercial: {sum(k.startswith('c:') for k in records)} records")
    return {"models": models, "records": records,
            "built_s": round(time.monotonic() - t0, 1),
            "note": "commercial amenities skipped: the kit has no amenity catalog (ids only)"}


def load_index(rebuild=False, path=CACHE, kit=KIT, log=print):
    """The text index; built and cached on first use (or when rebuild=True)."""
    if not rebuild and path in _memo:
        return _memo[path]
    if rebuild or not os.path.exists(path):
        if not os.path.isdir(kit):
            raise RuntimeError(f"CoStar kit not found at {kit}/ (see data/README.md); cannot build the text index")
        log("Building CoStar text index (one time) ...")
        idx = build_index(kit, log)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False)
        log(f"  built in {idx['built_s']}s, {os.path.getsize(path) / 1e6:.1f} MB at {path}")
    else:
        with open(path, encoding="utf-8") as f:
            idx = json.load(f)
    _memo[path] = idx
    return idx


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild-text-index", action="store_true")
    args = ap.parse_args()
    idx = load_index(rebuild=args.rebuild_text_index)
    print(f"{len(idx['models'])} Matterport models, {len(idx['records'])} records; {idx['note']}")
    index_csv = "data/models_index.csv"
    if os.path.exists(index_csv):
        with open(index_csv, newline="", encoding="utf-8") as f:
            sids = [r["sid"] for r in csv.DictReader(f)]
        hit = sum(s in idx["models"] for s in sids)
        print(f"{hit} of {len(sids)} models in {index_csv} have a CoStar text entry")


if __name__ == "__main__":
    sys.exit(main())
