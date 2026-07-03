---
name: reaper-pack
description: Pack a repository into LLM-ingestible artifacts with git-reaper, and reconstruct trees from them — context-window sharding, verifiable hashes, secret scrubbing, docs harvesting, and code-block extraction. Use when asked to bundle a repo for a model, fit a codebase into a context window, share code as a single file, or rebuild files from a packed artifact or markdown document.
---

git-reaper (`reaper` on PATH; `pip install git-reaper` if missing) packs
repos into clean single-file artifacts and back. All commands take a local
path or remote URL; artifacts go to stdout (or `--out`), narration to stderr.

## Size first, then pack

```sh
reaper census .                                   # token estimate — will it fit?
reaper conjure . --sha256 -o PACKED.md            # tree + every text file, delimited
reaper conjure . --split-tokens 100000 -o PACKED.md   # sharded into context-sized parts
```

`conjure` inlines every text file after a tree overview, honoring
`.gitignore`/`.reaperignore`/`--exclude`, skipping binaries and oversized
files loudly (`--max-file-size`, `--max-total-size` to tune). Flags that
matter:

- `--sha256` records per-file hashes so the unpack can verify fidelity.
- `--split-tokens N` shards into parts of at most N tokens
  (`PACKED.part1.md`, ...). Exact counts need
  `pip install "git-reaper[tokens]"`; otherwise a good estimate is used.
- `--veil` scrubs secrets and configured patterns in flight — use it whenever
  the artifact leaves the machine.

When the full contents are too big even sharded, step down a rung:
`reaper bones .` (imports/signatures/docstrings only) or
`reaper harvest . --pattern "*.md"` (just the docs corpus).

## And back again

```sh
reaper reanimate PACKED.md --out risen/ --verify      # parts welcome: PACKED.part*.md
reaper leech TUTORIAL.md --out src/ --lang python     # fenced code blocks → files
```

- `reanimate` rebuilds the directory tree from a conjured artifact.
  `--verify` checks the per-file sha256 metadata (pack with `--sha256` to
  enable). The target must be empty unless `--force`. Path traversal in
  artifacts is refused outright.
- `leech` is reanimate for ordinary markdown: it drains fenced code blocks
  into files. Blocks naming a path (```` ```python title=app.py ```` or a
  bare-path info string) keep their name; the rest are numbered by language.

## Preservation-grade snapshots

`reaper embalm . -o snapshot.tar.gz` writes a deterministic tarball — sorted
entries, zeroed ownership, timestamps pinned to the HEAD commit — with a
`PROVENANCE` block and `MANIFEST.sha256` inside, and prints the archive's own
sha256. Byte-identical across runs, so the snapshot is citable.

## Ground rules

- Same repo state + same flags = byte-identical artifact (only the
  provenance timestamp moves) — safe to cache and diff.
- Every artifact opens with a provenance header: source, ref/sha, tool
  version, exact invocation.
- Skips are loud, never silent: the artifact records what was omitted and why.
