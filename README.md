# Accessible Spaces (HackPrinceton Fall 2026)

Find a place you can actually live in, then get around the building when you arrive.

- **Finder:** an agent that screens Houston and LA listings for wheelchair accessibility
  (hallway widths, door widths, bathroom turning space, entrance steps) using CoStar, Matterport
  and Vexcel data, and shows its evidence.
- **Glasses:** Meta Ray-Ban glasses that work out where you are inside a building by matching
  the camera view to its Matterport scan, then speak step-free directions.

## Start here

| File | What |
|---|---|
| [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) | The plan: idea, data, checks, architecture, phases, risks, pitch |
| [TASKS.md](TASKS.md) | Who is doing what right now |
| [AGENTS.md](AGENTS.md) | Team and coding-agent rules |
| [data/README.md](data/README.md) | Downloading the sponsor data (never committed) |
| [scripts/README.md](scripts/README.md) | Phase 0 test scripts |

## Layout

```
PROJECT_CONTEXT.md  TASKS.md  AGENTS.md  CLAUDE.md
docs/          discussion log, glasses SDK notes, EGM manual, hacker packet, designs/
scripts/       Phase 0 tests + shared helpers (mp_common.py)
finder/        Part A: listing screener
localize/      Part B: glasses localization and routing
data/          sponsor data, models_index.csv, photos (git-ignored)
out/ cache/    generated outputs and downloads (git-ignored)
legacy-archive/  superseded proposals
```

## Setup

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt
cp .env.example .env      # fill in from /costar-keys in the CoStar Discord
```

Then follow [data/README.md](data/README.md). Run everything from the repo root.
