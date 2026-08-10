"""Research-prompt rendering: section extraction + `{{include: path}}` expansion.

The research backend runs in an isolated container and cannot read this repo,
so any config a topic depends on (e.g. a watchlist roster) has to be expanded
into the prompt string before the call. Doing it here rather than in the runner
prompt keeps it deterministic and testable.
"""
from __future__ import annotations

import re
from pathlib import Path

from watch.topics import parse_topic

_INCLUDE = re.compile(r"\{\{include:\s*([^{}]+?)\s*\}\}")
_SECTION = "## Research prompt"


def _section_text(body: str, path: Path) -> str:
    lines = body.splitlines()
    try:
        start = lines.index(_SECTION)
    except ValueError:
        raise ValueError(f"{path}: missing '{_SECTION}' section") from None
    out = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        out.append(line)
    text = "\n".join(out).strip()
    if not text:
        raise ValueError(f"{path}: empty '{_SECTION}' section")
    return text


def _read_include(ref: str, repo_root: Path) -> str:
    target = Path(ref)
    if target.is_absolute():
        raise ValueError(f"include must be repo-relative, got {ref!r}")
    resolved = (repo_root / target).resolve()
    root = repo_root.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"include escapes repo root: {ref!r}")
    if not resolved.is_file():
        raise ValueError(f"include not found: {ref!r}")
    text = resolved.read_text()
    if _INCLUDE.search(text):
        raise ValueError(f"nested includes are not supported: {ref!r}")
    return text.strip()


def research_prompt(topic_path: Path, repo_root: Path) -> str:
    """The topic's research-prompt section with every include expanded."""
    text = _section_text(parse_topic(topic_path).body, topic_path)
    return _INCLUDE.sub(lambda m: _read_include(m.group(1), repo_root), text)
