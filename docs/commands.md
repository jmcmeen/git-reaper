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

## limbs

Hierarchical file listing (the tree, limb by limb) for any folder, git or not.

```sh
reaper limbs .                       # ASCII tree, markdown-fenced
reaper limbs . --sizes --lines       # annotate files
reaper limbs . -d 2 --dirs-only      # shallow, directories only
reaper limbs . --format json         # machine-readable
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

## Dark arts

Security and risk mining. `exhume` and `veil` share one rules engine
(`core/rules.py`): regex signatures plus a Shannon-entropy sweep, extended by
`[rules.<name>]` tables in the grimoire. Neither ever writes a full secret to
any output, log, or error message -- a found secret appears only masked, as
`AKIA...MNOP`.

### exhume

Scan the full history (every reachable blob) for committed secrets. Reports
the commit, path, rule, and a masked preview. `--baseline FILE` suppresses
known findings (a JSON list of fingerprints, or a previous `--format json`
report). `--fail-on {any,high}` gates CI with exit 3.

```sh
reaper exhume .                              # report, exit 0
reaper exhume . --fail-on any                # one-line CI gate (exit 3)
reaper exhume . --baseline known.json --fail-on high
reaper exhume . --no-entropy --format html -o secrets.html
```

### veil

Scrub secrets and configured patterns from any artifact before it leaves the
crypt, replacing each match with `[VEILED:rule-name]`. Reads a file or stdin
(`-`). Also available inline as `conjure --veil`.

```sh
reaper conjure . -o PACKED.md
reaper veil PACKED.md -o SAFE.md --report md   # veiled artifact + a receipt
cat secrets.log | reaper veil -                # scrub a stream
```

### omens

Composite risk prophecy per file: a weighted blend of churn, bug-fix commit
density, recency, and size, each normalized to 0..1. Lenses isolate one
component; weights live in the grimoire's `[omens]` table. Omens are hints,
not fate.

```sh
reaper omens .                       # the full blend, ranked
reaper omens . --lens churn -n 20    # one lens, top 20
reaper omens . --fail-over 0.8       # exit 3 if any file scores >= 0.8
reaper omens . --format html -o risk.html
```

```toml
# .reaperrc -- tune the blend (defaults shown)
[omens]
churn = 0.35
bugs = 0.30
age = 0.20
size = 0.15
```

### doppelgangers

Find duplicate files by content hash. Reports clusters and reclaimable space.
Empty files are convention, not waste, and are ignored by default.

```sh
reaper doppelgangers .
reaper doppelgangers . --min-size 4KB --format json
```

### bloat

The largest files in the working tree and, for repos, the blobs deleted from
the tree but still weighing down `.git` -- the body is still in the walls.

```sh
reaper bloat . -n 30
reaper bloat . --format html -o bloat.html
```

## Deeper necromancy

### bones

Strip implementation, keep structure: every file's imports, class/function
signatures, and docstring first lines. A compact code map that fits huge repos
into small contexts. Python via the stdlib `ast` (zero deps); other languages
need the `git-reaper[bones]` extra (tree-sitter), and are reported as skipped
without it -- never silently dropped.

```sh
reaper bones .
reaper bones . --format json
pip install "git-reaper[bones]"    # adds JS, TS, Go, Rust, Java, C/C++, ...
```

### scry

Compare two refs: total churn, the most-changed files, contributors active in
the range, and which souls appeared for the first time. Reads git's `A..B`
range.

```sh
reaper scry v1.0.0 v2.0.0
reaper scry v1.0.0 HEAD -s . --format html -o release-delta.html
```

### plague

Opt-in and network-using: read dependency manifests (pyproject, requirements,
package.json) and check the exactly-pinned ones against the OSV database.
`--offline` degrades gracefully to manifest parsing only. `--fail-on any`
gates CI with exit 3. This is the only command that ever leaves the crypt.

```sh
reaper plague .                    # consult the OSV oracle
reaper plague . --offline          # parse manifests, never touch the network
reaper plague . --fail-on any      # exit 3 if any affliction is found
```

### necropolis

Fan any source-taking reaper command across every grave in a
`necropolis.toml` manifest (or a GitHub org via `--org` and the `gh` CLI).
Writes a per-grave artifact plus a combined `INDEX.md` that records every
outcome, failures included. A failed grave never stops the fleet.

```sh
reaper necropolis harvest --tag docs --out-dir out/
reaper necropolis exhume --fail-on any --out-dir audit/   # exit 3 if cursed
reaper necropolis census --org my-org --out-dir survey/
```

```toml
# necropolis.toml
[[grave]]
source = "https://github.com/jmcmeen/observa.git"
tags = ["docs"]

[[grave]]
source = "/local/path/to/repo"
name = "beta"
```

## Last rites

### ward

The composite CI gate. A `[ward]` grimoire table folds the
`exhume`/`omens`/`plague`/`rot` thresholds and `distill --check` skill
freshness into one policy; one `reaper ward` exits 3 if any ward breaks. A
check that crashes fails closed. With nothing inscribed, the default policy
gates committed secrets (`exhume = "any"`).

```sh
reaper ward .                      # the whole policy, one exit code
```

```toml
# .reaperrc
[ward]
exhume = "any"                     # or "high", or "off"
omens = 0.85                       # exit 3 when any omen scores this or worse
rot = "730d"                       # exit 3 when files sit untouched past this
skills = ["skills/git-reaper"]     # distill --check freshness, gated
```

### banshee

Watch mode: poll a directory (ignore rules honored) and scream -- re-run a
recipe from the grimoire -- whenever it changes. Portable polling, no new
dependencies. Runs the recipe once at the start, then keeps vigil; ctrl+c
lays her to rest.

```sh
reaper banshee nightly-pack                    # watch ., recast on change
reaper banshee nightly-pack -s docs/ --interval 5 --once
```

### leech

The inverse of harvest for ordinary markdown: drain fenced code blocks back
into files. Blocks the document names (` ```python title=app.py ` or a bare
path info string) keep their name; the rest are numbered by language.
Reanimate's path-traversal guards apply.

```sh
reaper leech TUTORIAL.md --out src/
reaper leech notes.md --lang python            # only the python blocks
cat model-output.md | reaper leech - --out risen/
```

### embalm

Preserve a repo state in a deterministic, provenance-stamped `.tar.gz`:
sorted entries, zeroed ownership, timestamps pinned to the HEAD commit --
byte-identical across runs. A `PROVENANCE` block and `MANIFEST.sha256` ride
at the archive root, and the receipt prints the archive's own sha256.

```sh
reaper embalm . -o snapshot.tar.gz
reaper embalm . -x "*.log" --format json
```

## The number of the bits

### wake

Draft a Keep-a-Changelog section from the commits since the last tag (or
`--since REF`). Conventional-commit prefixes map onto the Keep-a-Changelog
categories, everything else lands under Changed, and a version bump is
suggested (`!` or BREAKING means major). A draft for a human to edit.

```sh
reaper wake .
reaper wake . --since v0.8.0 -o DRAFT.md
```

### lineage

Trace a line's true origin across history with git's pickaxe: every commit
that added or removed the needle (`-S`, or `-G` with `--regex`), plus the
origin -- who first summoned it.

```sh
reaper lineage "def resolve_source" -s .
reaper lineage "MAGIC_\w+" --regex --path src/
```

### possession

The ownership and knowledge map: dominant author per file and per top-level
directory, with the share they hold. One soul holding `--threshold` (default
75%) of a file's commits flags it possessed -- the bus-factor hotspots to
find before they leave. Knowledge, not blame.

```sh
reaper possession . -n 20
reaper possession . --threshold 0.9 --format json
```

### revenant

Track what will not stay buried: files deleted and later re-added (deaths,
rebirths, whether it walks today) and repeat offenders that keep collecting
fix commits (`--fixes` sets the bar).

```sh
reaper revenant .
reaper revenant . --fixes 5
```

### prophecy

Omens extended across time: forecast which files will demand attention next
from heat (decayed activity), momentum (this `--horizon` window vs the one
before it), and fresh fixes. Like omens: hints, not fate.

```sh
reaper prophecy . -n 20
reaper prophecy . --horizon 30 --format json
```

### exorcise

Compose `bloat`'s dead blobs (past `--min-size`) and `exhume`'s findings
into a *safe* history-purge plan: the exact `git filter-repo` and BFG
commands, printed beside the warnings that belong with them. It plans and
prints; it never rewrites history itself.

```sh
reaper exorcise .
reaper exorcise . --min-size 5MB --no-secrets
```

### effigy

Render the repo as a self-contained SVG poster: a contributor
constellation, the witching-hours heatmap, and a directory treemap strip,
with the provenance riding in the SVG's `<desc>`. The portrait of the dead,
suitable for a README or a talk.

```sh
reaper effigy . -o portrait.svg
reaper effigy . --format json          # the measured portrait data
```

## summon (the TUI)

Launch the interactive Textual TUI (needs the `[tui]` extra). A Dracula-themed
cockpit over the same core the CLI drives: pick a source, choose a ritual, tune
its options, reap, preview, and save.

```sh
pip install "git-reaper[tui]"
reaper summon .            # prefill the source
```

- **Rituals**, grouped in the sidebar: *reaping* (limbs, harvest), *packing*
  (conjure, census, unfinished, bones), *necromancy* (chronicle, souls, haunt,
  graveyard, rot, ghosts, tombstone, wake, possession, revenant), *forensics*
  (doppelgangers, bloat), and *dark arts* (exhume, omens, plague, prophecy,
  exorcise, ward). Git-only rituals are marked `*` and gray out when the
  source is a plain folder.
- **Options panel.** Each ritual exposes its flags as widgets: `format`
  (md/json/csv/html), `omens --lens`, `souls --heatmap`, limits, `exhume`'s
  entropy toggle, `plague --offline` (on by default -- no surprise network).
- **Cursed badge.** `exhume`, `omens`, and `plague` show a red badge with the
  finding count when the scan turns up what you feared. Previews stay masked.
- **Themes.** Defaults to `reaper-dracula`; **Ctrl+P** opens the command palette
  to switch to any built-in theme (dracula, nord, gruvbox, ...) live.
- **Keys.** `r` reap - `s` save (extension follows the format) - `c` copy -
  `b` browse for a source - `/` focus source - `m` raw/rendered markdown -
  `?` help - `q` quit.

Commands that need positional arguments (`scry`, `autopsy`, `resurrect`,
`reanimate`, `veil`, `lineage`, `leech`) or that are meta (`grimoire`, `cast`,
`banish`, `banshee`, `pulse`, `necropolis`) stay CLI-only; `embalm` and
`effigy` write artifacts rather than reports and stay CLI-only too.

## commune (the MCP server)

Serve the read-only rituals to agents over the Model Context Protocol (needs
the `[mcp]` extra). A fourth face on the same engine: every analysis ritual in
the TUI's catalog becomes an agent-callable tool whose input schema mirrors
the ritual's options and whose output is the same provenance-stamped JSON the
CLI prints -- plus `autopsy`, `scry`, and `grimoire`, which take extra
arguments.

```sh
pip install "git-reaper[mcp]"
reaper commune .                     # stdio server, read-only, rooted at .
reaper commune --http 127.0.0.1:6666 # shared server for a team
reaper commune . --allow-write       # let a trusted agent resurrect/banish
```

- **Transports.** stdio by default (for local agent clients); streamable HTTP
  with `--http HOST:PORT` for a shared or remote reaper. Off unless asked
  for, consistent with the no-phone-home posture.
- **Rooted.** Local paths must sit under an allowed root (`--root`,
  repeatable; defaults to the launch source) and remote URLs on an allowed
  host (`--host`). An agent cannot point the reaper at arbitrary disk.
- **Read-only by default.** The writing rituals -- `resurrect`, `reanimate`
  (whose target must land inside the allowed roots), and `banish` -- appear
  only with `--allow-write`. `veil` is always available: it scrubs artifact
  text in flight and touches no disk. `plague` is forced to offline manifest
  parsing unless `--allow-network`. `exhume` returns the same masked previews
  it prints anywhere else -- a full secret never crosses the wire.
- **Resources and prompts.** The effective grimoire, tombstone, and census
  are published as MCP resources; `pack-this-repo`, `audit-this-repo`, and
  `explain-this-repo` prompts give an agent a sane default workflow.
- **Config.** A `[commune]` grimoire table (`roots`, `hosts`, `tools`,
  `allow_write`, `allow_network`) ships one blessed server config; flags
  outrank it.

To register with an MCP client, point it at the command -- for example,
`claude mcp add reaper -- reaper commune ~/repos/that-cursed-monolith`.

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
reaper limbs --schema
reaper harvest --schema
reaper exhume --schema
```

Analysis commands add `--format html` for a self-contained, dark-themed
report (no external requests; styles and the only chart -- a CSS bar per
row -- are inline).

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Rest in peace. Success. |
| 1 | The ritual failed. Unexpected error. |
| 2 | Bad incantation. Usage error. |
| 3 | Cursed. The scan succeeded and found what you feared. |

Exit 3 is what makes `reaper exhume --fail-on any` a one-line CI gate;
`omens --fail-over`, `plague --fail-on`, a broken `ward`, `distill --check`,
and `necropolis` (when any grave is cursed) share the semantics. When you
want a single gate, wire in `reaper ward` and tune the `[ward]` table.

## Plain output

`--plain` (or `--no-theme`) produces clean ASCII; `NO_COLOR` is honored;
non-tty output auto-disables color, animation, and art. Artifacts go to
stdout or `--out`; all narration goes to stderr, so piping is always safe.
