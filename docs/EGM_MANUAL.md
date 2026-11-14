# EGM Quick Manual (HackPrinceton F26)

How our team uses the **Elephant-Goldfish Model (EGM)** plugin during the hackathon. It's short
on purpose: we have about 24 hours, so EGM is used only where a mistake would be expensive.

Plugin: **egm 0.1.1** (Google, Apache-2.0), github.com/google/elephant-goldfish-model.

---

## 1. The idea in one minute

| Role | Who | Knows | Job |
|---|---|---|---|
| **Elephant** | Your main agent session | The whole conversation and project | Drafts the design and fixes it after review |
| **Goldfish** | Fresh reviewer agents | **Only** the document and files it links | Find gaps, hidden assumptions, unclear parts, risks |
| **You** | The human | What matters and why | Make trade-offs, approve the design, decide what gets built |

If a reviewer with no context can understand the design and build from it, the design is
complete. If not, something important exists only in someone's chat and must be written down.
On a team this also means **every teammate's agent can build from the same document.**

---

## 2. Setup

### Claude Code
```sh
claude plugin marketplace add google/elephant-goldfish-model
claude plugin install egm@egm
claude --version     # need 2.1.271 or newer for isolated reviewers
```
Start a new session afterwards. Commands use the `/egm:` prefix and **only the human can start
them** (type them in the chat).

### Codex CLI
```sh
codex plugin marketplace add google/elephant-goldfish-model
codex plugin add egm@egm
```
Start a new session afterwards. In Codex, **pick the EGM skill from the skill picker** (no
`/egm:` prefix). Codex desktop: install the published EGM plugin from the plugin listing.

### Already done in this repo
- `CLAUDE.md` and `AGENTS.md` both contain `EGM artifact directory: egm/`, so drafts and reports
  go to `egm/`, not the repo root.
- `egm/` is **committed** so teammates can see drafts and findings.
- `docs/designs/SITEMAP.md` is the index of approved designs.

---

## 3. The commands we'll use

Shown with the Claude Code prefix. In Codex, choose the same skill name from the picker.

### `/egm:egm-draft`: write the design, one section at a time
Use it when the direction is decided (it is: see `PROJECT_CONTEXT.md`).

1. Claude reads the context you point it to.
2. It drafts section by section and stops after each for **approve / change**:
   Overview & Problem → Technical Plan → Alternatives → Implementation plan (files + checks).
3. Output: `egm/design_draft.md`. When approved it moves to `docs/designs/<name>.md`.

**Type:**
```
/egm:egm-draft Design the MVP described in PROJECT_CONTEXT.md (use it for data and
API details). Scope: only what the 2-minute demo needs. The implementation plan must split work
into pieces that 3-4 people can build in parallel, each with a way to check it works.
```
Give feedback in chat, or edit `egm/design_draft.md` directly / add `<!-- note -->` comments.

### `/egm:egm-review <file>`: fresh-eyes review
```
/egm:egm-review egm/design_draft.md
```
Claude asks for **Goldfish context** (files reviewers may read). Good picks: `docs/DISCUSSION_LOG.md`,
`PROJECT_CONTEXT.md`, and any code the design points to. **Never pass `.env` or keys.**

Then pick a mode:

| Option | Runs | Use it in this hackathon? |
|---|---|---|
| 0. Interactive, all stages | 5 → 9, pausing after each | No, too slow |
| 1. Consolidated report | 5 → 9 in one go | Only if we have slack |
| **2. Feature spec only** | 5 → 8 | **Default pick:** checks the design itself |
| 3. Implementation plan only | 9 | Good second pass right before splitting work |

| Stage | Reviewer | Question |
|---|---|---|
| 5 | Zoom Out | Right problem and scope? Anything simpler? |
| 6 | Comprehension | Can someone with no background follow it? |
| 7 | Design Critic | Are the architecture choices sound? What breaks? |
| 8 | Zoom Out (again) | After fixes, does it still hold together? |
| 9 | Implementation Readiness | Could someone build it from this alone? |

**Expect many findings; that's intended.** Keep what matters for the demo, reject the rest.
Between stages Claude sorts findings (via `egm-resolve`) into: *contest* (reviewer was wrong),
*propose a fix* (you approve), or *negotiate* (you decide the trade-off).

### `/egm:egm-review-loop`: quick custom review
Faster than a full review. Good for the README / Devpost text or a single small design.
```
/egm:egm-review-loop Review README.md, full file. Reviewers: comprehension, style,
structural. Standards: structural -> feature-spec-standard. Goldfish context: none.
```
Reviewers: `zoom_out`, `comprehension`, `design_critic`, `structural`, `style`,
`codebase_details`, `implementation_readiness`.

### `/egm:egm-drift-report docs/designs`: does the code still match the design?
Run once Saturday night or before submitting. It lists only the differences (missing features,
hard-coded values, a different approach). For each one, update the design or the code.
Output: `egm/YYYY-MM-DD_DRIFT_REPORT.md`.

### Skip during the hackathon
- `/egm:egm-brainstorm`: the team is already settled the direction in `PROJECT_CONTEXT.md`.
- `/egm:egm-bootstrap`: per-folder READMEs; not worth it for a 24-hour repo.

---

## 4. Our plan (time-boxed)

| When | Who | Command | Time box |
|---|---|---|---|
| Sat, once a lane needs a design | One person (the "elephant") | `/egm:egm-draft` | ~30 min |
| Right after | Same person | `/egm:egm-review egm/design_draft.md`, **option 2** | ~30 min |
| Then | Team | Approve → move to `docs/designs/`, add to SITEMAP, write Review history | 10 min |
| Build | Everyone | Each teammate's agent builds its piece **from the approved design** | — |
| Before submitting | Anyone | `/egm:egm-drift-report docs/designs` | ~15 min |
| Optional | Anyone | `/egm:egm-review-loop` on README / Devpost text | ~10 min |

**Only one person drives the draft and review**, so there's a single elephant with the full
context. Others keep building prototypes or checking data in the meantime.

---

## 5. Where files go

| What | Where | Committed? |
|---|---|---|
| Drafts, briefs, stage reports, drift reports | `egm/` | Yes (team visibility) |
| Approved designs | `docs/designs/<name>.md` | Yes |
| Design index | `docs/designs/SITEMAP.md` | Yes |
| Keys | `.env` | **Never** |

---

## 6. Rules

- **Humans own decisions.** Rejecting a finding is fine; note why in the Review history.
- **It costs time and tokens.** A full review starts many agents. Stick to the time boxes.
- **No secrets** in designs or reviewer context.
- **Isolation:** if reviewers can't be isolated, EGM stops instead of running a weaker review.
  On Codex, reviewers may still see `AGENTS.md` (EGM issue #237), so keep design assumptions out
  of it.
- **EGM never commits.** Commit approved designs yourself.

---

## 7. Quick reference

```
/egm:egm-draft <what to design>          design, by section   → egm/design_draft.md → docs/designs/
/egm:egm-review <file>                   fresh-eyes review    → egm/*_report.md   (pick option 2)
/egm:egm-resolve                         work through findings (usually automatic)
/egm:egm-review-loop <file + reviewers>  quick custom review
/egm:egm-drift-report docs/designs       code vs. design      → egm/YYYY-MM-DD_DRIFT_REPORT.md
```
Codex: same skill names, chosen from the skill picker.
