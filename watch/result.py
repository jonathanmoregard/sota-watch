"""Classify `claude -p --output-format json` stdout for the runner wrapper.

`claude -p` reports task-level trouble inside the result JSON, so the
wrapper cannot rely on the exit code alone (see run-watch.sh). Three
outcomes matter to it:

  ok           — the turn completed; the completion gate decides the rest.
  usage_limit  — quota exhausted for the model that was asked for. Another
                 model may still have headroom (verified 2026-07-31:
                 claude-fable-5 returned 429 "You've hit your org's monthly
                 usage limit" while claude-opus-5 and claude-sonnet-5 both
                 answered normally), so the wrapper retries down its model
                 list instead of failing the unit.
  error        — anything else, including expired OAuth / not-logged-in.
                 Switching model cannot fix those, so they must NOT consume
                 a fallback attempt.
"""
from __future__ import annotations

import json
import re

_USAGE_LIMIT_TEXT = re.compile(r"usage limit|rate limit", re.I)


def classify(stdout: str) -> str:
    """Return "ok", "usage_limit" or "error" for a runner invocation."""
    lines = [l for l in stdout.splitlines() if l.lstrip().startswith("{")]
    if not lines:
        return "error"
    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError:
        return "error"
    if not isinstance(result, dict):
        return "error"
    if not result.get("is_error"):
        return "ok"
    if result.get("api_error_status") == 429 or _USAGE_LIMIT_TEXT.search(
        str(result.get("result", ""))
    ):
        return "usage_limit"
    return "error"
