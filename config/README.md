# config/

Watchlist config expanded into research prompts via `{{include: config/<file>.md}}`.

**Everything here except this file and `*.example.*` is gitignored.** The research
backend is isolated and cannot read this repo, so whatever a topic needs at
research time gets inlined into the prompt string — which means this directory
holds the substance of what you watch. Keep it local.

## Setup

Copy the templates and fill them in:

```bash
cp config/roster.example.md        config/roster.md
cp config/roster-source.example.json config/roster-source.json
```

## Files

| File | Purpose |
|---|---|
| `roster.example.md` | Shape of a hand-maintained `{{include:}}` config block. |
| `roster-source.example.json` | Source sheet for the machine-refreshed roster (`runner/refresh-roster.sh`). |

`roster-source.json` fields:

- `sheet_id` — Google Sheet ID from the URL (`/spreadsheets/d/<sheet_id>/`).
- `gid` — tab id (`#gid=<gid>`).
- `output` — repo-relative path the rendered table is written to. Must live
  under `config/`, so it is gitignored like everything else here.

The sheet is fetched over its public CSV export URL — no credentials, no OAuth.
If your sheet is not link-viewable the fetch returns HTML and the run fails loud.
