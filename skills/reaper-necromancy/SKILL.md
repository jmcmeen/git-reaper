---
name: reaper-necromancy
description: Answer who/when/why questions about a repository's git history with git-reaper — authorship, churn, file forensics, deleted code, ownership risk, and release diffs. Use when asked who wrote something, when code changed, why a file keeps breaking, what changed between releases, or to recover deleted files.
---

git-reaper (`reaper` on PATH; `pip install git-reaper` if missing) mines git
history into structured artifacts, replacing long chains of raw `git log`
archaeology. All commands accept a local path or a remote URL (history
commands clone full-depth automatically) and support `--format json` plus
`--schema` for the exact shape. Artifacts print to stdout; narration to
stderr.

## Pick the ritual for the question

| Question | Command |
| --- | --- |
| What happened in this repo, overall? | `reaper chronicle . -n 200 --format json` (`--changelog` groups by tag) |
| Who built this, and is there a bus factor? | `reaper souls . --heatmap` |
| Which files change most (bug-risk proxy)? | `reaper haunt . -n 20 --format json` |
| Everything about one file's life | `reaper autopsy path/to/file.py -s .` — birth commit, renames, authors, churn, blame-based line age |
| Who first added this line/string? | `reaper lineage "def resolve_source" -s .` (pickaxe; `--regex` for git `-G`, `--path` to narrow) |
| Who owns what? Where does knowledge concentrate? | `reaper possession . --threshold 0.8` |
| What changed between two releases? | `reaper scry v1.0.0 HEAD -s . -n 20` |
| What files were deleted, and by whom? | `reaper graveyard . --format json` |
| Bring a deleted file back | `reaper resurrect old/module.py -s . --out risen/` |
| What keeps getting deleted and re-added, or re-fixed? | `reaper revenant . --fixes 3` |
| Which files will demand attention next? | `reaper prophecy . -n 20` (heat + momentum + fresh fixes; hints, not fate) |
| Stale branches to clean up | `reaper ghosts . --than 90d` |
| Files untouched the longest | `reaper rot . -n 20` |
| Draft a changelog since the last tag | `reaper wake .` (or `--since REF`) |

Note the argument shape: `autopsy`, `lineage`, and `resurrect` take their
subject as the positional argument and the repo via `-s/--source`; everything
else takes the source positionally.

## Interpreting results

- `souls` reports bus factor and the "witching hour" (peak commit hour);
  `possession` flags files where one author holds ≥ threshold of commits —
  those are the knowledge-risk hotspots.
- `haunt`, `omens`, and `prophecy` are correlated but different: haunt is raw
  churn ranking, omens blends churn/bug-density/recency/size into one score,
  prophecy extrapolates the trend forward.
- Every JSON artifact carries a `provenance` block (source, sha, invocation);
  cite it so findings are reproducible.
- History rituals need real history: on a shallow clone the tool unshallows
  the cached clone automatically, but a locally truncated repo gives
  truncated answers.
