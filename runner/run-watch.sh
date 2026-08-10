#!/usr/bin/env bash
# Locked-down headless SOTA-watch runner.
#
# Hardening notes (per locked-down-headless-agent skill):
#
# --disallowedTools (NOT --tools ""):
#   Live smoke 2026-07-12 proved --tools "" removes tools entirely and
#   --allowedTools cannot resurrect removed tools — the runner ended up
#   with the research MCP but no Read/Write/Bash and politely gave up.
#   So: allowlist auto-approves the minimal set under dontAsk; explicit
#   denies close the dangerous surface (web, subagents, skills, edits).
#
# --allowedTools layers on top of --tools "":
#   - Bash(uv run*): scoped to uv run invocations only (due_topics + mark_run).
#   - Bash(notify-send*): desktop notification on medium/high severity only.
#   - No git at all: proposals/ and topics/ are gitignored local state, so
#     there is nothing for the agent to commit. Dropped 2026-08-10 when the
#     watchlist and its output stopped being tracked (README "Private by
#     design") — a git-capable agent with nothing to commit is pure surface.
#   - Read,Glob,Grep: topic file reading and proposal scaffolding.
#   - Write: proposal file output to proposals/.
#   - mcp__research-agent__research: the ONE allowed external call.
#   - ToolSearch: required when MCP tool count is large — lets the agent
#     load deferred tool schemas without which mcp__research-agent__research
#     would be visible by name but uncallable (skill §ToolSearch note).
#
# --mcp-config inline JSON:
#   Provides the research-agent stdio server definition. Needed because
#   --strict-mcp-config (below) suppresses ~/.claude.json MCP inheritance.
#   The 'research-agent-mcp' binary is NixOS-managed and reads all API
#   secrets from agenix at launch — no env vars needed here.
#
# --strict-mcp-config:
#   Only the server in --mcp-config loads; all user/project MCP inheritance
#   is suppressed. Prevents unintended tool surface from other MCP servers
#   (futuresearch, safe-bash, etc.). Draft did not include this; added by skill.
#
# --permission-mode dontAsk:
#   Auto-denies anything not in the explicit allow list. Never use
#   bypassPermissions — it propagates to subagents and cannot be cancelled.
#
# RSI inbox delivery is NOT done by the agent:
#   The agent under dontAsk cannot write outside the repo (--add-dir on
#   the inbox was tried 2026-07-28 and Claude Code still denied the
#   Write). Instead the agent only writes its normal proposals/ files,
#   and the post-run section of THIS wrapper (plain bash, no permission
#   sandbox) derives inbox copies from the medium/high proposals written
#   during the run. See the delivery block after the claude invocation.
#
# No --bare:
#   --bare requires ANTHROPIC_API_KEY and skips OAuth/keychain entirely.
#   This runner uses the user's existing OAuth session (personal/single-user
#   cron). Using --bare would break auth. Draft included --bare; dropped.
#   CLAUDE.md auto-discovery is suppressed instead via:
#     - cd to repo root (not a CLAUDE.md-bearing ancestor directory).
#     - CLAUDE_CODE_DISABLE_CLAUDE_MDS=1
#
# env -i + timeout:
#   Scrubs inherited shell env (SSH agents, other tokens). Exports only
#   what the runner genuinely needs. timeout 7200 caps wall-clock — the
#   runner processes ALL due topics per invocation (one research call
#   each, 3.5-6 min at normal depth), and Persistent=true catch-up after
#   an offline stretch can make every topic due at once. Topics are
#   marked done one at a time, so a timeout only loses the in-flight topic.
#   DBUS_SESSION_BUS_ADDRESS + XDG_RUNTIME_DIR are re-exported because
#   env -i scrubs them and notify-send needs the session bus — without
#   them the medium/high desktop notification fails silently.
#   Draft had no env -i or timeout; added by skill Layer 4.
#
# CLAUDE_CONFIG_DIR isolation:
#   Points to runner/.claude-profile/ — an empty isolated profile.
#   Symlink to user credentials is created on first run (see below).
#   Prevents auto-memory, plugin sync, and stale hook inheritance.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE_DIR="$REPO_ROOT/runner/.claude-profile"

# Create isolated profile on first run.
mkdir -p "$PROFILE_DIR"

# Symlink credentials so OAuth token refreshes work from the isolated profile.
if [ ! -e "$PROFILE_DIR/.credentials.json" ]; then
  ln -sf "$HOME/.claude/.credentials.json" "$PROFILE_DIR/.credentials.json"
fi

# Minimal settings for isolated profile: dontAsk default, no background tasks.
if [ ! -f "$PROFILE_DIR/settings.json" ]; then
  cat > "$PROFILE_DIR/settings.json" <<'SETTINGS'
{
  "permissions": {
    "defaultMode": "dontAsk"
  },
  "env": {
    "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
    "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"
  }
}
SETTINGS
fi

# MCP config: only research-agent. --strict-mcp-config enforces this list only.
# The 'research-agent-mcp' binary is on PATH via NixOS profile; it reads
# all API secrets from /run/agenix/* at launch without extra env vars.
MCP_CONFIG='{"mcpServers":{"research-agent":{"type":"stdio","command":"research-agent-mcp","args":[],"env":{}}}}'

REAL_HOME="$HOME"

# cd into repo root BEFORE invoking claude so CLAUDE.md files in parent
# directories are not picked up. (skill: "cd $SCRATCH is mandatory")
cd "$REPO_ROOT"

# Wrapper-context PATH (pre/post sections run OUTSIDE env -i). Under the
# systemd user unit the inherited PATH is narrow; the due-list checks and
# RSI derivation below need uv. The per-user Nix profile is derived from the
# invoking user rather than hardcoded, so this runs as anyone.
RUN_USER="$(id -un)"
BASE_PATH="/etc/profiles/per-user/$RUN_USER/bin:/run/current-system/sw/bin:/usr/bin:/bin"
export PATH="$BASE_PATH:$PATH"

UV_PY=(uv run --project "$REPO_ROOT" python3)

# Due-list snapshot BEFORE the run. The post-run gate compares against
# due_topics() again: any topic still due afterwards was NOT processed —
# a purely programmatic completion check (no reliance on model-printed
# markers). "Skipped because research failed" leaves last_run untouched
# by design, so a degraded research backend also fails the unit and
# triggers the OnFailure notification.
DUE_BEFORE="$("${UV_PY[@]}" -c "from datetime import date; from pathlib import Path; from watch.topics import due_topics; print(len(due_topics(Path('topics'), date.today())))")"

# Epoch stamp: the RSI derivation below only considers proposal files
# modified at/after this instant (i.e. written by THIS run).
RUN_START_EPOCH="$(date +%s)"

# Model fallback list, tried in order until one is not quota-blocked.
# Quotas are per-model: on 2026-07-31 claude-fable-5 returned 429
# "You've hit your org's monthly usage limit" in 589 ms while
# claude-opus-5 and claude-sonnet-5 answered the same trivial prompt
# normally — so a capped preferred model must roll to the next one
# instead of failing the unit for the rest of the month. Only
# classify()=="usage_limit" rolls over; auth failures (401 / not logged
# in) and every other error fail immediately, since no model change can
# fix them. Retrying is safe mid-run too: topics completed by the capped
# attempt are already mark_run, so the retry only picks up
# what is still due.
MODELS=(claude-fable-5 claude-opus-5 claude-sonnet-5)

# No `exec`: the runner's exit code must reflect TASK success, not CLI
# success. `claude -p` exits 0 when the model completes its turn — even
# a turn that did nothing because the research tool was missing
# (observed 2026-07-19..26: is_error:false on every tool-missing run, so
# the systemd unit stayed green and OnFailure never fired). Capture the
# JSON, log it, then derive failure programmatically below.
rc=0
CLASS=error
for i in "${!MODELS[@]}"; do
  MODEL="${MODELS[$i]}"
  rc=0
  OUTPUT="$(env -i \
    HOME="$REAL_HOME" \
    USER="$RUN_USER" \
    LOGNAME="$RUN_USER" \
    PATH="$BASE_PATH" \
    DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}" \
    XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" \
    CLAUDE_CONFIG_DIR="$PROFILE_DIR" \
    CLAUDE_CODE_DISABLE_CLAUDE_MDS="1" \
    CLAUDE_CODE_DISABLE_AUTO_MEMORY="1" \
    CLAUDE_CODE_DISABLE_BACKGROUND_TASKS="1" \
    timeout 7200 \
    claude -p "$(cat "$REPO_ROOT/runner/runner-prompt.md")" \
      --model "$MODEL" \
      --mcp-config "$MCP_CONFIG" \
      --strict-mcp-config \
      --permission-mode dontAsk \
      --allowedTools "Read,Glob,Grep,Write,ToolSearch,mcp__research-agent__research,mcp__research-agent__retry_research,Bash(uv run*),Bash(notify-send*)" \
      --disallowedTools "WebFetch,WebSearch,Task,Agent,Skill,Edit,NotebookEdit,EnterWorktree,CronCreate" \
      --max-turns 150 \
      --output-format json)" || rc=$?
  printf '%s\n' "$OUTPUT"
  # Structured classification of the result JSON (last JSON line of
  # stdout) instead of substring-matching. See watch/result.py.
  CLASS="$(printf '%s\n' "$OUTPUT" | "${UV_PY[@]}" -c \
    'import sys; from watch.result import classify; print(classify(sys.stdin.read()))')" \
    || CLASS=error
  if [ "$CLASS" != "usage_limit" ]; then
    break
  fi
  NEXT=$((i + 1))
  if [ "$NEXT" -lt "${#MODELS[@]}" ]; then
    echo "run-watch: $MODEL is quota-blocked — falling back to ${MODELS[$NEXT]}" >&2
  else
    echo "run-watch: $MODEL is quota-blocked and no fallback models remain" >&2
  fi
done
if [ "$rc" -ne 0 ]; then
  echo "run-watch: claude exited rc=$rc (model=$MODEL, class=$CLASS)" >&2
  exit "$rc"
fi
if [ "$CLASS" != "ok" ]; then
  echo "run-watch: claude result classified '$CLASS' (model=$MODEL) — failing unit for OnFailure" >&2
  exit 1
fi

# RSI inbox delivery — derived by this trusted wrapper, not the agent.
# The sandboxed agent cannot write outside the repo (dontAsk denies it;
# --add-dir was tried 2026-07-28 and the Write was still denied), and a
# model-written copy would duplicate authorship anyway. The proposal
# file on disk is the single source of truth: every proposal file
# touched by this run with severity medium/high gets a mechanical
# frontmatter rewrite into the RSI proposals inbox, where the
# SessionStart hook surfaces it. Idempotent: existing inbox files are
# never overwritten.
RSI_INBOX="$REAL_HOME/.claude/recursive-self-improvement/proposals"
if ! "${UV_PY[@]}" - "$REPO_ROOT" "$RSI_INBOX" "$RUN_START_EPOCH" <<'PYEOF'
import re, sys, pathlib
repo, inbox, start = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), float(sys.argv[3])
if not inbox.is_dir():
    print(f"run-watch: RSI inbox {inbox} missing — skipping delivery")
    sys.exit(0)
# A medium/high finding that is researched and written but never
# reaches the inbox is exactly the silent-drop this project exists to
# kill. So: any medium/high proposal from THIS run that fails to
# deliver (malformed frontmatter, non-kebab topic, unreadable bytes)
# makes this block exit nonzero → unit fails → OnFailure notifies.
undelivered = []
for p in sorted((repo / "proposals").glob("*.md")):
    try:
        if p.stat().st_mtime < start:
            continue
        text = p.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as e:
        print(f"run-watch: UNREADABLE {p.name} — {type(e).__name__}")
        undelivered.append(p.name)
        continue
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        continue  # no frontmatter → not a proposal we emit; ignore
    fm, body = m.groups()
    def field(name):
        f = re.search(rf"^{name}:\s*(\S+)\s*$", fm, re.M)
        return f.group(1) if f else None
    sev, topic, date = field("severity"), field("topic"), field("date")
    if sev not in ("medium", "high"):
        continue  # none/low stay repo-only by design
    # SECURITY: topic/date come from model-authored frontmatter whose
    # inputs include untrusted research reports. Without strict shape
    # gates, `topic: ../../skills/evil` would make THIS trusted wrapper
    # write attacker-influenced markdown into the user's agent config
    # (path traversal out of the inbox). Allow only kebab-case topics
    # and ISO dates, then assert the resolved parent is exactly inbox.
    if not topic or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", topic):
        print(f"run-watch: UNDELIVERED {p.name} — bad topic {topic!r}")
        undelivered.append(p.name)
        continue
    if not date or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date):
        print(f"run-watch: UNDELIVERED {p.name} — bad date {date!r}")
        undelivered.append(p.name)
        continue
    dst = inbox / f"{date}-sota-watch-{topic}.md"
    if dst.resolve().parent != inbox.resolve():
        print(f"run-watch: UNDELIVERED {p.name} — path escapes inbox")
        undelivered.append(p.name)
        continue
    if dst.exists():
        continue  # idempotent: already delivered on a prior run
    dst.write_text(
        f"---\nstatus: pending\ncategory: automation\ndate: {date}\nsource: sota-watch\n---\n{body}"
    )
    print(f"run-watch: delivered {dst.name} to RSI inbox (severity={sev})")
if undelivered:
    print(f"run-watch: {len(undelivered)} medium/high proposal(s) NOT delivered: {undelivered}")
    sys.exit(1)
PYEOF
then
  echo "run-watch: RSI delivery reported undelivered medium/high proposals — failing unit for OnFailure" >&2
  exit 1
fi

# Programmatic completion gate: if any topic is still due, the run did
# not finish its job (tool missing, research degraded, model gave up,
# max-turns clipped — all collapse to this one observable). Compare to
# zero, not DUE_BEFORE: a topic crossing its cadence boundary mid-run
# would fail loud, which is the correct direction. Empty due list at
# start trivially passes.
DUE_AFTER="$("${UV_PY[@]}" -c "from datetime import date; from pathlib import Path; from watch.topics import due_topics; print(len(due_topics(Path('topics'), date.today())))")"
if [ "$DUE_AFTER" -ne 0 ]; then
  echo "run-watch: $DUE_AFTER of $DUE_BEFORE due topics still unprocessed — failing unit for OnFailure" >&2
  exit 1
fi
exit 0
