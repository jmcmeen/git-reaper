# Commands

One name per command, no aliases. Each command below accepts the global
options `--plain`/`--no-theme`, `-q`/`--whisper`, and `-v`/`--moan`.

## harvest

Gather files matching a pattern (default `*.md`) from a local path or a
repo URL, and concatenate them into one flat artifact with a provenance
header and per-file dividers.

```sh
reaper harvest .                                   # every *.md, to stdout
reaper harvest . -p "*.py" -p "*.toml" -o CODE.md  # multiple patterns
reaper harvest https://github.com/Textualize/rich --ref main -o RICH.md
reaper harvest . --max-file-size 1MB -x "CHANGELOG.md"
```

Remote sources are cloned shallow into the catacombs cache and reused on
repeat visits. Binary files and files over `--max-file-size` are skipped
with a reason; `--max-total-size` aborts loudly instead of truncating
silently.

## tree

Hierarchical file listing for any folder, git or not.

```sh
reaper tree .                       # ASCII tree, markdown-fenced
reaper tree . --sizes --lines       # annotate files
reaper tree . -d 2 --dirs-only      # shallow, directories only
reaper tree . --format json         # machine-readable
```

## conjure

Bundle a repo into a single LLM-ingestible artifact (schema `conjure/v1`):
provenance block, file tree, then every text file inlined in deterministic
sorted order. Fences are computed to outlast any backtick run in the
content; end markers gain a nonce when the content fakes them. Binary,
non-UTF-8, and over-cap files are skipped with receipts in the artifact.

```sh
reaper conjure . -o PACKED.md
reaper conjure . --sha256 -o PACKED.md          # verifiable hashes
reaper conjure . --split-tokens 100000 -o P.md  # P.part01.md, P.part02.md, ...
reaper conjure https://github.com/Textualize/rich -x "tests/*" -o RICH.md
```

## reanimate

The inverse of `conjure`: rebuild the directory tree from a packed
artifact, closing the loop for LLM editing workflows. Writes to an empty
directory by default (`--force` to overwrite); refuses absolute paths and
`..` segments outright. Feed it all the parts of a sharded artifact.

```sh
reaper reanimate PACKED.md --out risen/
reaper reanimate P.part*.md --out risen/ --verify
```

The property that guards the round trip, tested from birth:
`reanimate(conjure(tree)) == tree`, byte for byte.

## census

File-type census: counts, total and per-extension sizes, line counts,
language breakdown, token estimate. Size a repo before conjuring it.

```sh
reaper census .
reaper census . --format csv > census.csv
reaper census https://github.com/Textualize/rich --format json
```

## unfinished

Scan source for TODO / FIXME / HACK / XXX markers: file, line, text,
author (via git blame when the source is a repo), and `--age` for how
long each marker has haunted the codebase.

```sh
reaper unfinished .
reaper unfinished . --age --format csv
```

## grimoire

Show effective configuration, where each value came from, and the stored
recipes. Configuration layers, weakest first: defaults, `[tool.reaper]`
in pyproject.toml, `.reaperrc` (TOML), environment variables.

```sh
reaper grimoire
reaper grimoire --format json
```

## cast

Run a saved recipe from the grimoire. Extra arguments pass through as
overrides.

```toml
# .reaperrc
[recipes.nightly-pack]
command = "conjure"
args = [".", "--sha256", "--out", "PACKED.md"]
```

```sh
reaper cast nightly-pack
reaper cast nightly-pack --split-tokens 50000   # override at cast time
```

## pulse

Signs-of-life check: git present and version, optional extras installed,
catacombs health, tty/color detection. The first thing to run when a
ritual misbehaves.

```sh
reaper pulse
reaper pulse --format json
```

## banish

Clear the catacombs (the clone cache).

```sh
reaper banish                  # clear everything
reaper banish --older-than 7d  # partial exorcism
```

## The catacombs

Remote clones land in a content-addressed cache:

```text
~/.cache/git-reaper/catacombs/<host>/<owner>/<repo>
```

Local `file://` sources are buried flat as `localhost/<name>-<digest>`:
mirroring a deep source path under the catacombs would breach Windows'
260-char path limit.

Shallow by default (`--depth 1`), reused across runs, cleared by `banish`.
Override the location with the `GIT_REAPER_CACHE` environment variable.

## Ignore rules

The reaper honors, in combination:

1. the repo's own `.gitignore`
2. a project-level `.reaperignore` (same syntax)
3. ad-hoc `--exclude` globs
4. `.git` is always ignored; symlinks are never followed

## Schemas

Every JSON-emitting command publishes its output schema:

```sh
reaper tree --schema
reaper harvest --schema
```

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Rest in peace. Success. |
| 1 | The ritual failed. Unexpected error. |
| 2 | Bad incantation. Usage error. |
| 3 | Cursed. Reserved: the scan succeeded and found what you feared. |

## Plain output

`--plain` (or `--no-theme`) produces clean ASCII; `NO_COLOR` is honored;
non-tty output auto-disables color, animation, and art. Artifacts go to
stdout or `--out`; all narration goes to stderr, so piping is always safe.
