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
| `distill` | Skill harvesting: read a repo and emit a portable Agent Skill (`SKILL.md` + `reference/`) that teaches a model to work there — conventions, real build/test/lint commands, the structural map, the files that break most, and who to ask (`--anon` for roles). Deterministic, no network, no model calls; `--polish CMD` optionally pipes each draft's prose through your own agent command (stamps and frontmatter protected). `--profile {repo,stack,onboarding}` sets the voice; `--check skills/<name>/` exits 3 when the code has moved past the stamped sha. `necropolis distill` harvests a whole fleet into a skill library with a routing index skill at its root. |
| `unfinished` | Scan for TODO / FIXME / HACK / XXX markers, with authors via git blame and `--age` for how long each has haunted. |
| `leech` | The inverse of harvest for ordinary documents: drain fenced code blocks out of a markdown file back into files. Blocks the document names (` ```python title=app.py ` or a bare path info string) keep their name; the rest are numbered by language. `--lang` filters; reanimate's path-traversal guards apply. |
| `embalm` | Preserve a repo state in a deterministic, provenance-stamped `.tar.gz`: sorted entries, zeroed ownership, every timestamp pinned to the HEAD commit (byte-identical across runs), with a `PROVENANCE` block and a `MANIFEST.sha256` at the archive root. The receipt prints the archive's own sha256, so the snapshot is citable. |
| `grimoire` | Show effective configuration, where each value came from, and stored recipes. |
| `cast` | Run a saved recipe from the grimoire instead of retyping nine flags. |
| `banshee` | Watch mode: poll a directory (ignore rules honored) and scream — re-run a recipe from the grimoire — whenever it changes. `--interval` tunes the poll, `--once` stops after the first scream. Portable polling, no extra dependencies. |
| `pulse` | Signs-of-life check: git present, optional extras, cache health. |
| `banish` | Clear the catacombs (the clone cache). `--older-than 7d` for partial exorcisms. |
| `summon` | Launch the Sanctum, the interactive Textual TUI (needs the `[tui]` extra): a Dracula-themed workbench of chambers reached from a home crypt map. The Altar runs any analysis ritual (options, preview, save, cursed badge); the Grimoire composes recipes visually and inscribes them in `.reaperrc` for `cast`; the Incantation console is an assisted CLI with `/` commands, fuzzy menus, live flag validation, and history; the Necropolis board reaps a whole `necropolis.toml` fleet with per-grave fates; the Reliquary triages `exhume`/`omens`/`plague`/`rot` on one severity-sorted slab; the Séance table pairs the souls heatmap with an hour-by-hour commit explorer and a two-ref scry. Number keys jump chambers, escape returns home, Ctrl+P's palette knows every door and theme. Nothing is TUI-trapped: recipes cast headless and every console line is a real `reaper` invocation. |
| `commune` | Serve the read-only rituals to agents as an MCP server (needs the `[mcp]` extra): every analysis ritual becomes an agent-callable tool returning the same provenance-stamped JSON, over stdio (default) or `--http HOST:PORT`. Rooted to the launch source unless `--root`/`--host` widen the circle; the writing rituals (`resurrect`, `reanimate`, `banish`) appear only with `--allow-write`, `veil` scrubs text in flight, and `plague` stays offline without `--allow-network`. Publishes the grimoire, tombstone, and census as MCP resources plus ready-made audit/pack/explain prompts. |

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
| `wake` | Draft a Keep-a-Changelog section from the commits since the last tag (or `--since REF`). Conventional-commit prefixes map to Added/Fixed/etc., everything else lands under Changed, and a version bump is suggested (`!` means major). A draft for a human to edit, honestly labeled as one. |
| `lineage` | Trace a line's true origin across history with git's pickaxe (`-S`, or `-G` with `--regex`): every commit that added or removed the needle, and who first summoned it. `--path` narrows the dig. |
| `possession` | The ownership and knowledge map: the dominant author per file and per top-level directory, with the share they hold. Files where one soul holds `--threshold` (default 75%) of the commits are flagged possessed — the bus-factor hotspots to find before they leave. |
| `revenant` | Track what will not stay buried: files deleted and later re-added (deaths, rebirths, whether it walks today) and repeat offenders that keep collecting `fix` commits (`--fixes` sets the bar). |
| `effigy` | Render the repo as a self-contained SVG poster: a contributor constellation, the witching-hours heatmap, and a directory treemap strip, stamped with provenance. `--format json` for the raw portrait data. |

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
| `prophecy` | Omens extended across time: forecast which files will demand attention next from heat (decayed activity), momentum (this `--horizon` window vs the one before), and fresh fixes. Like omens: hints, not fate. |
| `exorcise` | Compose `bloat`'s dead blobs and `exhume`'s findings into a *safe* history-purge plan: the exact `git filter-repo` and BFG commands, with the warnings that belong beside them. It plans and prints; it never rewrites history itself. |
| `ward` | The composite CI gate: fold the exhume/omens/plague/rot thresholds and `distill --check` freshness into one `[ward]` policy in the grimoire; one `reaper ward` exits 3 if any ward breaks. A check that crashes fails closed. With nothing inscribed it gates committed secrets (`exhume = "any"`). |

### Deeper necromancy

| Command | What it does |
| --- | --- |
| `bones` | Strip implementation, keep structure: every file's imports, signatures, and docstrings. Python via `ast`; other languages via the `git-reaper[bones]` (tree-sitter) extra. |
| `scry` | Compare two refs: churn, most-changed files, contributors, and souls first seen in the range. |
| `plague` | Opt-in and network-using: read dependency manifests and check pinned versions against the OSV database. `--offline` parses manifests only. The only command that leaves the crypt. |
| `necropolis` | Fan any source-taking command across every grave in a `necropolis.toml` manifest (or a GitHub `--org`). Per-repo artifacts plus a combined `INDEX.md`. |

Analysis commands add `--format html` for a self-contained, dark-themed
report. `exhume --fail-on`, `omens --fail-over`, `plague --fail-on`, a broken
`ward`, and a cursed grave in `necropolis` all exit `3` for one-line CI gates
(`ward` is the one command to wire in when you want a single gate).

```sh
reaper harvest https://github.com/Textualize/rich --pattern "*.md" -o RICH.md
reaper conjure . --sha256 --split-tokens 100000 -o PACKED.md
reaper reanimate PACKED.md --out risen/ --verify
reaper census . --format csv | head
reaper distill . --out skills/git-reaper/     # harvest an Agent Skill
reaper distill --check skills/git-reaper/     # is the skill still true? (exit 3 if stale)
reaper distill . --polish 'claude -p "tighten this skill draft"'  # your model, your key
reaper necropolis distill --org acme --out-dir skills/  # a skill library + routing skill
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

reaper ward .                                 # the whole [ward] policy, exit 3 if broken
reaper banshee nightly-pack                   # re-cast the recipe on every change
reaper leech TUTORIAL.md --out src/           # code blocks back into files
reaper embalm . -o snapshot.tar.gz            # citable, byte-identical archive
reaper wake .                                 # changelog draft since the last tag
reaper lineage "def resolve_source" -s .      # who first summoned this line
reaper possession . --threshold 0.8           # bus-factor hotspots
reaper revenant .                             # what would not stay buried
reaper prophecy . -n 20                       # which files demand attention next
reaper exorcise . --min-size 5MB              # a purge plan (printed, never run)
reaper effigy . -o portrait.svg               # the repo as an SVG poster

reaper summon .            # interactive TUI (pip install "git-reaper[tui]")
reaper commune .           # MCP server over stdio (pip install "git-reaper[mcp]")
reaper commune . --http 127.0.0.1:6666 --root ~/repos   # a shared reaper for a team
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

# bless a team's `commune` MCP server with shared defaults
[commune]
roots = ["~/repos"]
allow_network = true

# tune the omens blend (defaults shown)
[omens]
churn = 0.35
bugs = 0.30
age = 0.20
size = 0.15

# the composite CI gate: one `reaper ward` checks all of it (exit 3 if broken)
[ward]
exhume = "any"        # or "high", or "off"
omens = 0.85          # exit 3 when any omen scores this or worse
rot = "730d"          # exit 3 when files sit untouched past this age
skills = ["skills/git-reaper"]   # distill --check freshness, gated
```

## Optional extras

The base install is lean. Heavier machinery lives behind extras:

```sh
pip install "git-reaper[bones]"    # tree-sitter: bones for JS/TS/Go/Rust/Java/...
pip install "git-reaper[tui]"      # textual: the Dracula `reaper summon` TUI
pip install "git-reaper[tokens]"   # tiktoken: exact token counts
pip install "git-reaper[git]"      # GitPython backend (GIT_REAPER_BACKEND=gitpython)
pip install "git-reaper[pygit2]"   # libgit2 backend (GIT_REAPER_BACKEND=pygit2): the
                                   # performance pass for history-heavy rituals; reads
                                   # run in-process, clone/fetch still use real git
pip install "git-reaper[mcp]"      # the `reaper commune` MCP server
pip install "git-reaper[all]"      # everything
```

Third-party "rituals" extend the CLI through the `git_reaper.rituals` entry
point: a package that registers a Typer sub-app appears as `reaper <name>`.

## Agents, Docker, and examples

Three ready-made ways in, each in its own folder:

- **[docker/](docker/)** — a `Dockerfile` and `docker-compose.yml` that run
  the CLI and the `commune` MCP server in a container:
  `docker compose up -d reaper-mcp` serves every read-only ritual to agents
  at `http://localhost:6666/mcp`, rooted to a mounted `/repos`, guardrails
  engaged. One-off CLI runs share the image:
  `docker compose run --rm reaper tombstone /repos/some-repo`.
- **[skills/](skills/)** — portable Agent Skills that teach a coding agent
  the rituals: `reaper-orient` (map an unfamiliar repo), `reaper-necromancy`
  (history mining), `reaper-audit` (secrets, risk, gating), and
  `reaper-pack` (LLM context packing). Copy a folder into your agent's
  skills directory (for Claude Code, `.claude/skills/`) and it triggers on
  the matching questions. Not to be confused with `reaper distill`, which
  *generates* a repo-specific skill from any codebase.
- **[examples/](examples/)** — scripted end-to-end workflows in plain bash:
  `orientation.sh` (first contact with a repo), `audit.sh` (the full sweep,
  CI-ready exit codes), `pack-roundtrip.sh` (conjure, reanimate `--verify`,
  byte-compare), `ci-gate.sh` (one-line `ward` gate), and `fleet.sh`
  (necropolis fan-out). Each takes a path or remote URL.

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
