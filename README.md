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
| `tree` | Hierarchical file listing as markdown or JSON. Depth limits, dirs-only, sizes, line counts, ignore rules. |
| `conjure` | Bundle a repo into a single LLM-ingestible file: tree first, then every text file inlined with spec'd delimiters. `--sha256` for verifiable hashes, `--split-tokens N` to shard into context-window-sized parts. |
| `reanimate` | The inverse of `conjure`: reconstruct a directory tree from a packed artifact. `--verify` checks per-file hashes; path traversal is refused outright. |
| `census` | File-type census: counts, sizes, line counts, language breakdown, token estimate. Size a repo before packing it. |
| `unfinished` | Scan for TODO / FIXME / HACK / XXX markers, with authors via git blame and `--age` for how long each has haunted. |
| `grimoire` | Show effective configuration, where each value came from, and stored recipes. |
| `cast` | Run a saved recipe from the grimoire instead of retyping nine flags. |
| `pulse` | Signs-of-life check: git present, optional extras, cache health. |
| `banish` | Clear the catacombs (the clone cache). `--older-than 7d` for partial exorcisms. |

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

```sh
reaper harvest https://github.com/Textualize/rich --pattern "*.md" -o RICH.md
reaper conjure . --sha256 --split-tokens 100000 -o PACKED.md
reaper reanimate PACKED.md --out risen/ --verify
reaper census . --format csv | head
reaper unfinished . --age
reaper cast nightly-pack
reaper tree . --format json | jq .file_count
reaper banish --older-than 7d

reaper chronicle . --changelog
reaper souls . --heatmap
reaper haunt . -n 20 --format json | jq '.hotspots[0]'
reaper autopsy src/git_reaper/cli.py
reaper graveyard . && reaper resurrect old/module.py --out risen/
reaper ghosts . --than 90d
reaper tombstone .
```

Recipes live in `.reaperrc` (or `[tool.reaper]` in pyproject.toml):

```toml
[recipes.nightly-pack]
command = "conjure"
args = [".", "--sha256", "--split-tokens", "100000", "--out", "PACKED.md"]
description = "the whole crypt, sharded for the model"
```

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
