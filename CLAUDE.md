# CLAUDE.md: HackPrinceton F26 team repo

@AGENTS.md

The shared rules above apply to Claude Code too. Claude-specific notes follow.

## EGM in Claude Code

EGM artifact directory: egm/

- Commands use the `/egm:` prefix, e.g. `/egm:egm-draft`. Only the human can start them.
- EGM reviewer agents run without `CLAUDE.md`. Anything a reviewer must know belongs in the
  design document or in files it links, not here.
- Before a review, `PROJECT_CONTEXT.md` and `docs/DISCUSSION_LOG.md` are good Goldfish context. Never pass
  `.env` or any file containing keys.

## Working style

- Before a phase that changes several files, give a short plan (files, commands, how to check),
  then wait for the go-ahead. Small fixes can go straight ahead.
