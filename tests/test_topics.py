from datetime import date
from pathlib import Path

import pytest

from watch.topics import Topic, parse_topic, due_topics, mark_run

SAMPLE = """---
name: sample-topic
cadence_days: 30
last_run: 2026-06-01
depth: normal
enabled: true
---

## Research prompt
Ask about things.

## Current state
We use X.

## Flag criteria
Flag if Y.
"""


def _write(tmp_path: Path, text: str, name: str = "sample-topic.md") -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def test_parse_topic(tmp_path):
    t = parse_topic(_write(tmp_path, SAMPLE))
    assert t.name == "sample-topic"
    assert t.cadence_days == 30
    assert t.last_run == date(2026, 6, 1)
    assert t.enabled is True
    assert "Ask about things." in t.body


def test_parse_never_run(tmp_path):
    t = parse_topic(_write(tmp_path, SAMPLE.replace("2026-06-01", "never")))
    assert t.last_run is None


def test_due_topics_ordering(tmp_path):
    _write(tmp_path, SAMPLE, "a.md")  # last_run 2026-06-01, cadence 30 -> due
    _write(tmp_path, SAMPLE.replace("sample-topic", "b").replace("2026-06-01", "never"), "b.md")
    _write(tmp_path, SAMPLE.replace("sample-topic", "c").replace("2026-06-01", "2026-07-10"), "c.md")
    _write(tmp_path, SAMPLE.replace("sample-topic", "d").replace("enabled: true", "enabled: false"), "d.md")
    due = due_topics(tmp_path, today=date(2026, 7, 12))
    names = [t.name for t in due]
    assert "b" in names[0:1], "never-run topics come first"
    assert "sample-topic" in names, "overdue topic is due"
    assert "c" not in names, "recently-run topic is not due"
    assert "d" not in names, "disabled topic is never due"


def test_mark_run_updates_frontmatter(tmp_path):
    p = _write(tmp_path, SAMPLE)
    mark_run(p, on=date(2026, 7, 12))
    t = parse_topic(p)
    assert t.last_run == date(2026, 7, 12)
    assert "## Research prompt" in p.read_text(), "body untouched"


def test_parse_rejects_malformed(tmp_path):
    with pytest.raises(ValueError):
        parse_topic(_write(tmp_path, "no frontmatter here"))
