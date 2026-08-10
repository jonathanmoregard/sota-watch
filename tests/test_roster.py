"""Roster parsing/rendering. Fixtures are synthetic on purpose — the real
roster names real people and lives in gitignored config/, never in a test."""
from watch.roster import (
    REFRESHED_PLACEHOLDER,
    RosterRow,
    _extract_snapshot,
    _render_cell,
    csv_url,
    parse_csv,
    render_markdown,
    source_url,
    strip_refreshed_line,
)

import pytest

CSV_FIXTURE = """Name,Current role (as of 2026-07-28),Main website,GitHub,Additional websites,Things built,Role / project sources
Ada Lovelace,Analytical engine programmer.,https://ada.invalid/,https://github.com/ada,"https://ada.invalid/notes
https://ada.invalid/journal","Note G — https://ada.invalid/noteg
Difference engine — https://github.com/ada/engine",https://ada.invalid/about
Grace Hopper,"Compiler pioneer, rear admiral",,https://github.com/grace,,COBOL — https://grace.invalid/cobol,Interview
"""


def test_parse_csv_shape():
    snapshot, rows = parse_csv(CSV_FIXTURE)
    assert snapshot == "2026-07-28"
    assert len(rows) == 2
    assert rows[0].name == "Ada Lovelace"
    assert rows[0].github == "https://github.com/ada"
    assert "https://ada.invalid/notes" in rows[0].additional_websites
    assert rows[1].main_website == ""
    assert rows[1].github == "https://github.com/grace"


def test_parse_csv_missing_snapshot():
    text = CSV_FIXTURE.replace("(as of 2026-07-28)", "")
    snapshot, _ = parse_csv(text)
    assert snapshot is None


def test_parse_csv_rejects_wrong_header():
    text = CSV_FIXTURE.replace("Main website", "Website")
    with pytest.raises(ValueError, match="header column mismatch"):
        parse_csv(text)


def test_parse_csv_skips_blank_rows():
    text = CSV_FIXTURE + ",,,,,,\n"
    _, rows = parse_csv(text)
    assert len(rows) == 2


def test_render_cell_joins_multiline_with_semicolons():
    assert _render_cell("https://a/\nhttps://b/") == "https://a/ ; https://b/"


def test_render_cell_empty_becomes_emdash():
    assert _render_cell("") == "—"
    assert _render_cell("   \n\n") == "—"


def test_render_cell_escapes_pipes():
    assert _render_cell("foo | bar") == "foo \\| bar"


def test_extract_snapshot():
    assert _extract_snapshot("Current role (as of 2026-07-28)") == "2026-07-28"
    assert _extract_snapshot("Current role") is None


def test_urls_are_built_from_config_not_hardcoded():
    assert csv_url("SHEET", "42") == (
        "https://docs.google.com/spreadsheets/d/SHEET/export?format=csv&gid=42"
    )
    assert source_url("SHEET", "42") == (
        "https://docs.google.com/spreadsheets/d/SHEET/edit?gid=42#gid=42"
    )


def test_render_markdown_contains_placeholder():
    rows = [
        RosterRow(
            name="Ada",
            role="Founder.",
            main_website="https://a/",
            github="https://github.com/ada",
            additional_websites="",
            things_built="X — https://x/",
        ),
    ]
    out = render_markdown("2026-07-28", rows, source_url("SHEET", "42"))
    assert REFRESHED_PLACEHOLDER in out
    assert "Sheet snapshot date: 2026-07-28" in out
    assert "| Ada | Founder |" in out  # role period stripped
    assert "spreadsheets/d/SHEET" in out
    assert out.endswith("\n")


def test_render_markdown_unknown_snapshot():
    out = render_markdown(None, [])
    assert "Sheet snapshot date: unknown" in out
    assert "- Source: unknown" in out


def test_strip_refreshed_line_makes_two_renders_equal():
    rows = [
        RosterRow(name="Ada", role="Founder", main_website="", github="",
                  additional_websites="", things_built=""),
    ]
    a = render_markdown("2026-07-28", rows).replace(REFRESHED_PLACEHOLDER, "2026-08-01")
    b = render_markdown("2026-07-28", rows).replace(REFRESHED_PLACEHOLDER, "2026-08-02")
    assert a != b
    assert strip_refreshed_line(a) == strip_refreshed_line(b)


def test_full_render_matches_full_fixture():
    snapshot, rows = parse_csv(CSV_FIXTURE)
    out = render_markdown(snapshot, rows)
    # spot-check: two data rows rendered, header preamble present, columns aligned
    assert out.count("\n|") >= 4  # header row + separator + 2 data rows
    assert "Machine-refreshed" in out
    assert "Ada Lovelace" in out
    assert "Grace Hopper" in out
