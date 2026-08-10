#!/usr/bin/env bash
# Refresh config/ai-power-users.md from the source Google Sheet.
#
# Zero AI, zero MCP, zero credentials: the sheet is publicly viewable via
# its CSV export URL, so this is a plain HTTPS GET + CSV parse + git commit.
# All logic lives in runner/refresh_roster.py; this wrapper only handles
# environment (CWD, SSL_CERT_FILE) and log rotation.
#
# Exits non-zero on any failure so the systemd unit turns red and the shared
# sota-watch-failure-notify OnFailure notifier fires — same signalling
# contract as run-watch.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# uv-managed Python does not read the NixOS system CA bundle by default; the
# systemd unit runs under `env -i` so we cannot rely on the interactive shell
# env either. Pin the bundle path explicitly. /etc/ssl/certs/ca-bundle.crt is
# provided by the cacert package on NixOS; falling back to
# ca-certificates.crt (Debian/Ubuntu path) keeps the script portable for
# manual runs from other hosts.
if [ -z "${SSL_CERT_FILE:-}" ]; then
  for candidate in /etc/ssl/certs/ca-bundle.crt /etc/ssl/certs/ca-certificates.crt; do
    if [ -r "$candidate" ]; then
      export SSL_CERT_FILE="$candidate"
      break
    fi
  done
fi

exec uv run --project "$REPO_ROOT" python3 -m runner.refresh_roster "$@"
