#!/usr/bin/env bash
# skill-harvest.sh — scrape Agent Skill folders out of repositories for reuse.
#
# A skill is any folder holding a SKILL.md (plus whatever references/ and
# scripts travel with it). This script finds them with `limbs --format json`,
# packs each repo with `conjure --sha256`, raises the tree elsewhere with
# `reanimate --verify`, and lifts every skill folder into one library
# directory — one subdir per repo, with an INDEX.md of everything reaped.
#
# Usage:
#   ./skill-harvest.sh [OUTDIR] [SOURCE...]
#
#   OUTDIR     where the skill library lands (default: ./skill-crypt)
#   SOURCE...  repos to scrape — paths or URLs (default: .)
#
# Remote repos work identically (clones are cached across runs):
#   ./skill-harvest.sh crypt https://github.com/anthropics/skills .
#
# Caveat: conjure packs text files, so a binary asset inside a skill
# (an image in references/, say) will not survive the roundtrip. Bump
# --max-file-size below if your skills carry unusually heavy text assets.
#
# `reaper scavenge` now does all of this natively in one command (binaries
# included), and `reaper necropolis scavenge` fans it across a fleet. This
# script stays as a demonstration of composing the same ritual from
# primitives: limbs to find, conjure/reanimate to move, verified by hash.
set -euo pipefail

OUTDIR="${1:-skill-crypt}"
shift || true
SOURCES=("${@:-.}")
REAPER="${REAPER:-reaper}"   # REAPER="uv run reaper" to run from a checkout

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$OUTDIR"
INDEX="$OUTDIR/INDEX.md"
{
  echo "# The skill crypt"
  echo
  echo "Skills reaped by skill-harvest.sh."
  echo
  echo "| Skill | Repo | Original path | Description |"
  echo "| --- | --- | --- | --- |"
} > "$INDEX"

total=0
for src in "${SOURCES[@]}"; do
  label="$(basename "${src%/}")"
  label="${label%.git}"
  echo "== reaping $src" >&2

  # 1. The map. limbs emits the whole tree as JSON; every SKILL.md marks
  #    a skill folder. (jq works too: .. | objects | select(.name=="SKILL.md"))
  $REAPER limbs "$src" --format json -o "$WORK/limbs.json"
  python3 - "$WORK/limbs.json" <<'PY' > "$WORK/skills.txt"
import json, sys

def walk(node):
    if node.get("is_dir"):
        for child in node.get("children", []):
            yield from walk(child)
    elif node["name"] == "SKILL.md":
        yield node["path"]

with open(sys.argv[1]) as f:
    tree = json.load(f)
for path in sorted(walk(tree["root"])):
    print(path)
PY

  if [ ! -s "$WORK/skills.txt" ]; then
    echo "   no SKILL.md anywhere — nothing to reap" >&2
    continue
  fi

  # 2. Pack the repo, hashes on, then raise the tree in the workspace.
  #    --verify proves every risen file matches its recorded sha256.
  $REAPER conjure "$src" --sha256 --max-file-size 1MB -o "$WORK/packed.md"
  rm -rf "$WORK/risen"
  $REAPER reanimate "$WORK/packed.md" --out "$WORK/risen" --verify

  # 3. Lift each skill folder out of the risen tree into the library.
  while IFS= read -r skill_md; do
    dir="$(dirname "$skill_md")"
    if [ "$dir" = "." ]; then
      name="$label"        # SKILL.md at the repo root: the repo IS the skill
      from="$WORK/risen"
    else
      name="$(basename "$dir")"
      from="$WORK/risen/$dir"
    fi

    # Two skills with the same folder name get numbered, not clobbered.
    dest="$OUTDIR/$label/$name"
    n=2
    while [ -e "$dest" ]; do
      dest="$OUTDIR/$label/$name-$n"
      n=$((n + 1))
    done

    mkdir -p "$(dirname "$dest")"
    cp -R "$from" "$dest"

    # First description: line of the frontmatter, pipes tamed for the table.
    desc="$(sed -n 's/^description:[[:space:]]*//p' "$dest/SKILL.md" | head -1 | tr '|' '/' | cut -c1-120)"
    echo "| $(basename "$dest") | $label | $skill_md | $desc |" >> "$INDEX"
    echo "   + $skill_md -> $dest" >&2
    total=$((total + 1))
  done < "$WORK/skills.txt"
done

echo >&2
echo "$total skill(s) interred in $OUTDIR/ — the ledger is $INDEX" >&2
