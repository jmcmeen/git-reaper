---
name: run-git-reaper
description: Build, run, and drive git-reaper. Use when asked to run or start the reaper CLI or the summon TUI, run its tests, take a screenshot of the TUI, or verify a change works in the real app.
---

git-reaper is a Python CLI (Typer) with an optional Textual TUI (`reaper summon`).
The CLI is driven directly via `uv run reaper ...`; the TUI is driven headlessly —
no terminal, tmux, or X needed — via `.claude/skills/run-git-reaper/driver.py`,
which wraps Textual's Pilot test harness and reads commands from stdin.

All paths are relative to the repo root.

## Prerequisites

Only `uv` and `git` (both preinstalled here). No apt packages needed — the TUI
driver runs headless through Textual's test harness, not a real terminal.

## Setup

```bash
uv sync --all-extras   # deps + tui/bones/tokens/git extras (~30s cold)
```

Plain `uv sync` (or `--extra tui`) **removes** any other extras already in the
venv — use `--all-extras` unless you mean to prune.

## Run: CLI (agent path)

No build step; `uv run` picks up source changes immediately. Smoke sequence
(all verified):

```bash
uv run reaper --version        # e.g. git-reaper 0.5.1.dev5+g506b73b77 (hatch-vcs: moves with commits)
uv run reaper pulse            # signs-of-life table; exits 0
uv run reaper census . --format json | python3 -c "import json,sys; print(json.load(sys.stdin)['provenance']['files'])"
uv run reaper limbs . --format json | python3 -c "import json,sys; print(json.load(sys.stdin)['file_count'])"
uv run reaper haunt . -n 3 --format json | python3 -c "import json,sys; print(json.load(sys.stdin)['hotspots'][0]['path'])"
uv run reaper tombstone .      # ASCII tombstone art
```

Artifacts go to stdout, narration to stderr — pipe safely. Non-tty output is
automatically plain ASCII.

## Run: summon TUI (agent path)

Drive the TUI with the driver — pipe commands on stdin, one per line:

```bash
uv run python .claude/skills/run-git-reaper/driver.py . <<'EOF'
ss /tmp/summon-launch.svg
click #reap
wait 3
text #status
eval app.query_one("#preview").text[:300]
ss /tmp/summon-reaped.svg
quit
EOF
```

Expected: `[driver] launched ...`, then after the reap `text #status` prints
`reaped limbs - N crypts, M souls (s to save)` and the eval prints the tree
artifact. Screenshots are **SVG** (Textual native). To view one as PNG:

```bash
uv run --with cairosvg python -c \
  "import cairosvg; cairosvg.svg2png(url='/tmp/summon-reaped.svg', write_to='/tmp/summon-reaped.png', output_width=1400)"
```

Driver commands:

| command | what it does |
|---|---|
| `ss <path.svg>` | save an SVG screenshot of the current screen |
| `press <k1> <k2> ...` | key presses (textual names: `down`, `enter`, `escape`, `r`, `s` ...) |
| `click <selector>` | click a widget, e.g. `click #reap`, `click #operations` |
| `type <text>` | type literal text into the focused widget |
| `text <selector>` | print a widget's value/text (searches the topmost screen, so modals work) |
| `eval <expr>` | eval raw Python; `app` and `pilot` in scope |
| `wait <secs>` | let workers run — reaps happen in a thread worker, give them ~3s |
| `quit` | clean exit (EOF also quits) |

Useful selectors: `#source` (source Input), `#operations` (rituals OptionList),
`#reap` (Reap button), `#preview` (artifact TextArea), `#status` (status Label),
`#path`/`#ok`/`#cancel` (SaveScreen modal).

Verified flows:

```text
# pick a different ritual by keyboard, then reap with the r binding
click #operations
press down down down          # lands on conjure
press r
wait 3
text #status                  # reaped conjure - 92 files, ~195,848 tokens (s to save)

# save the artifact to disk (SaveScreen modal)
click #reap
wait 3
press s
eval app.screen.__class__.__name__   # 'SaveScreen'
type /tmp/artifact.md                # replaces the default (Input selects-all on focus)
press enter
wait 1
text #status                  # wrote /tmp/artifact.md
```

## Run (human path)

`uv run reaper summon .` opens the TUI in your terminal (q quits). Useless
headless — it needs a real tty.

## Test

```bash
uv run pytest        # 256 passed in ~20s
make check           # lint + mypy + pytest (the full gauntlet)
```

## Gotchas

- **Focus starts in the source Input, so key bindings don't fire at launch.**
  Pressing `r` right after launch types the letter "r" into the source field
  instead of reaping. Click `#reap` / `#operations` (or press `tab`) first;
  after that the `r`/`s`/`d`/`q` bindings work.
- **Modal widgets need the topmost screen.** `app.query_one("#path")` raises
  NoMatches while SaveScreen is up — use `app.screen.query_one(...)` in `eval`
  (the driver's `text` command already does this).
- **SaveScreen has no escape binding.** `press escape` leaves the modal up;
  cancel with `click #cancel` (or submit with `press enter`).
- **Typing into the save path replaces the default** — Textual Inputs
  select-all on focus, so `type /tmp/foo.md` overwrites `limbs.md`; no need to
  clear first.
- **Reaps are async.** Reap runs in a thread worker; read `#status`/`#preview`
  too early and you get the pre-reap state. `wait 3` is enough for this repo.
- **SVG→PNG tofu boxes are a conversion artifact.** cairosvg lacks the
  box-drawing glyphs, so borders render as □□□. The app is fine — judge layout
  and text, not the borders.
- **`uv sync --extra tui` uninstalls the other extras.** Sync with
  `--all-extras` to keep bones/tokens/git available.

## Troubleshooting

- **`NoMatches: No nodes match '#status' on SaveScreen()`**: a modal is still
  open (escape doesn't close SaveScreen). `click #cancel` first.
- **`text #path` prints a `rich.panel.Panel` repr instead of the value**: only
  with an old driver copy — the driver reads `Input.value` before falling back
  to `render()`; make sure you're running the committed driver.
- **Reap seems to do nothing, status still "pick a ritual and reap"**: the `r`
  went into the source Input (see Gotchas); click `#reap` instead.
