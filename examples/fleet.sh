#!/usr/bin/env bash
# fleet.sh — reap a whole fleet of repositories with one command.
#
# `reaper necropolis` fans any source-taking ritual across every grave in
# a necropolis.toml manifest, writing one artifact per repo plus a
# combined INDEX.md. This script writes a small manifest and fans
# `tombstone` out over it; swap in census, exhume, conjure, or any other
# ritual the same way.
#
# Usage:
#   ./fleet.sh [OUTDIR] [SOURCE...]
#
#   OUTDIR     where the per-grave artifacts land (default: ./fleet-report)
#   SOURCE...  repos for the manifest — paths or URLs (default: .)
#
# Remote fleets work identically (clones are cached across runs):
#   ./fleet.sh out https://github.com/tiangolo/typer https://github.com/Textualize/rich
# Or skip the manifest and reap a whole GitHub org (needs the gh CLI):
#   reaper necropolis tombstone --org your-org --out-dir out
set -euo pipefail

OUTDIR="${1:-fleet-report}"
shift || true
SOURCES=("${@:-.}")
REAPER="${REAPER:-reaper}"   # REAPER="uv run reaper" to run from a checkout

MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST"' EXIT

# One [[grave]] per repo. Local paths must be absolute in a temp manifest;
# a real necropolis.toml would live at your fleet's root instead.
for src in "${SOURCES[@]}"; do
  case "$src" in
    http*|git@*) grave="$src" ;;
    *)           grave="$(cd "$src" && pwd)" ;;
  esac
  printf '[[grave]]\nsource = "%s"\n\n' "$grave" >> "$MANIFEST"
done

echo "the manifest:" >&2
cat "$MANIFEST" >&2

# Fan out. A cursed grave (one repo failing) exits 3 after the rest finish.
$REAPER necropolis tombstone --manifest "$MANIFEST" --out-dir "$OUTDIR"

echo >&2
echo "the fleet report:" >&2
ls -1 "$OUTDIR" >&2
