# git-reaper

`git-reaper` reaps structured knowledge from repositories: it clones,
gathers, concatenates, and packs the contents of a git repo (or a plain
directory) into clean, portable artifacts. Library first; the CLI is a thin
adapter over `git_reaper.core`.

## Install

```sh
uv tool install git-reaper   # or: pip install git-reaper
```

Both `reaper` and `git-reaper` land on your PATH (the long form is the
fallback if the REAPER DAW already owns the short one).

## Quick start

```sh
# concatenate every markdown file in a repo into one artifact
reaper harvest https://github.com/Textualize/rich -o RICH.md

# map a folder, any folder
reaper tree . --sizes --lines

# pack a repo for a model, then raise it back from the artifact
reaper conjure . --sha256 -o PACKED.md
reaper reanimate PACKED.md --out risen/ --verify

# size the crypt and list the unfinished business
reaper census .
reaper unfinished . --age

# is this thing alive?
reaper pulse
```

## Behavior you can rely on

- **Artifacts to stdout (or `--out`); narration to stderr.** Piping is
  always safe.
- **Deterministic output.** Same repo state + same flags = byte-identical
  artifact (only the provenance timestamp moves).
- **Provenance by default.** Every artifact opens with source, ref/sha,
  timestamp, tool version, and the exact invocation.
- **Ignore rules honored.** `.gitignore` + `.reaperignore` + `--exclude`
  globs; `.git` is never reaped.
- **Caps with receipts.** Size caps and binary detection skip files loudly,
  never silently.
- **Published schemas.** Every JSON-emitting command prints its JSON schema
  with `--schema`.
- **No telemetry.** The dead tell no tales.
