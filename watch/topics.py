"""Topic files: frontmatter parsing, due-selection, last_run updates."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

_FM_DELIM = "---"


@dataclass
class Topic:
    path: Path
    name: str
    cadence_days: int
    last_run: date | None
    depth: str
    enabled: bool
    body: str


def parse_topic(path: Path) -> Topic:
    text = path.read_text()
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FM_DELIM:
        raise ValueError(f"{path}: missing frontmatter")
    try:
        end = lines[1:].index(_FM_DELIM) + 1
    except ValueError:
        raise ValueError(f"{path}: unterminated frontmatter") from None
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            raise ValueError(f"{path}: bad frontmatter line: {line!r}")
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    last_run_raw = fields.get("last_run", "never")
    return Topic(
        path=path,
        name=fields["name"],
        cadence_days=int(fields["cadence_days"]),
        last_run=None if last_run_raw == "never" else date.fromisoformat(last_run_raw),
        depth=fields.get("depth", "normal"),
        enabled=fields.get("enabled", "true") == "true",
        body="\n".join(lines[end + 1:]),
    )


TEMPLATE_NAME = "template.md"


def due_topics(topics_dir: Path, today: date) -> list[Topic]:
    """Enabled topics past their cadence, never-run first, then most-overdue first.

    ``template.md`` is skipped by name. It is the one tracked file in this
    gitignored directory and it parses as a valid never-run topic, so without
    this guard every fresh clone would spend its first research call on the
    template. Skipping by name rather than shipping the template with
    ``enabled: false`` keeps a copied template live immediately — a user who
    fills one in and forgets to flip a flag would otherwise get silence, which
    is the exact failure mode this project exists to catch.
    """
    due = []
    for p in sorted(topics_dir.glob("*.md")):
        if p.name == TEMPLATE_NAME:
            continue
        t = parse_topic(p)
        if not t.enabled:
            continue
        if t.last_run is None or today - t.last_run >= timedelta(days=t.cadence_days):
            due.append(t)
    return sorted(
        due,
        key=lambda t: (t.last_run is not None,
                       t.last_run + timedelta(days=t.cadence_days) if t.last_run else today),
    )


def mark_run(path: Path, on: date) -> None:
    topic = parse_topic(path)  # validates format
    text = path.read_text()
    old = f"last_run: {'never' if topic.last_run is None else topic.last_run.isoformat()}"
    new = f"last_run: {on.isoformat()}"
    if old not in text:
        raise ValueError(f"{path}: cannot find {old!r} to update")
    path.write_text(text.replace(old, new, 1))
