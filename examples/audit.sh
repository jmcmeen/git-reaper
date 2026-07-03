#!/usr/bin/env bash
# audit.sh — the full audit sweep: secrets, risk, dependencies, debt.
#
# Runs the dark-arts rituals against a repo, writes every report to a
# directory, and exits non-zero if the secrets gate breaks — so this
# script drops straight into CI.
#
# Usage:
#   ./audit.sh [SOURCE] [OUTDIR]
#
#   SOURCE  local path or repo URL (default: .)
#   OUTDIR  where the reports land (default: ./audit-report)
#
# Environment:
#   ALLOW_NETWORK=1  let plague consult the OSV database (default: offline)
set -euo pipefail

SOURCE="${1:-.}"
OUTDIR="${2:-audit-report}"
REAPER="${REAPER:-reaper}"   # REAPER="uv run reaper" to run from a checkout

mkdir -p "$OUTDIR"
broken=0

echo "auditing $SOURCE -> $OUTDIR/" >&2

# Committed secrets, across the FULL history. Previews stay masked.
# --fail-on any exits 3 on findings; catch it so the sweep finishes.
if ! $REAPER exhume "$SOURCE" --fail-on any -o "$OUTDIR/exhume.md"; then
  echo "!! exhume found committed secrets — see $OUTDIR/exhume.md" >&2
  broken=1
fi

# Composite risk per file: churn + bug density + recency + size.
$REAPER omens "$SOURCE" -n 20 -o "$OUTDIR/omens.md"

# Dependency advisories. Offline parses manifests only; opt in to OSV.
if [ "${ALLOW_NETWORK:-0}" = "1" ]; then
  $REAPER plague "$SOURCE" -o "$OUTDIR/plague.md" || broken=1
else
  $REAPER plague "$SOURCE" --offline -o "$OUTDIR/plague.md"
fi

# The debt ledger: TODO/FIXME/HACK markers and their age.
$REAPER unfinished "$SOURCE" --age -o "$OUTDIR/unfinished.md"

# What keeps coming back: repeat-fix offenders and undead files.
$REAPER revenant "$SOURCE" -o "$OUTDIR/revenant.md"

echo >&2
echo "the reports:" >&2
ls -1 "$OUTDIR" >&2

if [ "$broken" -ne 0 ]; then
  echo "AUDIT FAILED — a gate broke (see above)" >&2
  exit 3
fi
echo "audit clean" >&2
