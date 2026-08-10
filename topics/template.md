---
name: my-topic
cadence_days: 30
last_run: never
depth: normal
enabled: true
---

## Research prompt
Self-contained question for the research agent. It runs in an isolated backend
that cannot read this repo, so everything it needs must be in this text.

Optional: pull in local config with an include (repo-relative, no nesting):
{{include: config/roster.md}}

## Current state
What we currently use/do — the baseline the report is diffed against. Write it
so a difference is checkable, not vibes. `UNKNOWN` is allowed and forces a
severity-medium "establish the baseline" proposal on first run.

## Flag criteria
- A specific, checkable condition that means we lag
- Another one — say which severity it implies (medium/high)

## Pin sources
Optional. Files the runner Reads as authoritative current state, overriding
`## Current state` where they differ. Use for things that drift, e.g. a model
pin inside a script. Delete this section if unused.
