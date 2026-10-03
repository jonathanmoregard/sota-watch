"""watch.cli: the only commands the runner agent may execute.

The runner's Bash allowlist names these exact invocations instead of a
`uv run*` prefix, so the CLI is the security boundary for topic paths:
anything outside topics/*.md must be refused before it is read or written.
"""
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from watch import cli

TOPIC = """---
name: sample-topic
cadence_days: 30
last_run: never
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


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "topics").mkdir()
    (tmp_path / "topics" / "sample-topic.md").write_text(TOPIC)
    (tmp_path / "topics" / "template.md").write_text(TOPIC)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_due_prints_json(repo, capsys):
    assert cli.main(["due"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out == [{"path": "topics/sample-topic.md", "name": "sample-topic", "depth": "normal"}]


def test_prompt_renders(repo, capsys):
    assert cli.main(["prompt", "topics/sample-topic.md"]) == 0
    assert capsys.readouterr().out.strip() == "Ask about things."


def test_mark_updates_last_run(repo):
    assert cli.main(["mark", "topics/sample-topic.md"]) == 0
    text = (repo / "topics" / "sample-topic.md").read_text()
    assert f"last_run: {date.today().isoformat()}" in text


@pytest.mark.parametrize("bad", [
    "../topics/sample-topic.md",
    "topics/../watch/result.py",
    "watch/result.py",
    "runner/run-watch.sh",
    "topics/sample-topic.txt",
    "topics/sub/x.md",
    "topics/template.md",
    "/etc/passwd",
    "topics/missing.md",
])
@pytest.mark.parametrize("cmd", ["prompt", "mark"])
def test_rejects_paths_outside_topics(repo, capsys, cmd, bad):
    with pytest.raises(SystemExit) as e:
        cli.main([cmd, bad])
    assert e.value.code != 0


def test_rejects_symlink_escaping_topics(repo):
    outside = repo / "outside.md"
    outside.write_text(TOPIC)
    (repo / "topics" / "link.md").symlink_to(outside)
    with pytest.raises(SystemExit):
        cli.main(["mark", "topics/link.md"])
    assert "last_run: never" in outside.read_text()


def test_unknown_subcommand_and_extra_args_refused(repo):
    with pytest.raises(SystemExit):
        cli.main(["exec", "print(1)"])
    with pytest.raises(SystemExit):
        cli.main(["due", "extra"])


def test_module_entrypoint(repo):
    """The exact allowlisted shape `python3 -m watch.cli due` works from the repo root."""
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "PYTHONPATH": str(root)}
    r = subprocess.run([sys.executable, "-m", "watch.cli", "due"], cwd=repo,
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)[0]["name"] == "sample-topic"
