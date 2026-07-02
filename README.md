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

```sh
reaper harvest https://github.com/Textualize/rich --pattern "*.md" -o RICH.md
reaper conjure . --sha256 --split-tokens 100000 -o PACKED.md
reaper reanimate PACKED.md --out risen/ --verify
reaper census . --format csv | head
reaper unfinished . --age
reaper cast nightly-pack
reaper tree . --format json | jq .file_count
reaper banish --older-than 7d
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

The version comes from git tags (`hatch-vcs`); there is nothing to bump.
Publishing a GitHub release for a `vX.Y.Z` tag builds and uploads to PyPI
via trusted publishing, and docs deploy to GitHub Pages on every push to
`main`.

## License

MIT. Rest in peace.
