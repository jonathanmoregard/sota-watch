"""The runner agent's only executable surface: `python3 -m watch.cli <cmd>`.

run-watch.sh allowlists these exact invocations (not a `uv run*` prefix),
so the agent, whose input includes untrusted research reports, cannot run
arbitrary Python. Topic paths are validated here: only an existing
`topics/<name>.md` file directly inside ./topics (not template.md, not a
symlink out of the directory) is read or written.

    due              JSON list of due topics: [{path, name, depth}, ...]
    prompt <path>    rendered research prompt for one topic
    mark <path>      set the topic's last_run to today
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from watch.prompt import research_prompt
from watch.topics import TEMPLATE_NAME, due_topics, mark_run

TOPICS = Path("topics")


def _topic_path(raw: str) -> Path:
    p = Path(raw)
    if p.is_absolute() or p.parent != TOPICS or p.suffix != ".md" or p.name == TEMPLATE_NAME:
        raise SystemExit(f"watch.cli: refusing topic path {raw!r} (must be topics/<name>.md)")
    topics_dir = TOPICS.resolve()
    resolved = p.resolve()
    if resolved.parent != topics_dir or not resolved.is_file():
        raise SystemExit(f"watch.cli: refusing topic path {raw!r} (missing or escapes topics/)")
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m watch.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("due")
    sub.add_parser("prompt").add_argument("topic")
    sub.add_parser("mark").add_argument("topic")
    args = ap.parse_args(argv)

    if args.cmd == "due":
        ts = due_topics(TOPICS, date.today())
        print(json.dumps([{"path": str(t.path), "name": t.name, "depth": t.depth} for t in ts]))
    elif args.cmd == "prompt":
        print(research_prompt(_topic_path(args.topic), Path(".")))
    elif args.cmd == "mark":
        mark_run(_topic_path(args.topic), date.today())
    return 0


if __name__ == "__main__":
    sys.exit(main())
