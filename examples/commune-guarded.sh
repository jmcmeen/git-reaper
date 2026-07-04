#!/usr/bin/env bash
# commune-guarded.sh — prove a locked-down reaper MCP server starts clean,
# and print how to connect an agent to it.
#
# `reaper commune` is meant to run as a long-lived server; this script's job
# is to demonstrate the guarded invocation (root-restricted, read-only,
# offline — the posture an agent-facing server should start with) and
# confirm it actually comes up. For a real session, run the printed command
# yourself and leave it running (or drop it into a supervisor / docker
# compose — see docker/README.md).
#
# Usage:
#   ./commune-guarded.sh [SOURCE] [PORT]
#
#   SOURCE  local repo to expose (default: .)
#   PORT    HTTP port (default: 6666)
#
# Needs `pip install "git-reaper[mcp]"`.
set -euo pipefail

SOURCE="${1:-.}"
PORT="${2:-6666}"
REAPER="${REAPER:-reaper}"   # REAPER="uv run reaper" to run from a checkout

SOURCE="$(cd "$SOURCE" && pwd)"   # commune wants an absolute --root
CONNECT="claude mcp add --transport http reaper http://127.0.0.1:$PORT/mcp"

echo "starting: $REAPER commune $SOURCE --root $SOURCE --http 127.0.0.1:$PORT" >&2
echo "guardrails: read-only (no --allow-write), offline (no --allow-network)" >&2

$REAPER commune "$SOURCE" --root "$SOURCE" --http "127.0.0.1:$PORT" &
PID=$!
trap 'kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true' EXIT

# Wait for the port to accept connections. A plain TCP check, not a full MCP
# handshake — that needs a real client, which is the point of this script.
up=0
for _ in $(seq 1 50); do
  if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
    exec 3<&- 3>&-
    up=1
    break
  fi
  sleep 0.1
done

if [ "$up" -ne 1 ]; then
  echo "the server never came up" >&2
  exit 1
fi

echo >&2
echo "up. to actually use it, run the command above yourself and leave it" >&2
echo "running, then connect a client with:" >&2
echo "  $CONNECT" >&2
echo >&2
echo "(this script only proved it starts clean — stopping it now)" >&2
