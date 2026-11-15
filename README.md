# Accessible Spaces (HackPrinceton Fall 2026)

Find a place you can actually live in, then get around the building when you arrive.

Listings almost never say whether a wheelchair fits. Accessible Spaces screens real Houston and
Los Angeles listings using CoStar's data. It measures hallway widths, door widths and bathroom
turning space from Matterport scans, ranks the buildings, and shows the evidence for every verdict.

Built for the **CoStar "Inside and Out: AI for the Built World"** track. Uses the Matterport Model
API, Vexcel and the CoStar records kit.

## What it does

### Finder: screen listings for wheelchair access (`finder/`)

You say what you need in plain words and where you want to live. The finder does the following:

1. It finds Matterport-scanned listings near that point, using `data/models_index.csv`.
2. It pulls each listing's rooms and mapped door openings from the Matterport Model API.
3. It runs three accessibility checks:

| Check | Threshold (ADA, approximate) | Source |
|---|---|---|
| Hallway width | ≥ 36 in (0.914 m) | Width of rooms labelled Hallway |
| Door clear width | ≥ 32 in (0.813 m) | Wall-edge openings of type `doorway` |
| Wheelchair turning space | 60 in (1.524 m) circle | Narrow side of the bathroom |

4. It groups units into buildings by their parsed street address and shows one row per building:
   the best unit, plus `+N units`.
5. It ranks buildings by fewest fails, then fewest "no data" results, then distance.

**Uncertainty means failure.** A check passes only when it was measured and meets the threshold.
Missing data fails with the label **no data**. An implausible value, such as a "doorway" under
20 in, fails with the label **bad measurement**. People should never be sent to a place they
can't use because of a guess.

### Agent: plain-language requests

`finder.ask` puts an LLM in front of the screener. The model plans which tools to call:
`set_requirements`, `set_extra_needs`, `search_area`, `inspect_building`, `search_listing_text`
and `finish`. Our code does all the measuring and ranking.

- **Verdicts come only from the checks.** The model never decides pass or fail and cannot drop a
  check. If its notes claim that a failing building passes, they are withheld.
- **Extra needs from listing text.** Some needs can't be measured from a scan: roll-in shower,
  grab bars, ramp or step-free entry, elevator, and "wheelchair accessible". For these the finder
  searches the CoStar listing text against a reviewed phrase catalog (`finder/needs.py`). Each
  building gets either **listing says** (with the matched phrase and where it was found) or
  **information unavailable**. These results never count as a pass or a fail. They only reorder
  buildings whose measured results are equal.
- **Works with any model.** It works with any OpenAI-compatible server: Ollama (the default,
  `qwen3:8b`, so sponsor data stays on the laptop), LM Studio, vLLM, Groq, Gemini or OpenAI.
- **Fails fast and falls back.** If the model is slow, unreachable or makes bad tool calls, you
  get a one-line notice and the ranked results based only on measurements. Every step is saved
  to `out/finder/agent_trace.json`.

### Web page (`finder/web.py`)

`.venv/bin/python -m finder.web --warm` serves the finder at http://localhost:8800. Pick an area and
get the ranked buildings. A click on one shows its floor plan drawn from the scan with every doorway's
width, a photo of each doorway rendered from the nearest panorama, what the listing text says, and the
building's stories and elevator status (CoStar and Vexcel roof height; information only).

### Indoor localization test (`scripts/localize_test.py`)

This script tests whether a photo from a phone or from Meta Ray-Ban glasses can be matched to
the right spot inside a building's Matterport scan. It cuts the panoramas of the venue scan
(Rabinowitz Hall) into 8 views per scan position, embeds them with DINOv2, and matches each
photo to its nearest scan position. In the first run, about 4 of 6 glasses photos and 5 of 7
phone photos matched the right spot (judged by eye). Distinctive spots such as stairwells and
the atrium matched well.

## Findings from the data

In a survey of 800 listings across LA and Houston:

- **Doors are the bottleneck.** Only 4% of listings measure ≥ 32 in on every mapped doorway.
  (Surveyed before closet and pantry doorways were excluded, so this is a lower bound.)
- **Only 7 listings pass all three checks.**
- Door openings are sparse in the scans, and many rooms are unlabelled. This is why missing data
  must fail rather than pass.

## Quick start

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt
cp .env.example .env      # fill in from /costar-keys in the CoStar Discord
```

Then download the sponsor data as described in [data/README.md](data/README.md). That data is
never committed. Run everything from the repo root.

```sh
# Ranked screen near USC, Los Angeles (measurements only)
.venv/bin/python -m finder.screen --lat 34.0242 --lon -118.2991 --radius-km 1.5 --limit 10

# Ask in plain words (needs an LLM server; default is local Ollama with qwen3:8b)
ollama pull qwen3:8b
.venv/bin/python -m finder.ask --lat 34.0242 --lon -118.2991 --radius-km 1.5 --limit 10 \
    "I use a power wheelchair and need a roll-in shower"

# Same request without any LLM
.venv/bin/python -m finder.ask --lat 34.0242 --lon -118.2991 --radius-km 1.5 --limit 10 --no-llm \
    "I use a power wheelchair and need a roll-in shower"

# Unit tests (made-up data, no network)
for t in finder/test_*.py; do .venv/bin/python "$t"; done
```

To use a different model server, set `FINDER_LLM_BASE_URL`, `FINDER_LLM_MODEL` and
`FINDER_LLM_API_KEY` in `.env`. You can also pass `--base-url`, `--model` and `--api-key-env` on
the command line.

**Outputs:** `out/finder/<sid>.json` holds the checks for each listing, `out/finder/ranked.json`
holds the ranking, and `out/finder/agent_trace.json` holds the agent's steps. Raw API responses
are cached in `cache/finder/` (use `--refresh` to fetch them again).

## How it's built

```
"power wheelchair, roll-in shower" + lat/lon
  → LLM agent (any OpenAI-compatible server) plans tool calls
      search_area       → candidates near the point (models_index.csv)
      inspect_building  → Matterport rooms + door openings → checks.py verdicts
      search_listing_text → CoStar listing text vs. reviewed phrase catalog
  → buildings ranked by measured results, extra needs break ties
  → table with pass / fail (and why) per check, evidence, agent notes
```

| File | Role |
|---|---|
| `finder/candidates.py` | Listings near a point from the model index |
| `finder/matterport.py` | Matterport GraphQL queries (rooms, door openings), cached |
| `finder/checks.py` | Hallway, door and turning-space checks; the only source of verdicts |
| `finder/buildings.py` | Groups units into buildings by parsed street address |
| `finder/screen.py` | Measurement-only screen and ranking (CLI) |
| `finder/tools.py` | Agent tools as data, plus the limits enforced in code |
| `finder/agent.py` | Agent loop: time and step budgets, fail-fast checks, fallback |
| `finder/llm.py` | OpenAI-compatible chat backend |
| `finder/costar_text.py`, `finder/needs.py` | CoStar text index and reviewed extra-needs catalog |
| `finder/ask.py` | Plain-language CLI |
| `scripts/` | Phase 0 data check, localization test, venue panorama download |

More detail: [finder/README.md](finder/README.md), [scripts/README.md](scripts/README.md).

## Repo layout

```
finder/          listing screener and agent
localize/        indoor localization and routing
scripts/         Phase 0 tests and shared Matterport helper (mp_common.py)
docs/            discussion log, glasses SDK notes, EGM manual, designs
data/            sponsor data (git-ignored; see data/README.md)
out/ cache/      generated outputs and downloads (git-ignored)
egm/             design drafts and review reports
legacy-archive/  superseded proposals
```

For the team: the plan is in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), current work is in
[TASKS.md](TASKS.md), and the rules for coding agents are in [AGENTS.md](AGENTS.md).

## Data and privacy

The CoStar kit, the Matterport downloads and the API keys are sponsor data. They live only in
git-ignored `data/` and `.env`. No listing records are committed or quoted here. By default the
agent runs on a local model, so sponsor data does not leave the laptop.
