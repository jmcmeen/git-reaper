#!/usr/bin/env bash
# ci-gate.sh — the one-line repo-health gate, ready to paste into CI.
#
# `reaper ward` folds the [ward] policy from .reaperrc (or [tool.reaper]
# in pyproject.toml) into a single pass/fail: secrets, risk thresholds,
# rot, dependency advisories, skill freshness — whatever is inscribed.
# With no policy at all it still gates committed secrets.
#
# Every gating ritual uses the same convention: exit 3 when the gate
# breaks, so CI needs exactly one line.
#
# Usage:
#   ./ci-gate.sh [SOURCE]
#
# Example policy, in .reaperrc at the repo root:
#
#   [ward]
#   exhume = "any"      # any committed secret breaks the ward
#   omens = 0.85        # any file scoring >= 0.85 breaks it
#   rot = "730d"        # files untouched past two years break it
set -euo pipefail

SOURCE="${1:-.}"
REAPER="${REAPER:-reaper}"   # REAPER="uv run reaper" to run from a checkout

# The whole gate. In a CI config this one line is all you need;
# everything below is reporting.
rc=0
$REAPER ward "$SOURCE" || rc=$?

if [ "$rc" -eq 0 ]; then
  echo "the ward holds" >&2
  exit 0
elif [ "$rc" -eq 3 ]; then
  echo "the ward is broken — a gate failed (see the report above)" >&2
else
  echo "ward crashed (exit $rc) — wards fail closed, treat as broken" >&2
fi
exit "$rc"
