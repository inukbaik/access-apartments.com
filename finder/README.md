# Finder (Part A)

Listing screener: candidates near a point from `data/models_index.csv`, accessibility checks
(hallway, door, turning space), ranked results with evidence. Uncertainty means failure.

Owner and task list: [TASKS.md](../TASKS.md) lane A. Plan: [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) §4-5.

## Usage

Run from the repo root:

```
.venv/bin/python -m finder.screen --lat 34.0636 --lon -118.2999 --radius-km 2 --limit 15
.venv/bin/python finder/test_checks.py
```

Outputs: `out/finder/<sid>.json` per listing (candidate, checks, error) and `out/finder/ranked.json`.
Raw API data is cached in `cache/finder/` (use `--refresh` to re-fetch).

- Hallway under 36 in, doorway under 32 in, or no bathroom with a 60 in narrow side = **fail**.
- A check passes only when measured and meeting the threshold. Missing data = **fail (no data)**; a
  doorway under 20 in = **fail (bad measurement)**. Sizes are room bounding boxes, not clear widths.
- One listing per building, decided in this order (see `buildings.py`): (1) `street_key` of the address, (2) `street_key` of the name, (3) `costar_property_id`, (4) a "<building> - <unit>" name prefix within 50 m, (5) lat/lon within 15 m. `street_key` parses with `usaddress` and keeps house number (with fractions like "1286 1/2"), pre-direction and street name; it drops street type, unit, city and zip, and returns None for unit descriptions ("2BR, 1BA", "Studio"). Same key but over 150 m apart is not merged. When unsure, do not merge: a wrong merge can hide a failing unit. Other units shown as `+N`.
- Ranking: fewest fails, then fewest "no data", then nearest. Listings that failed to load go last.

## Agent

An LLM plans which tools to call; our code does the measuring and the ranking. Any OpenAI-compatible
server works (Ollama `/v1`, Gemini, Groq, OpenAI, LM Studio, vLLM). Tools live in `tools.py` as data
(`search_area`, `inspect_building`, `finish`), the backend in `llm.py`, the loop in `agent.py`.

```
.venv/bin/python -m finder.ask --lat 34.0242 --lon -118.2991 --radius-km 1.5 --limit 10 \
    "I use a power wheelchair and need a roll-in shower"
.venv/bin/python -m finder.ask ... --no-llm          # measurement-based results only
.venv/bin/python finder/test_agent.py                # scripted fake model, no network
```

- Config (env or flags `--base-url --model --api-key-env`): `FINDER_LLM_BASE_URL` (default
  `http://localhost:11434/v1`), `FINDER_LLM_MODEL` (default `qwen3:8b`), `FINDER_LLM_API_KEY`
  (default empty). Optional `FINDER_LLM_REASONING_EFFORT`: qwen3 thinking is switched off with
  `reasoning_effort: none` (details in `llm.py`); set `off` for providers that reject the parameter.
- Verdicts come only from `checks.py`. The model never decides pass/fail and cannot drop a check.
  Its notes print under "Agent notes (not a verdict)" and are withheld if they claim a failing
  building passes.
- Fails fast: 3 s preflight (`GET /models`), 45 s per LLM call, 120 s total, 12 steps, stop after 2
  invalid tool calls in a row or an identical repeated call. If nothing (left) is worth inspecting the
  run finishes without asking the model again (so the model's notes appear only when it calls `finish` itself).
- Fallback: on any of those, or any LLM error, you get a one-line banner (`AI agent unavailable
  (reason: ...) — showing measurement-based results.`) and the normal ranked table. Exit code 0.
- Every step is printed live and saved to `out/finder/agent_trace.json` (with the fallback reason).

## Extra needs (searched in CoStar listing text, not measured)

Core checks stay strict pass/fail from measurements. Needs they cannot measure (roll-in shower, grab
bars, ramp / step-free entry, elevator, wheelchair accessible) are searched in CoStar text and come
back per building as **listing says** (with the matched phrase, source field and ~80 chars of context)
or **information unavailable** (not mentioned, or no CoStar record). Unavailable is never "no".

```
.venv/bin/python -m finder.costar_text --rebuild-text-index    # build/inspect the index
.venv/bin/python finder/test_needs.py                          # made-up data, no network
```

- `costar_text.py` builds `cache/finder/costar_text.json` once (about 3 s, 17 MB; git-ignored) from
  `data/costar/`: Matterport model id to the text of its listing or property. It stores values only
  (never JSON field names). Residential: `remarks`, true `has...` flags as text ("has accessibility
  features"; the flags live in `resoValues`), highlights, feature lines and names. Commercial: notes,
  photo captions, apartment model and unit descriptions. Commercial `amenities` are skipped: the kit
  has only amenity ids and no catalog of names. Rebuild with `--rebuild-text-index` (also on `ask.py`).
- `needs.py` is the reviewed catalog: accepted phrases and blocked look-alikes per need ("walk-in
  shower" is never a roll-in shower). Whole-phrase, case-insensitive, hyphen = space. A phrase right
  after "no", "not", "without" is ignored. Edit the catalog there.
- Tools: `set_extra_needs(needs, reasons)` and `search_listing_text(need, terms, building_ids)`.
  Reviewed terms of a known need are always searched; the agent's own `terms` are allowed and their
  matches are labelled "agent-suggested match"; blocked terms are refused with an explanation.
- Limits enforced in code (a hit returns `{"stopped": ...}`, which is not an invalid call): at most 3
  extra needs, 2 search rounds per need, 5 terms per round, only the top 10 buildings by measurement
  ranking. A building searches all its units' models; found if any matches.
- Ranking: measurement key (fails, then no-data count) first; inside an equal group, more extra needs
  found first, then distance. A building with more failed core checks never moves above one with fewer.
- Without a working model (`--no-llm`, dead server, any fallback), or if the model sets no extra
  needs, the needs are read from the request words by the catalog and searched once with reviewed
  terms on the top 10.
- Notes that claim a building has a need without a "listing says" for it are withheld, like pass claims.
- `finder.screen` output is unchanged. `ask.py` adds one column per need, an "Extra needs" line and an
  "Evidence" section.
- Data caveat: in this kit no listing text contains a roll-in shower phrase; grab bars, step-free
  entry and "Wheelchair Access" highlights do occur.
