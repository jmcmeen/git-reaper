# Changelog

All notable changes to `git-reaper` are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-02

Deeper Digging. The conjure/reanimate round trip, repo analysis, and the
grimoire.

### Added

#### Commands

- `reaper conjure` - bundle a repo into a single LLM-ingestible artifact
  (schema `conjure/v1`): provenance block, file tree, then every text file
  inlined in deterministic sorted order. Fences are computed to outlast any
  backtick run in the content, end markers gain a nonce when the content
  fakes them, and `--sha256` records per-file hashes. `--split-tokens N`
  shards the output into context-window-sized parts that each repeat the
  provenance block with a `part: i/n` line.
- `reaper reanimate` - the inverse of `conjure`: reconstruct a directory
  tree from a packed artifact (sharded parts welcome). Writes to an empty
  directory by default, `--force` to overwrite, `--verify` to check
  per-file hashes. Absolute paths and `..` segments are refused outright.
  The round trip is property-tested from birth:
  `reanimate(conjure(tree)) == tree`, byte for byte, under adversarial
  contents (nested fences, fake end markers, CRLF, missing final newlines,
  unicode line separators).
- `reaper census` - file-type census: counts, per-extension sizes, line
  counts, language breakdown, and token estimate.
- `reaper unfinished` - scan for TODO / FIXME / HACK / XXX markers with
  file, line, and text; authors come from git blame when the source is a
  repo, and `--age` adds how long each marker has haunted the codebase.
- `reaper grimoire` - show effective configuration, where each value came
  from, and stored recipes. Layers, weakest first: defaults,
  `[tool.reaper]` in pyproject.toml, `.reaperrc` (TOML), environment.
- `reaper cast <recipe>` - run a named recipe from the grimoire; extra
  arguments pass through as overrides.

#### Output and formats

- CSV output (`--format csv`) for `census` and `unfinished`.
- Non-UTF-8 text files are skipped with receipts when conjuring, so the
  packed artifact is exactly reconstructible.

#### Library

- `git_reaper.config`: layered configuration and recipe loading.
- `GitBackend.blame()` on the git backend abstraction.
- Schema strings (`conjure/v1`, ...) and the `--schema` registry now derive
  from one source, `git_reaper.schemas`.

## [0.1.0] - 2026-07-02

The First Harvest. Initial release: the flagship gather-and-concatenate
workflow, folder trees, a health check, and cache management, on top of a
library-first core.

### Added

#### Commands

- `reaper harvest` - gather files matching a pattern (default `*.md`) from a
  local path or remote repo URL and concatenate them into a single artifact
  with a provenance header and per-file dividers.
- `reaper tree` - hierarchical file listing as markdown or JSON, with depth
  limits, dirs-only mode, sizes, line counts, and ignore rules. Works on any
  folder, git or not.
- `reaper pulse` - signs-of-life check: git presence and version, optional
  extras, tty/color detection, cache health.
- `reaper banish` - clear the catacombs (the clone cache), with
  `--older-than 7d` for partial exorcisms.
- `reaper boo` - hidden. You did not read this.

#### Core behavior

- Library-first architecture: all real work lives in `git_reaper.core` and
  returns typed result models; the CLI is a thin presentation layer.
- The catacombs: remote clones cache under
  `~/.cache/git-reaper/catacombs/<host>/<owner>/<repo>`, shallow by default
  and reused across runs. Local `file://` sources are buried flat as
  `localhost/<name>-<digest>` so deep source paths stay inside Windows
  path limits.
- Provenance by default: every artifact opens with source, ref and SHA,
  timestamp, tool version, and the exact invocation used to produce it.
- Deterministic output: same repo state plus same flags yields a
  byte-identical artifact (only the provenance timestamp moves).
- Ignore rules honored: `.gitignore`, `.reaperignore`, and `--exclude` globs;
  `.git` is never reaped.
- Binary detection and per-file size caps, with receipts: skipped files are
  reported loudly, never silently.
- Artifacts go to stdout or `--out`; all themed narration and warnings go to
  stderr, so piping is always safe.

#### Output and formats

- Markdown and JSON formatters.
- Published JSON schemas: every JSON-emitting command prints its schema with
  `--schema`.
- Spooky Rich theming with a shared palette, plus `--plain` / `--no-theme`,
  `NO_COLOR` support, and automatic degradation on non-tty output.

#### Packaging and tooling

- `src/` layout with hatchling build backend and uv lockfile; VCS-derived
  versioning.
- Both `reaper` and `git-reaper` console entry points (the long form is the
  fallback if the REAPER DAW owns the short one).
- Test suite covering the CLI, harvest, tree, ignore matching, cache, and
  schema export; CI workflow; mkdocs documentation site; Makefile.

[Unreleased]: https://github.com/jmcmeen/git-reaper/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/jmcmeen/git-reaper/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jmcmeen/git-reaper/releases/tag/v0.1.0
