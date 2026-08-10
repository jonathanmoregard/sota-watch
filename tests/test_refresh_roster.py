"""End-to-end tests for the refresh_roster CLI: config loading and its guards,
idempotent no-op, first-run write, unchanged-sheet skip. Fetch is stubbed —
network belongs in the real run, not the test suite.

No git anywhere: the rendered roster lands in gitignored config/, so the CLI
writes and stops. Fixtures are synthetic; the real roster names real people."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from runner import refresh_roster
from watch.roster import REFRESHED_PLACEHOLDER

CSV = """Name,Current role (as of 2026-07-28),Main website,GitHub,Additional websites,Things built,Role / project sources
Ada Lovelace,Analytical engine programmer,https://ada.invalid/,https://github.com/ada,https://ada.invalid/notes,Note G — https://ada.invalid/noteg,https://ada.invalid/about
"""


def _write_source(root: Path, **over) -> None:
    cfg = {"sheet_id": "SHEET", "gid": "42", "output": "config/roster.md"}
    cfg.update(over)
    (root / "config" / "roster-source.json").write_text(json.dumps(cfg))


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    _write_source(tmp_path)
    monkeypatch.setattr(refresh_roster, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(refresh_roster, "fetch_csv", lambda *_a, **_k: CSV)
    return tmp_path


def _roster(repo: Path) -> Path:
    return repo / "config" / "roster.md"


def test_first_run_writes(repo: Path, capsys: pytest.CaptureFixture[str]):
    assert refresh_roster.refresh(today=date(2026, 8, 2)) == 0
    text = _roster(repo).read_text()
    assert "Refreshed: 2026-08-02" in text
    assert REFRESHED_PLACEHOLDER not in text
    assert "spreadsheets/d/SHEET" in text
    assert "updated rows=1" in capsys.readouterr().out


def test_second_run_with_unchanged_sheet_is_no_op(
    repo: Path, capsys: pytest.CaptureFixture[str]
):
    refresh_roster.refresh(today=date(2026, 8, 2))
    capsys.readouterr()
    assert refresh_roster.refresh(today=date(2026, 8, 3)) == 0
    assert "Refreshed: 2026-08-02" in _roster(repo).read_text()  # date NOT bumped
    assert "unchanged rows=1" in capsys.readouterr().out


def test_changed_sheet_bumps_date(repo: Path, monkeypatch: pytest.MonkeyPatch):
    refresh_roster.refresh(today=date(2026, 8, 2))
    changed = CSV + "Grace Hopper,Compiler pioneer,,,,,,\n"
    monkeypatch.setattr(refresh_roster, "fetch_csv", lambda *_a, **_k: changed)
    assert refresh_roster.refresh(today=date(2026, 8, 3)) == 0
    text = _roster(repo).read_text()
    assert "Refreshed: 2026-08-03" in text
    assert "Grace Hopper" in text


def test_dry_run_never_writes(repo: Path, capsys: pytest.CaptureFixture[str]):
    assert refresh_roster.refresh(today=date(2026, 8, 2), dry_run=True) == 0
    assert not _roster(repo).exists()
    assert "would update" in capsys.readouterr().out


def test_missing_source_config_is_actionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(refresh_roster, "REPO_ROOT", tmp_path)
    # config/ is not in the repo at all, so the error must carry the required
    # JSON shape itself — there is no template file left to point at.
    with pytest.raises(SystemExit, match=r"(?s)not found.*sheet_id.*gid.*output"):
        refresh_roster.refresh(today=date(2026, 8, 2))


def test_malformed_source_config_rejected(repo: Path):
    (repo / "config" / "roster-source.json").write_text("{nope")
    with pytest.raises(SystemExit, match="not valid JSON"):
        refresh_roster.refresh(today=date(2026, 8, 2))


def test_empty_field_rejected(repo: Path):
    _write_source(repo, sheet_id="")
    with pytest.raises(SystemExit, match="missing/empty: sheet_id"):
        refresh_roster.refresh(today=date(2026, 8, 2))


@pytest.mark.parametrize(
    "output",
    ["../escaped.md", "topics/roster.md", "config/nested/roster.md", "/etc/passwd"],
)
def test_output_confined_to_config_dir(repo: Path, output: str):
    """The output path decides whether the rendered roster is covered by the
    config/ gitignore rule — so anything outside config/ is refused."""
    _write_source(repo, output=output)
    with pytest.raises(SystemExit, match="config/|repo-relative"):
        refresh_roster.refresh(today=date(2026, 8, 2))
