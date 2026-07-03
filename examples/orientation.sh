#!/usr/bin/env bash
# orientation.sh — get your bearings in an unfamiliar repository.
#
# Reaps the layout, the census, the structural code map, and the vital
# stats into one report directory: everything you want to read before
# touching a codebase you have never seen.
#
# Usage:
#   ./orientation.sh [SOURCE] [OUTDIR]
#
#   SOURCE  local path or repo URL (default: .)
#   OUTDIR  where the report lands  (default: ./orientation-report)
#
# Works on remote repos too:
#   ./orientation.sh https://github.com/Textualize/rich rich-report
set -euo pipefail

SOURCE="${1:-.}"
OUTDIR="${2:-orientation-report}"
REAPER="${REAPER:-reaper}"   # REAPER="uv run reaper" to run from a checkout

mkdir -p "$OUTDIR"

echo "reaping $SOURCE -> $OUTDIR/" >&2

# The tree, limb by limb: folder layout with sizes and line counts.
$REAPER limbs "$SOURCE" --sizes --lines -o "$OUTDIR/limbs.md"

# How big is this really? Languages, counts, and a token estimate.
$REAPER census "$SOURCE" -o "$OUTDIR/census.md"

# Structure without the flesh: imports, signatures, docstrings.
$REAPER bones "$SOURCE" -o "$OUTDIR/bones.md"

# The vital stats card: born, age, commits, souls, witching hour.
$REAPER tombstone "$SOURCE" -o "$OUTDIR/tombstone.md"

# Who built it, and where the knowledge concentrates.
$REAPER souls "$SOURCE" --heatmap -o "$OUTDIR/souls.md"

# The debt that haunts: TODO/FIXME markers and how long they have lingered.
$REAPER unfinished "$SOURCE" --age -o "$OUTDIR/unfinished.md"

echo >&2
echo "the report:" >&2
ls -1 "$OUTDIR" >&2

# A one-line summary from the census JSON, no jq required.
$REAPER census "$SOURCE" --format json 2>/dev/null \
  | python3 -c 'import json,sys; c=json.load(sys.stdin); print("%s files, ~%s tokens" % (c["total_files"], format(c["token_estimate"], ",")))'
