# AGENTS.md: HackPrinceton F26 team repo

Shared rules for every coding agent on this team (Claude Code, Codex, others). Claude Code
loads this file through `CLAUDE.md`. Keep this file to **stable conventions**: put design
decisions in design documents, not here (see "EGM" below for why).

## Where the plan lives

| File | What it is |
|---|---|
| `PROJECT_CONTEXT.md` | Team working notes: idea, data, tracks, phases, risks. |
| `PROPOSAL.md` | The current project proposal (being written; **will land Sat Nov 14 morning**). |
| `docs/designs/` | **Approved designs.** Build from these. Index: `docs/designs/SITEMAP.md`. |
| `egm/` | EGM drafts and review reports (working files, committed so the team can see them). |
| `legacy-archive/` | Superseded proposals. Background only; don't build from them. |
| `HACKATHON_CONTEXT.md` | Notes on the Ray-Ban Meta glasses SDK (setup, gotchas, reusable code). |
| `F26 Onsite Hacker Packet - Google Docs.pdf` | Official rules, tracks, judging. |

If these files disagree, the newest approved design in `docs/designs/` wins, then
`PROPOSAL.md`, then `PROJECT_CONTEXT.md`. If something is still unclear, ask the human; don't guess.

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
- How to run EGM (Claude Code and Codex): see `EGM_MANUAL.md`.
- Codex reviewers may still receive this file (EGM issue #237), which is another reason to keep
  design assumptions out of it.
