"""Static guard on the runner agent's tool surface in runner/run-watch.sh.

Research reports are attacker-influenced text. The agent must not get a
general code-execution primitive (`Bash(uv run*)` ran arbitrary
`uv run python3 -c ...`) or an unscoped Write that could rewrite the
trusted wrapper/helper code it later executes.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "runner" / "run-watch.sh").read_text()
PROMPT = (ROOT / "runner" / "runner-prompt.md").read_text()


def _allowed() -> list[str]:
    m = re.search(r'--allowedTools "([^"]*)"', SCRIPT)
    assert m, "run-watch.sh must pass --allowedTools"
    return [t.strip() for t in m.group(1).split(",") if t.strip()]


def test_no_open_ended_uv_or_python():
    for rule in _allowed():
        if rule.startswith("Bash("):
            assert rule in {
                "Bash(uv run python3 -m watch.cli due)",
                "Bash(uv run python3 -m watch.cli prompt topics/*)",
                "Bash(uv run python3 -m watch.cli mark topics/*)",
                "Bash(notify-send -u normal *)",
            }, f"unexpected Bash rule {rule!r}"


def test_write_scoped_to_proposals():
    allowed = _allowed()
    assert "Write" not in allowed
    assert "Edit" not in allowed
    assert "Edit(./proposals/*.md)" in allowed


def test_prompt_uses_only_allowlisted_commands():
    cmds = re.findall(r"`(uv run[^`]*)`", PROMPT)
    assert cmds, "runner prompt must name its helper commands"
    for c in cmds:
        assert c.startswith("uv run python3 -m watch.cli "), c
    assert "python3 -c" not in PROMPT
