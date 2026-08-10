"""CLI: refresh the roster config file from its source Google Sheet.

Which sheet, and where the rendered table lands, come from gitignored
``config/roster-source.json`` (template: ``config/roster-source.example.json``).
Nothing here identifies a particular sheet or person.

Writes only — no git. The rendered file lives under ``config/``, which is
gitignored by design (see README "Private by design"), so committing it is both
impossible and unwanted; the file is local state next to the local topics that
include it.

Exits non-zero on network / parse / config failure so the systemd unit turns red
and the shared OnFailure notifier fires. Prints one status line so the daily
journal is greppable:

  ``refresh-roster: unchanged rows=<N>`` — sheet identical, no write
  ``refresh-roster: updated rows=<N> path=<path>``
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from watch.roster import (
    REFRESHED_PLACEHOLDER,
    csv_url,
    fetch_csv,
    parse_csv,
    render_markdown,
    source_url,
    strip_refreshed_line,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_CONFIG = "config/roster-source.json"


def load_source(repo_root: Path) -> tuple[str, str, Path]:
    """Read ``config/roster-source.json`` → ``(sheet_id, gid, output_path)``.

    ``output`` is constrained to ``config/`` so a bad edit cannot make the
    refresh scribble over source files — and so the rendered roster is always
    covered by the config/ gitignore rule rather than landing somewhere
    committable.
    """
    path = repo_root / SOURCE_CONFIG
    if not path.exists():
        raise SystemExit(
            f"refresh-roster: {SOURCE_CONFIG} not found — "
            f"cp config/roster-source.example.json {SOURCE_CONFIG} and fill it in"
        )
    try:
        cfg = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"refresh-roster: {SOURCE_CONFIG} is not valid JSON — {e}") from None

    missing = [k for k in ("sheet_id", "gid", "output") if not str(cfg.get(k, "")).strip()]
    if missing:
        raise SystemExit(f"refresh-roster: {SOURCE_CONFIG} missing/empty: {', '.join(missing)}")

    out_raw = str(cfg["output"])
    if Path(out_raw).is_absolute():
        raise SystemExit(f"refresh-roster: output must be repo-relative, got {out_raw!r}")
    out = (repo_root / out_raw).resolve()
    config_dir = (repo_root / "config").resolve()
    if out.parent != config_dir:
        raise SystemExit(
            f"refresh-roster: output must sit directly in config/, got {out_raw!r}"
        )
    return str(cfg["sheet_id"]), str(cfg["gid"]), out


def _stamp(text: str, today: date) -> str:
    return text.replace(REFRESHED_PLACEHOLDER, today.isoformat(), 1)


def refresh(today: date | None = None, dry_run: bool = False) -> int:
    """Fetch, parse, render, compare, maybe write. Returns process exit code."""
    today = today or date.today()
    sheet_id, gid, out_path = load_source(REPO_ROOT)

    csv_text = fetch_csv(csv_url(sheet_id, gid))
    snapshot, rows = parse_csv(csv_text)
    new_body = render_markdown(snapshot, rows, source_url(sheet_id, gid))

    old_body = out_path.read_text() if out_path.exists() else ""
    if strip_refreshed_line(old_body) == strip_refreshed_line(new_body):
        print(f"refresh-roster: unchanged rows={len(rows)}")
        return 0

    if dry_run:
        print(f"refresh-roster: would update rows={len(rows)} (dry-run)")
        return 0

    out_path.write_text(_stamp(new_body, today))
    rel = out_path.relative_to(REPO_ROOT)
    print(f"refresh-roster: updated rows={len(rows)} path={rel}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch, render, and diff — but do not write.",
    )
    args = ap.parse_args(argv)
    return refresh(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
