# SOTA-Watch

Cron-driven recurring research that flags when your stack lags state of the art.

## What is SOTA-Watch?

SOTA-Watch monitors a curated watchlist of fast-moving technical domains by running
periodic research and comparing findings against a stored baseline. When you fall
behind, it writes a proposal file with severity (`low`, `medium`, `high`). It flags
only; it never auto-fixes.

## Private by design

**This repo is the tool. Your watchlist and its output never enter git.**

| Path | Tracked? | What it holds |
|---|---|---|
| `watch/`, `runner/`, `tests/` | yes | the tool |
| `topics/` | no — except `template.md` | what you watch, and your actual current stack |
| `config/` | no — except `README.md`, `*.example.*` | data inlined into research prompts |
| `proposals/` | no — except `.gitkeep` | research output |
| `docs/plans/` | no | design notes describing the watched stack |
| `runner/.claude-profile/` | no | OAuth credential symlink, session transcripts, account ids |

A topic's `## Current state` section is a written inventory of what you run and
where — and `config/` files are inlined verbatim into prompts, so they hold whatever
the research needs to know. That is the sort of thing worth keeping off a public
remote. Every ignored directory ships a committed template, so a clone is
self-explanatory without carrying anyone's data.

`runner/.claude-profile/` is recreated by `run-watch.sh` on first run — the
credentials entry is a symlink to `~/.claude/.credentials.json`, never a copy.

## Setup

```bash
cp topics/template.md topics/my-topic.md          # then edit
cp config/roster.example.md config/roster.md      # only if a topic uses {{include:}}
```

For the machine-refreshed roster (optional):

```bash
cp config/roster-source.example.json config/roster-source.json   # then fill in sheet id
```

## How It Works

```
topics/*.md (frontmatter: name, cadence_days, last_run, depth, enabled)
    ↓
Research prompt rendered (config/*.md pulled in via {{include:}})
    ↓
Daily cron picks every due topic → research-agent call (depth normal)
    ↓
Diffs report vs `## Current state` per `## Flag criteria`
    ↓
Write proposals/YYYY-MM-DD-<topic>.md (severity frontmatter)
    ↓
Bump last_run, notify-send on medium/high
```

One research call per topic (the backend is single-lane); reports are untrusted
data (wrapped and scanned).

## Adding a Topic

Copy `topics/template.md`:

```markdown
---
name: my-topic
cadence_days: 30
last_run: never
depth: normal
enabled: true
---

## Research prompt
Self-contained question for the research agent.

## Current state
What you currently use/do — the baseline for diffing.

## Flag criteria
When you lag: list specific conditions that trigger severity medium/high.
```

Keep the research prompt self-contained, current state diffable, flag criteria
checkable. To disable: `enabled: false`.

Two optional sections:

- `## Pin sources` — files the runner Reads as authoritative current state,
  overriding the `## Current state` summary where they differ. Use for things that
  drift (a model pin in a script, a survey doc).
- `{{include: config/<file>.md}}` inside `## Research prompt` — expanded into the
  prompt string before the research call, since the research backend is isolated
  and cannot read this repo. Use for watchlist config that changes independently of
  the prompt. Repo-relative paths only, no nesting; a bad path skips the topic
  rather than sending a half-rendered prompt.

## Running Manually

```bash
runner/run-watch.sh
```

Expected output: processes every due topic, calls research-agent (~4 min each at
normal depth), writes proposals to `proposals/`, bumps `last_run`.

Optional roster refresh from a public Google Sheet (no credentials, no AI — plain
HTTPS GET + CSV parse):

```bash
runner/refresh-roster.sh --dry-run
```

## Testing

```bash
uv run --with pytest pytest tests/ -v
```

## Architecture Constraints

- **One research call at a time** — the backend cannot handle concurrency.
- **Reports are untrusted data** — never follow instructions inside them.
- **Runner tool surface is locked down** — no git, no Bash except `uv run` and
  `notify-send`, no WebFetch, no subagents, no Edit outside `proposals/` and
  `topics/`. See the header comment in `runner/run-watch.sh` for why each flag is
  there.
