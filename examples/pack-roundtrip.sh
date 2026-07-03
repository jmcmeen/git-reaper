#!/usr/bin/env bash
# pack-roundtrip.sh — conjure a repo into one artifact, raise it again,
# and prove nothing was lost on the way.
#
# The end-to-end packing workflow: size the repo, pack it with per-file
# hashes, reconstruct the tree elsewhere with verification on, then
# byte-compare every risen file against the original.
#
# Usage:
#   ./pack-roundtrip.sh [SOURCE] [WORKDIR]
#
#   SOURCE   local path to a repo or directory (default: .)
#   WORKDIR  scratch directory for the artifact and the risen tree
#            (default: ./pack-roundtrip)
set -euo pipefail

SOURCE="${1:-.}"
WORKDIR="${2:-pack-roundtrip}"
REAPER="${REAPER:-reaper}"   # REAPER="uv run reaper" to run from a checkout

mkdir -p "$WORKDIR"
ARTIFACT="$WORKDIR/PACKED.md"
RISEN="$WORKDIR/risen"

# 1. Size it first: will it even fit where it is going?
echo "== census ==" >&2
$REAPER census "$SOURCE" --format json \
  | python3 -c 'import json,sys; c=json.load(sys.stdin); print("%s files, ~%s tokens" % (c["total_files"], format(c["token_estimate"], ",")), file=sys.stderr)'

# 2. Pack: tree first, then every text file, with sha256 per file.
#    (--split-tokens 100000 would shard for a context window;
#     --veil would scrub secrets in flight.)
echo "== conjure ==" >&2
$REAPER conjure "$SOURCE" --sha256 -o "$ARTIFACT"

# 3. Raise the tree somewhere else, verifying every hash.
echo "== reanimate ==" >&2
rm -rf "$RISEN"
$REAPER reanimate "$ARTIFACT" --out "$RISEN" --verify >&2

# 4. Trust, then verify again: byte-compare every risen file.
echo "== compare ==" >&2
risen_count=0
while IFS= read -r file; do
  rel="${file#"$RISEN"/}"
  cmp -s "$file" "$SOURCE/$rel" || { echo "MISMATCH: $rel" >&2; exit 1; }
  risen_count=$((risen_count + 1))
done < <(find "$RISEN" -type f)

echo "$risen_count files rose intact, byte for byte" >&2
echo "artifact: $ARTIFACT" >&2
echo "risen tree: $RISEN/" >&2
