from pathlib import Path

import pytest

from watch.prompt import research_prompt

TOPIC = """---
name: sample-topic
cadence_days: 30
last_run: never
depth: normal
enabled: true
---

## Research prompt
Ask about these people:
{{include: config/roster.md}}
Cite primary sources.

## Current state
We use X.

## Flag criteria
Flag if Y.
"""


def _repo(tmp_path: Path, topic_text: str = TOPIC, roster: str = "- Ada\n- Grace") -> Path:
    (tmp_path / "topics").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "roster.md").write_text(roster)
    (tmp_path / "topics" / "sample-topic.md").write_text(topic_text)
    return tmp_path / "topics" / "sample-topic.md"


def test_expands_include(tmp_path):
    out = research_prompt(_repo(tmp_path), tmp_path)
    assert "- Ada\n- Grace" in out
    assert "{{include" not in out
    assert out.startswith("Ask about these people:")
    assert out.endswith("Cite primary sources.")


def test_stops_at_next_section(tmp_path):
    out = research_prompt(_repo(tmp_path), tmp_path)
    assert "We use X." not in out
    assert "Flag if Y." not in out


def test_passthrough_without_include(tmp_path):
    topic = TOPIC.replace("{{include: config/roster.md}}\n", "")
    assert research_prompt(_repo(tmp_path, topic), tmp_path) == (
        "Ask about these people:\nCite primary sources."
    )


def test_missing_include_file_raises(tmp_path):
    topic = TOPIC.replace("config/roster.md", "config/gone.md")
    with pytest.raises(ValueError, match="not found"):
        research_prompt(_repo(tmp_path, topic), tmp_path)


def test_traversal_outside_repo_raises(tmp_path):
    topic = TOPIC.replace("config/roster.md", "../../etc/passwd")
    with pytest.raises(ValueError, match="escapes repo root"):
        research_prompt(_repo(tmp_path, topic), tmp_path)


def test_absolute_include_raises(tmp_path):
    topic = TOPIC.replace("config/roster.md", "/etc/passwd")
    with pytest.raises(ValueError, match="repo-relative"):
        research_prompt(_repo(tmp_path, topic), tmp_path)


def test_nested_include_raises(tmp_path):
    with pytest.raises(ValueError, match="nested includes"):
        research_prompt(_repo(tmp_path, roster="{{include: config/roster.md}}"), tmp_path)


def test_missing_section_raises(tmp_path):
    topic = TOPIC.replace("## Research prompt", "## Something else")
    with pytest.raises(ValueError, match="missing"):
        research_prompt(_repo(tmp_path, topic), tmp_path)


def test_empty_section_raises(tmp_path):
    topic = TOPIC.replace(
        "Ask about these people:\n{{include: config/roster.md}}\nCite primary sources.\n", ""
    )
    with pytest.raises(ValueError, match="empty"):
        research_prompt(_repo(tmp_path, topic), tmp_path)
