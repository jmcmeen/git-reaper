# Changelog

All notable changes to `git-reaper` are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.0] - 2026-07-03

Last Rites and the Number of the Bits: the hardening pass and the dream
rituals, landed together.

### Added

- **The ward (`reaper ward`).** The composite CI gate: a `[ward]` grimoire
  table folds the `exhume`/`omens`/`plague`/`rot` thresholds and
  `distill --check` skill freshness into one policy, and one command exits 3
  if any ward breaks. A check that crashes fails closed — a gate that fails
  open is no gate. With nothing inscribed, the default policy gates
  committed secrets (`exhume = "any"`), so it is useful out of the box.
- **The banshee (`reaper banshee <recipe>`).** Watch mode, graduated from
  the crypt now that recipes exist to re-run: a portable polling watcher
  (ignore rules honored, no new dependencies) that screams — re-casts the
  recipe — whenever the watched tree changes. `--interval` tunes the poll,
  `--once` stops after the first scream, ctrl+c lays her to rest.
- **The leech (`reaper leech DOC.md`).** Inverse harvest, graduated from the
  crypt: drain fenced code blocks out of ordinary markdown back into files.
  Blocks the document names (```` ```python title=app.py ```` or a bare
  path info string) keep their name; the rest are numbered by language.
  `--lang` filters, duplicates get suffixes, and reanimate's path-traversal
  guards apply — a document cannot leech itself outside `--out`.
- **Embalming (`reaper embalm`).** A repo state preserved in a
  provenance-stamped `.tar.gz` that is byte-identical across runs: sorted
  entries, zeroed ownership, normalized modes, every timestamp pinned to
  the HEAD commit's author time (the epoch for plain folders), gzip header
  pinned too. A `PROVENANCE` block and `MANIFEST.sha256` ride at the
  archive root, and the receipt prints the archive's own sha256, so a
  snapshot found alone still says exactly what it is. (This also buries the
  old `hex` idea inside embalm, as planned.)
- **The pygit2 backend (`git-reaper[pygit2]`).** The performance pass:
  `GIT_REAPER_BACKEND=pygit2` binds libgit2 directly for the bulk read
  paths — the full log with per-file churn, blob enumeration and reads,
  blame, tags — with no subprocess per call. Network and working-tree
  operations (clone, fetch, checkout) and the per-file log shapes stay
  delegated to real git. Parity tests hold it to byte-identical results,
  including git's Z-suffixed UTC dates, binary numstat, and merge-commit
  semantics. `reaper pulse` reports the extra.
- **The wake (`reaper wake`).** Draft a Keep-a-Changelog section from the
  commits since the last tag (or `--since REF`): conventional-commit
  prefixes map onto Added/Fixed/Removed/Deprecated/Security, everything
  else lands under Changed, and a version bump is suggested (a `!` or
  BREAKING means major). Honestly labeled a draft for a human to edit —
  and dogfooded on this very file.
- **Lineage (`reaper lineage NEEDLE`).** Git's pickaxe with a face: every
  commit that added or removed the needle (`-S`, or `-G` via `--regex`,
  narrowed by `--path`), newest first, plus the origin — who first summoned
  this line. New `pickaxe` method on every git backend.
- **Possession (`reaper possession`).** The ownership and knowledge map:
  dominant author per file and per top-level directory with the share they
  hold, measured from one log pass. One soul holding `--threshold` (default
  75%) of a file's commits flags it possessed — the single points of
  failure to find before they leave. Knowledge, not blame.
- **The revenant (`reaper revenant`).** What will not stay buried: files
  deleted and re-added (deaths, rebirths, whether it walks today, via the
  new `file_events` backend method) and repeat offenders that keep
  collecting fix commits (`--fixes` sets the bar). The honest, git-only
  slice of the long-shelved `zombies` idea.
- **Prophecy (`reaper prophecy`).** Omens extended across time: a forecast
  from heat (exponentially decayed activity), momentum (the `--horizon`
  window against the one before it), and fresh fixes. Framed exactly like
  omens: hints, not fate.
- **Exorcism (`reaper exorcise`).** A *safe* purge plan composed from
  `bloat`'s dead blobs (past `--min-size`) and `exhume`'s findings: the
  exact `git filter-repo` and BFG commands, printed beside the warnings
  that belong with them (rotate the secret first; rewrites have no undo).
  It plans and prints; it never rewrites history itself.
- **The effigy (`reaper effigy`).** The repo as a self-contained SVG
  poster — a contributor constellation, the witching-hours heatmap, and a
  directory treemap strip in the crypt's palette, provenance riding in the
  `<desc>`. The first visual output; `--format json` exposes the measured
  portrait. New `formatters/svgfmt.py`.
- **Schema freeze prep.** A golden-registry test now pins every command's
  result-model fields: renaming or removing a field (or dropping a command)
  fails the build until the artifact schema version is bumped deliberately.
  The v1 lock that Ascension (1.0.0) promises starts enforcing here.
- **TUI: autopsy, lineage, and veil join the ritual catalog.** The Altar,
  the incantation console, and `commune` now cover them — 31 of the CLI's
  42 commands have a TUI surface. Positional rituals carry their argument as a
  text option (autopsy's path, lineage's needle, veil's file; relative veil
  files anchor to the source), and the console learned the CLI's positional
  grammar: `/autopsy PATH [SOURCE]`, `/lineage NEEDLE --regex`, `/veil FILE`.
  The headless twin stays true everywhere — the console's echoed argv and
  the Grimoire's saved recipes emit real CLI invocations (`autopsy PATH -s
  SOURCE`; `veil FILE` takes no source), so `cast` runs them unchanged. The
  necropolis board's fleet Select hides the positional rituals (they want
  per-grave arguments); `commune` keeps its richer dedicated autopsy/veil
  tools and gains `lineage` with a required needle.
- **Docker, Agent Skills, and scripted examples.** Three new top-level
  folders, each documented in the README and on a new "Agents, Docker, and
  examples" docs page. `docker/` runs the CLI and the `commune` MCP server
  in a container (`docker compose up -d reaper-mcp` serves the rituals at
  `http://localhost:6666/mcp`, guardrails engaged, loopback-bound; a `cli`
  profile shares the image for one-off runs). `skills/` ships four portable
  Agent Skills that teach a coding agent the rituals — `reaper-orient`,
  `reaper-necromancy`, `reaper-audit`, and `reaper-pack` — ready to copy
  into `.claude/skills/`. `examples/` holds five runnable bash workflows
  (`orientation.sh`, `audit.sh`, `pack-roundtrip.sh`, `ci-gate.sh`,
  `fleet.sh`), all honoring the stdout/stderr and exit-3 conventions.

### Changed

- The Sanctum, the incantation console, and the `commune` MCP server pick
  up the six source-driven new rituals (`wake`, `possession`, `revenant`,
  `prophecy`, `exorcise`, `ward`) automatically through the shared
  operation registry — the ward's broken circle shows as the cursed badge.
- `necropolis` can fan out `ward` and `embalm` across a fleet; `banshee`
  and `leech` are refused there like the other non-source commands.
- `grimoire` now reports the effective `[ward]` policy and its origin.
- A recipe whose command is `banshee` is refused like `cast` — the
  recursion would never rest.
- **TUI: the footer no longer crowds.** The `1`-`6` chamber bindings still
  jump from anywhere but are hidden from the footer, which used to wrap on
  binding-heavy chambers; the whole bottom line now belongs to each
  chamber's own command keys. The doors stay discoverable on the crypt map
  (escape) and in the Ctrl+P palette.
- The README wears its badges now (ci, docs, PyPI, Python versions,
  license), and every section header carries a suitably creepy emoji.

### Fixed

- **TUI: the Altar's top rows untangled.** Same-edge docked widgets
  superimpose, so the Altar's header sat buried under the source row and
  the source hint painted over the input's top border (a regression during
  0.9.0 development; it never shipped). The top stack is now spelled out:
  header, source row, hint, each on its own line.

## [0.8.0] - 2026-07-03

The Sanctum: one good screen becomes a workbench of chambers.

### Added

- **The Sanctum.** `reaper summon` now opens on a crypt-map home screen
  with six chambers as doors (Textual's Screen API). Chambers keep their
  state while you roam; number keys jump, escape returns to the map, and
  Ctrl+P's palette knows every door alongside the themes. Every chamber
  drives the same `tui_ops` registry and typed core -- still no logic
  outside the library, and nothing done in the Sanctum is TUI-trapped.
- **The Altar.** The original run-a-ritual screen, kept whole: the roomy
  list and `d` toggle, options panel, preview, cursed badge, save.
- **The Grimoire (recipe builder).** Compose a recipe visually with the
  same option widgets the Altar renders, watch the exact CLI invocation
  update live, and save: `config.save_recipe` inscribes it in `.reaperrc`
  with line-level section surgery (comments elsewhere survive), so it
  round-trips with `cast`. Existing recipes load back into the form
  (parsed by the console's own brain) and delete cleanly; pyproject
  recipes are shown but honestly point back at the file they live in.
- **The Incantation console.** A REPL over the rituals: `/` summons a
  fuzzy menu (prefix, substring, then subsequence), the help line
  validates flags as you type, Enter runs the line on a worker thread,
  and up/down recalls history. Every accepted line is a real, reproducible
  `reaper` argv, shown with its artifact. Meta commands: `/help`,
  `/recipes`, `/theme`, `/clear`, `/save`. The parser lives in the new
  textual-free `incant` module, tested without the `[tui]` extra.
- **The Necropolis board.** Load a `necropolis.toml` (the same manifest
  the CLI fans out over), pick a ritual, reap the fleet: per-grave fates
  update live (rest in peace / CURSED / the plain failure), and selecting
  a row drops that grave's artifact into the preview.
- **The Reliquary.** One triage pass unifying `exhume`, `omens`, `plague`
  (offline), and `rot`, merged onto one slab sorted most-cursed first,
  with masked previews and one-key markdown export. A ritual that fails
  (plain folder, no manifests) contributes an error line, never a crash.
- **The Seance table.** The souls heatmap, the chronicle, and a two-ref
  scry in one view: select an hour on the heatmap to see that hour's
  commits (in the commit's recorded timezone, via the newly public
  `history.weekday_hour`), select a commit for its full story.
- **The headless twin, everywhere.** New `tui_ops.incantation_args` maps
  any chamber's option values to their exact CLI flags -- the Grimoire's
  recipes and the console's argv both come from it, so what the Sanctum
  shows is what the shell would run.

### Changed

- `git_reaper.tui` is now a package (app, widgets, one module per
  chamber); `run_tui` and every screen stay importable from
  `git_reaper.tui`. Textual remains confined to the `[tui]` extra.

## [0.7.0] - 2026-07-03

The Apprentice: the reaper teaches what it has learned.

### Added

- **The Apprentice (`reaper distill`).** Skill harvesting: read a repo and
  emit a portable Agent Skill — a `SKILL.md` bundle with `reference/` files
  for structure (the bones map), conventions (layout, languages, tooling,
  the measured commit style), commands (real build/test/lint/run
  invocations lifted from `pyproject.toml`, the `Makefile`, `package.json`,
  and CI workflows — never guessed), gotchas (the files that break most,
  via churn plus the omens bug-fix signal, and the fix themes that recur),
  and ownership (top souls and the bus factor; `--anon` reduces them to
  roles). Composed from rituals that already exist, deterministic by
  default: zero network, zero model calls. `--profile
  {repo,stack,onboarding}` sets the voice.
- **Polish, on your key (`distill --polish CMD`).** The opt-in escape hatch
  from the deterministic draft: each reference file's prose is piped
  through the caller's own command (stdin to stdout) — a `claude -p`
  wrapper, a local model, anything you trust. Frontmatter and provenance
  stamps are held back and reattached, so a polisher may smooth prose but
  never rewrite facts of origin, and `--check` still works on polished
  skills. The model lives on the caller's side; the no-phone-home vow
  holds.
- **Freshness is first-class.** Every skill is stamped with the source and
  sha it was distilled from; `reaper distill --check skills/<name>/` exits
  3 (cursed) once the code has moved on, for one-line CI gates.
- **Skill harvesting at fleet scale.** `reaper necropolis distill` writes
  one skill directory per grave (plus the usual `INDEX.md`); the fleet
  runner now understands directory-bundle artifacts. A routing **index
  skill** lands at the library's root: a `SKILL.md` an agent loads first,
  with one row per harvested skill (description read back from the skill
  itself) and an honest list of any graves the fan-out failed on.

## [0.6.0] - 2026-07-02

The Communion: the reaper learns to speak with agents.

### Added

- **The Communion (`reaper commune`).** git-reaper as an MCP server, behind
  the new `git-reaper[mcp]` extra. Every read-only analysis ritual becomes
  an agent-callable tool returning provenance-stamped JSON, over stdio
  (default) or `--http HOST:PORT`. Guardrails, all opt-in to loosen:
  rooted to the launch source (`--root`/`--host` widen the circle),
  read-only unless `--allow-write` (which reveals `resurrect`, `reanimate`,
  and `banish`; `veil` scrubs text in flight and is always on), and
  `plague` stays offline unless `--allow-network`. Publishes
  the grimoire, tombstone, and census as MCP resources plus
  pack/audit/explain prompts, and reads defaults from a `[commune]`
  grimoire table. This retires `ouija`: the model now lives on the agent
  side, and git-reaper keeps its no-phone-home vow.
- **Provenance knows its caller.** `tui_ops` rituals now stamp artifacts
  with the surface that ran them (`reaper summon (census)` vs
  `reaper commune (census)`) via a context-scoped invoker.
- **`reaper pulse`** now reports the `[mcp]` extra.
- **Descriptions toggle (`d`).** The TUI rituals list can be flipped between
  a compact names-only view (the default) and the roomy two-line layout with
  a dimmed description beneath each name. The selected ritual and the
  graying of git-only rituals both survive the flip; the key is listed in
  the footer and the `?` help screen.
- **The grim reaper takes the stage.** The gallery gains a full hooded
  figure -- blade arcing over the cowl, skeletal grip on the shaft, tattered
  hem trailing into the mist (per the ASCII brief) -- plus a hooded visage
  for skinny terminals, both summonable via the hidden `reaper boo`.

### Changed

- **Art hangs in a gallery now.** The art module became a data-driven
  package: each piece lives in its own text file under
  `art/gallery/` (the `boo()` pool, auto-discovered) or `art/seasonal/`,
  retrieved by name through a cached `piece()` loader. Dropping a `.txt`
  into the gallery makes it discovered, served, and tested with no code
  change.
- **Room to breathe.** The TUI rituals list now shows each ritual's name on
  its own line with a dimmed description beneath, instead of the cramped
  `name - description` one-liner. `tui_ops.Operation` splits its `label`
  into `key` (the display name) and a new `description` field; `label`
  remains as a derived property and still titles the header above the
  options panel.

## [0.5.0] - 2026-07-02

Dark Arts, the Necropolis, and the Séance.

### Added

- `reaper exhume [SOURCE]` - scan the full history (every reachable blob) for
  committed secrets via regex signatures plus a Shannon-entropy sweep.
  Previews are masked (`AKIA...MNOP`), never the full secret. `--baseline`
  suppresses known findings (a JSON fingerprint list or a prior `--format
  json` report); `--fail-on {any,high}` gates CI with exit `3`.
- `reaper veil ARTIFACT` - scrub secrets and configured patterns from any
  artifact (or stdin, `-`), replacing each match with `[VEILED:rule-name]`.
  Shares one rules engine (`core/rules.py`) with `exhume`; also inline as
  `conjure --veil`, whose per-file hashes and receipts describe the veiled
  bytes so the round trip still verifies.
- `reaper omens [SOURCE]` - composite per-file risk prophecy: a weighted
  blend of churn, bug-fix commit density, recency, and size, each normalized
  to 0..1. `--lens {all,churn,bugs,age,size}`; weights configurable via the
  grimoire's `[omens]` table. `--fail-over N` gates CI with exit `3`. Omens
  are framed as hints, not fate.
- `reaper doppelgangers [SOURCE]` - find duplicate files by content hash,
  reporting clusters and reclaimable space (empty files ignored by default).
- `reaper bloat [SOURCE]` - the largest working-tree files and, in a repo,
  the blobs deleted from the tree but still weighing down `.git`.
- `reaper bones [SOURCE]` - strip implementation, keep structure: imports,
  signatures, and docstrings. Python via stdlib `ast`; other languages via
  the new `git-reaper[bones]` (tree-sitter) extra, reported as skipped
  without it, never silently dropped.
- `reaper scry REF_A REF_B` - compare two refs: churn, most-changed files,
  contributors, and souls first seen in the range. Graduated from the back
  of the crypt now that `omens` has stabilized.
- `reaper plague [SOURCE]` - opt-in, network-using: read dependency manifests
  (pyproject, requirements, package.json) and check the exactly-pinned ones
  against the OSV database. `--offline` degrades to manifest parsing only;
  `--fail-on any` gates CI. The only command that ever leaves the crypt.
- `reaper necropolis COMMAND` - fan any source-taking command across every
  grave in a `necropolis.toml` manifest (or a GitHub `--org` via the `gh`
  CLI). Writes per-repo artifacts plus a combined `INDEX.md`; a failed grave
  never stops the fleet, and a cursed grave propagates exit `3`.
- HTML report output (`--format html`) for the analysis commands: a
  self-contained, dark-themed page with inline CSS bar charts and no external
  requests.
- Exit code `3` ("cursed") is now live, wired into every `--fail-on` /
  `--fail-over` gate for one-line CI usage.
- Third-party rituals: the `git_reaper.rituals` entry-point group mounts
  external Typer sub-apps as `reaper <name>`; a broken plugin is reported and
  skipped, never fatal.
- Grimoire extensions: `[rules.<name>]` tables extend the shared secret/PII
  engine, and `[omens]` weights tune the risk blend. `grimoire` now reports
  both, with their source.
- Easter eggs: a Halloween banner on October 31 and a Friday-the-13th footer,
  both bypassed by `--plain`.
- Git backend gains blob-level mining (`blobs`, `cat_blob`, `blob_commit`),
  with subprocess/GitPython parity tests.
- **Dracula by default.** The TUI ships a bespoke `reaper-dracula` theme that
  maps the reaper's spooky tokens onto Dracula's palette (eldritch purple,
  necro green, blood red, ember orange). **Ctrl+P** opens Textual's command
  palette to switch to any built-in theme (dracula, nord, gruvbox, ...) live.
- **Fuller ritual coverage.** The TUI now exposes the analysis rituals it was
  missing: `exhume`, `omens`, `doppelgangers`, `bloat`, `bones`, and `plague`
  -- 18 rituals in all, grouped in the sidebar (reaping, packing, necromancy,
  forensics, dark arts).
- **Per-ritual options panel.** Each ritual's flags are editable widgets:
  `format` (md/json/csv/html), `omens --lens`, `souls --heatmap`,
  `chronicle --changelog`, limits, `exhume`'s entropy toggle, and
  `plague --offline` (on by default -- no surprise network). Options are
  declared in the textual-free `tui_ops`, so the base suite covers them.
- **Cursed badge.** `exhume`, `omens`, and `plague` results show a red badge
  with the finding count; previews stay masked.
- **Quality of life:** arrow-key highlighting selects a ritual outright (no
  Enter needed), the selected ritual's name sits in its own header above the
  work area while run status stays in a bar at the bottom, copy the artifact to
  the clipboard (`c`), a directory browser for the source (`b`), a source
  inspector that grays git-only rituals on a plain folder, staged reaping
  progress, a raw/rendered markdown toggle (`m`), format-aware save filenames,
  a help screen (`?`), and recipes that prefill their known flags into the
  options panel.

### Changed

- **Breaking:** the `tree` command is now `limbs` (its artifact schema is
  `limbs/v1`). One themed name per command, as the naming decision requires.
- `tui_ops.Operation` gains `group` and `options`, and its `run` now takes an
  options dict and returns a `ReapResult` (text, summary, cursed). The TUI
  minimum is bumped to `textual>=0.86` for the theme API.

## [0.4.0] - 2026-07-02

The Summoning. An interactive TUI over the same core the CLI drives.

### Added

- `reaper summon [SOURCE]` - launch a Textual TUI (behind the `git-reaper[tui]`
  extra): a source input, a ritual picker, a live scythe-spinner while the core
  runs on a worker thread, a scrollable preview of the rendered artifact, and a
  save dialog. Grimoire recipes are listed and prefill the source and ritual on
  selection. Without the extra, `summon` exits with clear guidance to install
  it.
- `git_reaper.tui_ops`: a textual-free registry mapping each interactive
  ritual to its core function and formatter, so the wiring is testable without
  the TUI.

## [0.3.0] - 2026-07-02

Git Necromancy. Mining commit history: who, what, when, and what has died.

### Added

#### Commands

- `reaper chronicle` - extract commit history (SHA, author, date, message,
  files touched, insertions/deletions) to markdown, JSON, or CSV.
  `--changelog` groups commits under the tag that heads their release range.
- `reaper souls` - contributor stats: commits, lines added/removed, first and
  last seen, and a bus-factor estimate. `--heatmap` renders a day-of-week x
  hour activity grid (bucketed by each commit's recorded timezone, so output
  never depends on the machine) and flags the repo's "witching hour."
- `reaper haunt` - code churn and hotspots: files ranked by change frequency
  and churn, the classic bug-risk proxy.
- `reaper autopsy <path>` - deep single-file examination: creation commit,
  rename history (`--follow`, on by default), authors over time, churn
  totals, and a blame-based line-age summary.
- `reaper graveyard` - every file that ever lived and died: path, date of
  death, the fatal commit, and its author. Renamed-away paths count as deaths.
- `reaper resurrect <path>` - restore a dead file's last living bytes (read
  from the parent of the commit that removed it) into the working tree or
  `--out`. Absolute paths and `..` segments are refused, same as reanimate.
- `reaper ghosts` - branch hygiene: branches ranked by abandonment, with
  merged, gone-upstream, and (past `--than 90d`) stale flags.
- `reaper rot` - staleness report: surviving files ranked by how long they
  have gone untouched, ages derived from a single log pass.
- `reaper tombstone` - a stats card for demos and READMEs (born, age,
  commits, souls, last words, witching hour) as ASCII tombstone art, or JSON.

#### Output and formats

- CSV output (`--format csv`) for `chronicle`, `souls`, `haunt`, `graveyard`,
  `ghosts`, and `rot`.

#### Library and backends

- The git backend gained the history surface: `log` (with per-file numstat
  churn), `file_log`, `rename_history`, `deleted_files`, `show_file`,
  `branches`, and `tags`. Commit records use control-char field separators so
  multiline messages can never break the parse, and `--no-renames` keeps churn
  attribution stable.
- Optional GitPython backend behind the `git-reaper[git]` extra, selectable
  with `GIT_REAPER_BACKEND=gitpython`. It shares command shapes and parsers
  with the subprocess backend (`git_reaper.gitio.logparse`), so both return
  byte-identical results.

### Fixed

- History commands run against a full clone: a full-depth fetch now
  `--unshallow`s a previously shallow catacombs clone instead of silently
  seeing only the tip commit.
- Non-ASCII paths in history output are no longer C-quoted (`core.quotepath`
  is disabled on log commands), so they read as UTF-8 literals.

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

[Unreleased]: https://github.com/jmcmeen/git-reaper/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/jmcmeen/git-reaper/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/jmcmeen/git-reaper/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/jmcmeen/git-reaper/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/jmcmeen/git-reaper/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/jmcmeen/git-reaper/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/jmcmeen/git-reaper/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/jmcmeen/git-reaper/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/jmcmeen/git-reaper/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jmcmeen/git-reaper/releases/tag/v0.1.0
