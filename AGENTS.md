# AGENTS.md: HackPrinceton F26 team repo

Shared rules for every coding agent on this team (Claude Code, Codex, others). Claude Code
loads this file through `CLAUDE.md`. Keep this file to **stable conventions**: put design
decisions in design documents, not here (see "EGM" below for why).

## Where the plan lives

| File | What it is |
|---|---|
| `PROJECT_CONTEXT.md` | **The plan**: idea, data facts, accessibility checks, architecture, phases, risks, pitch. |
| `TASKS.md` | Who is doing what right now, and which folders each lane touches. |
| `docs/designs/` | **Approved designs.** Build from these. Index: `docs/designs/SITEMAP.md`. |
| `egm/` | EGM drafts and review reports (working files, committed so the team can see them). |
| `legacy-archive/` | Superseded proposals. Background only; don't build from them. |
| `docs/DISCUSSION_LOG.md` | Why we picked this idea and which ideas we rejected. |
| `docs/GLASSES_SDK.md` | Notes on the Ray-Ban Meta glasses SDK (setup, gotchas, reusable code). |
| `docs/hacker-packet.pdf` | Official rules, tracks, judging. |
| `data/README.md` | How to download the sponsor data locally (never committed). |

If these files disagree, the newest approved design in `docs/designs/` wins, then
`PROJECT_CONTEXT.md`. If something is still unclear, ask the human; don't guess.

## Hard constraints

- **Deadline: 8:00 AM Sun Nov 15, 2026** (Devpost). The repo must stay public.
- The live demo is at most 2 minutes. Keep the demo path working at all times.

## Working rules

- Build from an approved design when one exists. If the code has to differ from the design, say
  so in your summary so the design can be updated.
- Only build what was asked. Stretch features go on a branch (`feat/<name>`), not `main`.
- When data is missing, the product says **"unknown"**. Never present a guess as fact.
- Prefer simple, readable code. Every external call (APIs, models) fails loudly with a clear
  message, never silently.

## Layout and conventions

- `scripts/`: Phase 0 tests and shared helpers (`mp_common.py` has the Matterport `graph()` call).
  `finder/`: Part A (listing screener). `localize/`: Part B (glasses localization and routing).
- Python 3, one `.venv` at the repo root, `pip install -r scripts/requirements.txt`.
  **Run everything from the repo root.**
- Downloads and sponsor data go in `data/`, generated outputs in `out/`, caches in `cache/`.
  All three are git-ignored.

## Secrets

- API keys go in `.env` only (git-ignored). Never paste keys into code, docs, designs, commits
  or EGM files. Add new variable names (no values) to `.env.example`.

## Git (shared repo, several people pushing)

- `git pull --rebase` before you start and before you push.
- Small commits with clear messages. Don't rewrite or force-push shared history.
- Commit or push only when your human asks.

## EGM (Elephant-Goldfish Model)

EGM artifact directory: egm/

- EGM drafts and reports go in `egm/`. Approved designs go to `docs/designs/<name>.md` and get
  a row in `docs/designs/SITEMAP.md`.
- Each approved design ends with a short **Review history** section: stages run, findings
  accepted and what changed, findings rejected and why, date.
- How to run EGM (Claude Code and Codex): see `docs/EGM_MANUAL.md`.
- Codex reviewers may still receive this file (EGM issue #237), which is another reason to keep
  design assumptions out of it.
