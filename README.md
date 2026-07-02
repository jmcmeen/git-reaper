# git-reaper

> A spooky utility for data mining git repositories (and any folder foolish enough to hold still).

`git-reaper` reaps structured knowledge from repositories: it clones, gathers,
concatenates, and packs the contents of a git repo (or a plain directory) into
clean, portable artifacts. Library first; the CLI is a thin adapter over
`git_reaper.core`.

## Install

```sh
uv tool install git-reaper   # or: pip install git-reaper
```

Both `reaper` and `git-reaper` land on your PATH (the long form is the
fallback if the REAPER DAW already owns the short one).

## Commands

### Reaping and packing

| Command | What it does |
| --- | --- |
| `harvest` | Gather files matching a pattern (default `*.md`) from a path or repo URL and concatenate them into one artifact with a provenance header and per-file dividers. |
| `limbs` | Hierarchical file listing (the tree, limb by limb) as markdown or JSON. Depth limits, dirs-only, sizes, line counts, ignore rules. |
| `conjure` | Bundle a repo into a single LLM-ingestible file: tree first, then every text file inlined with spec'd delimiters. `--sha256` for verifiable hashes, `--split-tokens N` to shard into context-window-sized parts. |
| `reanimate` | The inverse of `conjure`: reconstruct a directory tree from a packed artifact. `--verify` checks per-file hashes; path traversal is refused outright. |
| `census` | File-type census: counts, sizes, line counts, language breakdown, token estimate. Size a repo before packing it. |
| `unfinished` | Scan for TODO / FIXME / HACK / XXX markers, with authors via git blame and `--age` for how long each has haunted. |
| `grimoire` | Show effective configuration, where each value came from, and stored recipes. |
| `cast` | Run a saved recipe from the grimoire instead of retyping nine flags. |
| `pulse` | Signs-of-life check: git present, optional extras, cache health. |
| `banish` | Clear the catacombs (the clone cache). `--older-than 7d` for partial exorcisms. |
| `summon` | Launch the interactive Textual TUI (needs the `[tui]` extra): pick a source and a ritual, watch it reap, preview the artifact, and save it. |

### Git necromancy (history mining)

| Command | What it does |
| --- | --- |
| `chronicle` | Commit history (SHA, author, date, message, churn) to markdown, JSON, or CSV. `--changelog` groups commits by tag. |
| `souls` | Contributor stats: commits, lines added/removed, first/last seen, bus factor. `--heatmap` draws a day-of-week x hour activity grid and flags the repo's witching hour. |
| `haunt` | Code churn and hotspots: files ranked by change frequency and churn, the classic bug-risk proxy. |
| `autopsy <path>` | Deep single-file exam: creation commit, rename history (`--follow`), authors over time, churn, and a blame-based line-age summary. |
| `graveyard` | Every file that ever lived and died: path, date of death, the fatal commit, and its author. |
| `resurrect <path>` | Restore a dead file's last living bytes into the working tree or `--out`. Path traversal is refused outright. |
| `ghosts` | Branch hygiene: branches ranked by abandonment, with merged, gone-upstream, and (past `--than 90d`) stale flags. |
| `rot` | Staleness report: surviving files ranked by how long they have gone untouched. |
| `tombstone` | A stats card for demos and READMEs (born, age, commits, souls, last words, witching hour) as ASCII tombstone art, or JSON. |

History commands need real history, so remote sources are cloned full-depth
(a previously shallow catacombs clone is unshallowed automatically).

### Dark arts (security, risk, and forensics)

| Command | What it does |
| --- | --- |
| `exhume` | Scan the full history for committed secrets (API keys, tokens, private keys) via regex signatures plus entropy. Reports commit, path, rule, and a masked preview, never the full secret. `--baseline` suppresses known findings; `--fail-on {any,high}` gates CI. |
| `veil` | Scrub secrets and configured patterns from any artifact (or stdin) before it leaves the crypt, replacing each match with `[VEILED:rule-name]`. Shares one rules engine with `exhume`; also inline as `conjure --veil`. |
| `omens` | Composite per-file risk prophecy: a weighted blend of churn, bug-fix density, recency, and size. `--lens {churn,bugs,age,all}`, weights configurable in the grimoire. Hints, not fate. |
| `doppelgangers` | Find duplicate files by content hash. Reports clusters and reclaimable space. |
| `bloat` | Largest files in the working tree and, for repos, the blobs deleted from the tree but still weighing down `.git`. |

### Deeper necromancy

| Command | What it does |
| --- | --- |
| `bones` | Strip implementation, keep structure: every file's imports, signatures, and docstrings. Python via `ast`; other languages via the `git-reaper[bones]` (tree-sitter) extra. |
| `scry` | Compare two refs: churn, most-changed files, contributors, and souls first seen in the range. |
| `plague` | Opt-in and network-using: read dependency manifests and check pinned versions against the OSV database. `--offline` parses manifests only. The only command that leaves the crypt. |
| `necropolis` | Fan any source-taking command across every grave in a `necropolis.toml` manifest (or a GitHub `--org`). Per-repo artifacts plus a combined `INDEX.md`. |

Analysis commands add `--format html` for a self-contained, dark-themed
report. `exhume --fail-on`, `omens --fail-over`, `plague --fail-on`, and a
cursed grave in `necropolis` all exit `3` for one-line CI gates.

```sh
reaper harvest https://github.com/Textualize/rich --pattern "*.md" -o RICH.md
reaper conjure . --sha256 --split-tokens 100000 -o PACKED.md
reaper reanimate PACKED.md --out risen/ --verify
reaper census . --format csv | head
reaper unfinished . --age
reaper cast nightly-pack
reaper limbs . --format json | jq .file_count
reaper banish --older-than 7d

reaper chronicle . --changelog
reaper souls . --heatmap
reaper haunt . -n 20 --format json | jq '.hotspots[0]'
reaper autopsy src/git_reaper/cli.py
reaper graveyard . && reaper resurrect old/module.py --out risen/
reaper ghosts . --than 90d
reaper tombstone .

reaper exhume . --fail-on any                 # CI secret gate (exit 3)
reaper conjure . --veil -o SAFE.md            # pack, scrubbing secrets
reaper omens . --lens churn -n 20             # riskiest files first
reaper doppelgangers . && reaper bloat .      # duplicates, then heft
reaper bones . -o MAP.md                      # structure without the flesh
reaper scry v1.0.0 HEAD -o DELTA.md           # what changed between releases
reaper plague . --offline                     # dependency advisories (opt-in net)
reaper necropolis harvest --tag docs --out-dir out/   # fan out over a manifest
reaper haunt . --format html -o hotspots.html # self-contained dark report

reaper summon .            # interactive TUI (pip install "git-reaper[tui]")
```

Recipes live in `.reaperrc` (or `[tool.reaper]` in pyproject.toml), alongside
custom secret rules and tunable omen weights:

```toml
[recipes.nightly-pack]
command = "conjure"
args = [".", "--sha256", "--split-tokens", "100000", "--out", "PACKED.md"]
description = "the whole crypt, sharded for the model"

# extend the exhume/veil engine with your own signatures
[rules.internal-host]
pattern = "[a-z0-9-]+\\.corp\\.example\\.com"
severity = "medium"
veil_only = true   # veil redacts it; exhume does not report it as a secret

# tune the omens blend (defaults shown)
[omens]
churn = 0.35
bugs = 0.30
age = 0.20
size = 0.15
```

## Optional extras

The base install is lean. Heavier machinery lives behind extras:

```sh
pip install "git-reaper[bones]"    # tree-sitter: bones for JS/TS/Go/Rust/Java/...
pip install "git-reaper[tui]"      # textual: the `reaper summon` TUI
pip install "git-reaper[tokens]"   # tiktoken: exact token counts
pip install "git-reaper[git]"      # GitPython backend (GIT_REAPER_BACKEND=gitpython)
pip install "git-reaper[all]"      # everything
```

Third-party "rituals" extend the CLI through the `git_reaper.rituals` entry
point: a package that registers a Typer sub-app appears as `reaper <name>`.

## Behavior you can rely on

- **Artifacts to stdout (or `--out`); narration to stderr.** Piping is always safe.
- **Deterministic output.** Same repo state + same flags = byte-identical
  artifact (only the provenance timestamp moves).
- **Provenance by default.** Every artifact opens with source, ref/sha,
  timestamp, tool version, and the exact invocation.
- **Ignore rules honored.** `.gitignore` + `.reaperignore` + `--exclude`
  globs; `.git` is never reaped.
- **Caps with receipts.** Size caps and binary detection skip files loudly,
  never silently.
- **The catacombs.** Remote clones cache under
  `~/.cache/git-reaper/catacombs/<host>/<owner>/<repo>`, shallow, reused
  across runs. Local `file://` sources are buried flat
  (`localhost/<name>-<digest>`) to stay inside Windows path limits.
- **Published schemas.** Every JSON-emitting command prints its JSON schema
  with `--schema`.
- **`--plain` / `NO_COLOR`** produce clean ASCII; non-tty output auto-disables
  the theatrics.
- **No telemetry.** The dead tell no tales.

## Library use

```python
from git_reaper.core.source import resolve_source
from git_reaper.core.harvest import harvest
from git_reaper.formatters.markdown import write_harvest

repo = resolve_source("https://github.com/Textualize/rich").repo
result = harvest(repo, patterns=("*.md",))
with open("RICH.md", "w") as fh:
    write_harvest(result, fh)
```

## Development

Everything runs through `uv` and the Makefile:

```sh
make setup      # create venv, install deps
make check      # lint + typecheck + tests (the full gauntlet)
make fmt        # auto-format and fix lint findings
make test       # pytest
make cov        # pytest with coverage
make docs       # serve the docs locally
make run ARGS="tree ."
make build      # sdist + wheel
```

## License

MIT. Rest in peace.
