#!/usr/bin/env bash
# rite-perform.sh — compose a rite (a named, multi-step ritual chain) and
# run it across one or more repos in a single command.
#
# A rite lives in .reaperrc as an ordered list of steps, each a ritual plus
# its CLI args; `reaper perform` runs every step against every source and
# folds the results into one combined JSON report. This script writes a
# small two-step rite (history, then risk) into a scratch directory — so it
# never touches your real .reaperrc — and performs it.
#
# Usage:
#   ./rite-perform.sh [OUTFILE] [SOURCE...]
#
#   OUTFILE    where the combined JSON report lands (default: ./rite-report.json)
#   SOURCE...  repos to run the rite against — paths or URLs (default: .)
#
# Remote sources and a mix of local/remote both work:
#   ./rite-perform.sh out.json . https://github.com/tiangolo/typer
set -euo pipefail

OUTFILE="${1:-rite-report.json}"
shift || true
SOURCES=("${@:-.}")
REAPER="${REAPER:-reaper}"   # REAPER="uv run reaper" to run from a checkout

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

# Local paths must resolve before we cd into the scratch dir below (a
# relative "." would otherwise mean the scratch dir, not yours).
resolved=()
for src in "${SOURCES[@]}"; do
  case "$src" in
    http*|git@*) resolved+=("$src") ;;
    *)           resolved+=("$(cd "$src" && pwd)") ;;
  esac
done

# {source} is filled in per repo when the rite runs. Both steps must support
# --format json/--out to join a rite (reaper-orchestrate explains why).
cat > "$WORKDIR/.reaperrc" <<'EOF'
[rites.sweep]
description = "history + risk, combined"

[[rites.sweep.steps]]
command = "chronicle"
args = ["{source}", "--changelog"]

[[rites.sweep.steps]]
command = "omens"
args = ["{source}", "-n", "10"]
name = "risk"
EOF

echo "the rite:" >&2
cat "$WORKDIR/.reaperrc" >&2
echo >&2
echo "performing 'sweep' across ${#resolved[@]} source(s) -> $OUTFILE" >&2

(cd "$WORKDIR" && $REAPER perform sweep "${resolved[@]}" --format json) > "$OUTFILE"

# Per-step, per-source pass/fail without a full JSON read.
python3 - "$OUTFILE" <<'PY'
import json, sys

with open(sys.argv[1]) as fh:
    report = json.load(fh)
for outcome in report["outcomes"]:
    fate = "ok" if outcome["ok"] else f"FAILED: {outcome['error']}"
    print(f"  {outcome['source']:<40} {outcome['step']:<12} {fate}", file=sys.stderr)
PY

echo >&2
echo "combined report: $OUTFILE" >&2
