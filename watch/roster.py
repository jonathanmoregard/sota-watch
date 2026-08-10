"""Roster refresh: fetch the AI power-users sheet as CSV, render a canonical
markdown table for ``config/ai-power-users.md``.

Pure functions here — no filesystem, no network side effects at import time,
no git. The runner script drives orchestration and I/O.

Design points:

- **Sheet is publicly viewable via the CSV export URL** — no auth needed. The
  refresh is a plain HTTPS GET, deterministic, testable, and free of any AI /
  MCP dependency.
- **Which sheet is config, not code.** The roster names real people, so the
  sheet id lives in gitignored ``config/roster-source.json`` and is threaded in
  as an argument. Nothing in this module identifies a particular sheet or
  person.
- **``REFRESHED_DATE_PLACEHOLDER`` is a literal string in the rendered output**
  — the refresh wrapper substitutes today's date only *after* deciding the
  content actually changed, so an unchanged sheet does not produce a daily
  no-op commit.
- **Cell parsing preserves items exactly as the sheet has them.** Multi-line
  cells (Additional websites / Things built) join with `` ; `` between items;
  empty cells become `—`. Sheet-side errors are corrected in the topic's
  ``## Current state``, not here — this file is a faithful clone.
"""
from __future__ import annotations

import csv
import io
import re
import urllib.request
from dataclasses import dataclass
from typing import Sequence

REFRESHED_PLACEHOLDER = "REFRESHED_DATE_PLACEHOLDER"


def csv_url(sheet_id: str, gid: str) -> str:
    """Public CSV-export URL for one tab of a Google Sheet."""
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&gid={gid}"
    )


def source_url(sheet_id: str, gid: str) -> str:
    """Human-openable URL for the same tab, recorded in the rendered header."""
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/edit?gid={gid}#gid={gid}"
    )

_EXPECTED_HEADERS = (
    "Name",
    "Current role",
    "Main website",
    "GitHub",
    "Additional websites",
    "Things built",
    "Role / project sources",
)


@dataclass(frozen=True)
class RosterRow:
    name: str
    role: str
    main_website: str
    github: str
    additional_websites: str
    things_built: str


def fetch_csv(url: str, timeout: float = 30.0) -> str:
    """Fetch the sheet's CSV export. Raises ``urllib.error.URLError`` /
    ``HTTPError`` on network or HTTP failure — the caller lets it propagate so
    the systemd unit turns red and OnFailure notifies."""
    req = urllib.request.Request(url, headers={"User-Agent": "sota-watch-refresh/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https URL
        raw = resp.read()
    return raw.decode("utf-8")


def parse_csv(text: str) -> tuple[str | None, list[RosterRow]]:
    """Parse the roster CSV. Returns ``(snapshot_date, rows)``.

    ``snapshot_date`` is extracted from the ``Current role (as of YYYY-MM-DD)``
    header cell — the sheet has no dedicated snapshot-date column in this tab,
    but the "as of" annotation is authored on every edit, so it is a
    reasonable machine-readable marker. Returns ``None`` when the header does
    not carry an annotation.
    """
    reader = csv.reader(io.StringIO(text))
    all_rows = list(reader)
    if not all_rows:
        raise ValueError("empty CSV")
    header = [c.strip() for c in all_rows[0]]
    if len(header) < len(_EXPECTED_HEADERS):
        raise ValueError(f"CSV header too short: {header}")
    for expected, got in zip(_EXPECTED_HEADERS, header):
        if not got.startswith(expected):
            raise ValueError(
                f"CSV header column mismatch: expected {expected!r}, got {got!r}"
            )
    snapshot = _extract_snapshot(header[1])
    rows = []
    for raw in all_rows[1:]:
        # Skip blank rows (some sheets pad with trailing empties).
        if not any(cell.strip() for cell in raw):
            continue
        padded = list(raw) + [""] * (len(_EXPECTED_HEADERS) - len(raw))
        rows.append(
            RosterRow(
                name=padded[0].strip(),
                role=padded[1].strip(),
                main_website=padded[2].strip(),
                github=padded[3].strip(),
                additional_websites=padded[4].strip(),
                things_built=padded[5].strip(),
            )
        )
    return snapshot, rows


_SNAPSHOT_RE = re.compile(r"\(as of (\d{4}-\d{2}-\d{2})\)")


def _extract_snapshot(role_header: str) -> str | None:
    m = _SNAPSHOT_RE.search(role_header)
    return m.group(1) if m else None


def _render_cell(text: str) -> str:
    """Normalise one sheet cell into one markdown table cell.

    - Splits on newlines: sheet cells use `\\n` to separate multiple items.
    - Trims each item, drops empties, joins with `` ; ``.
    - Escapes `|` so the item cannot break the markdown table.
    - Returns `—` for a fully empty cell so the column stays visible.
    """
    items = [item.strip() for item in text.split("\n")]
    items = [item for item in items if item]
    if not items:
        return "—"
    return " ; ".join(item.replace("|", r"\|") for item in items)


def _role_cell(text: str) -> str:
    text = text.strip()
    if not text:
        return "—"
    text = text.rstrip(".")
    return text.replace("|", r"\|")


def render_markdown(
    snapshot_date: str | None,
    rows: Sequence[RosterRow],
    source: str = "",
) -> str:
    """Full contents of the rendered roster file (path set by ``output`` in
    ``config/roster-source.json``).

    Uses ``REFRESHED_PLACEHOLDER`` in the Refreshed line; the wrapper
    substitutes today's date after diffing, so an unchanged sheet produces
    zero diff (and therefore no rewrite)."""
    header = (
        "<!--\n"
        "Machine-refreshed by runner/refresh-roster.sh from the source Google Sheet.\n"
        "Do not hand-edit — changes will be overwritten. Header + table only; any\n"
        "prose context lives in the topic file that includes this one.\n"
        "-->\n"
        "\n"
        f"- Source: {source or 'unknown'}\n"
        f"- Sheet snapshot date: {snapshot_date or 'unknown'}\n"
        f"- Refreshed: {REFRESHED_PLACEHOLDER}\n"
        "\n"
        "| Name | Role | GitHub | Main website | Additional websites | Things built |\n"
        "|---|---|---|---|---|---|\n"
    )
    body_lines = []
    for r in rows:
        cells = [
            _role_cell(r.name),
            _role_cell(r.role),
            _render_cell(r.github),
            _render_cell(r.main_website),
            _render_cell(r.additional_websites),
            _render_cell(r.things_built),
        ]
        body_lines.append("| " + " | ".join(cells) + " |")
    return header + "\n".join(body_lines) + "\n"


_REFRESHED_LINE = re.compile(r"^- Refreshed: .*$", re.MULTILINE)


def strip_refreshed_line(text: str) -> str:
    """Remove the ``- Refreshed: ...`` line so two renders can be compared
    without the daily timestamp producing a spurious diff."""
    return _REFRESHED_LINE.sub("", text)
