"""The Necropolis board: the fleet, grave by grave, on one dashboard.

Load a necropolis.toml, pick a ritual, and reap the whole yard: each grave's
row shows its fate live (rest in peace, CURSED, or the plain failure), and
selecting a row drops its artifact into the preview without leaving the
chamber. The same fleet manifest `reaper necropolis` reads -- no TUI-only
fleet format.
"""

from __future__ import annotations

import contextlib
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, TextArea

from git_reaper.core import fleet as fleet_core
from git_reaper.tui.widgets import HelpScreen, ScytheSpinner
from git_reaper.tui_ops import OPERATIONS, OPERATIONS_BY_KEY, Operation, resolve

_HELP = (
    "[b]the necropolis board[/b]\n"
    "the fleet as rows. load a necropolis.toml (the same manifest the CLI\n"
    "fans out over), pick a ritual, reap the yard. select a row to read that\n"
    "grave's artifact in place; a CURSED fate means the ritual's gate tripped.\n\n"
    "  l  load manifest    r  reap the fleet\n"
    "  escape  crypt map   ?  this help"
)

_COLUMNS = ("grave", "source", "last reaped", "fate", "summary")


class NecropolisScreen(Screen[None]):
    """The fleet dashboard."""

    BINDINGS = [
        ("l", "load", "Load"),
        ("r", "reap_fleet", "Reap fleet"),
        ("question_mark", "help", "Help"),
        ("escape", "app.crypt", "Crypt map"),
        ("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._graves: list[fleet_core.Grave] = []
        self._artifacts: dict[str, str] = {}
        self._reaping = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="main"):
            with Horizontal(classes="board-controls"):
                yield Input(value=fleet_core.MANIFEST, placeholder="necropolis.toml", id="manifest")
                yield Button("load (l)", id="load")
                yield Select(
                    # positional rituals (autopsy, lineage, veil) want per-grave
                    # arguments the fleet cannot supply; they stay off the board
                    [(op.key, op.key) for op in OPERATIONS if op.positional is None],
                    value="census",
                    allow_blank=False,
                    id="fleet-ritual",
                )
                yield Button("reap fleet (r)", id="reap-fleet", variant="primary")
            yield DataTable(id="graves", cursor_type="row")
            yield TextArea("", id="board-preview", read_only=True)
            yield ScytheSpinner("", id="spinner")
            yield Label("load a manifest to see the yard", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#graves", DataTable)
        for column in _COLUMNS:
            table.add_column(column, key=column)
        self.action_load()

    def on_screen_resume(self) -> None:
        self.app.sub_title = "the necropolis board"

    # -- loading -----------------------------------------------------------

    @on(Button.Pressed, "#load")
    def _load_button(self) -> None:
        self.action_load()

    def action_load(self) -> None:
        table = self.query_one("#graves", DataTable)
        table.clear()
        self._artifacts.clear()
        manifest = Path(self.query_one("#manifest", Input).value.strip() or fleet_core.MANIFEST)
        try:
            self._graves = fleet_core.load_manifest(manifest)
        except fleet_core.FleetError as exc:
            self._graves = []
            self._status(str(exc))
            return
        for grave in self._graves:
            table.add_row(grave.name, grave.source, "-", "-", "-", key=grave.name)
        self._status(f"{len(self._graves)} graves in the yard - pick a ritual and reap")

    # -- reaping the fleet ---------------------------------------------------

    @on(Button.Pressed, "#reap-fleet")
    def _reap_button(self) -> None:
        self.action_reap_fleet()

    def action_reap_fleet(self) -> None:
        if self._reaping:
            self.notify("the fleet is already being reaped", severity="warning")
            return
        if not self._graves:
            self.notify("load a manifest first", severity="warning")
            return
        key = str(self.query_one("#fleet-ritual", Select).value)
        op = OPERATIONS_BY_KEY[key]
        self._reaping = True
        self.query_one(ScytheSpinner).start(f"reaping {key} across {len(self._graves)} graves")
        self._fleet_worker(op, list(self._graves))

    @work(thread=True, exclusive=True)
    def _fleet_worker(self, op: Operation, graves: list[fleet_core.Grave]) -> None:
        cursed = 0
        failed = 0
        try:
            for grave in graves:
                self.app.call_from_thread(
                    self.query_one(ScytheSpinner).stage, f"reaping {grave.name}"
                )
                try:
                    opts = op.defaults()
                    resolved = resolve(grave.source, opts)
                    if "out" in opts:
                        # Writing rituals get one bundle per grave, exactly as the
                        # CLI fan-out does -- a shared out dir would let one
                        # grave's loot refresh-clobber another's.
                        opts["out"] = str(Path(str(opts["out"])) / grave.name)
                    result = op.run(resolved.repo, opts)
                except Exception as exc:  # a grave must never take the fleet down
                    failed += 1
                    row = (grave.name, "failed", str(exc), None)
                    self.app.call_from_thread(self._update_row, *row)
                    continue
                cursed += 1 if result.cursed else 0
                fate = "CURSED" if result.cursed else "rest in peace"
                self.app.call_from_thread(
                    self._update_row, grave.name, fate, result.summary, result.text
                )
        finally:
            # the yard is released however the reaping ended: a render that
            # throws must not leave `reap the fleet` locked out for good.
            self.app.call_from_thread(self._fleet_done, len(graves), cursed, failed)

    def _update_row(self, name: str, fate: str, summary: str, artifact: str | None) -> None:
        table = self.query_one("#graves", DataTable)
        when = datetime.now().strftime("%H:%M:%S")
        table.update_cell(name, "last reaped", when)
        styled = Text(fate, style="bold red") if fate == "CURSED" else Text(fate)
        table.update_cell(name, "fate", styled)
        table.update_cell(name, "summary", summary)
        if artifact is not None:
            self._artifacts[name] = artifact

    def _fleet_done(self, total: int, cursed: int, failed: int) -> None:
        self._reaping = False
        with contextlib.suppress(NoMatches):  # the chamber may already be gone
            self.query_one(ScytheSpinner).stop()
            note = f"reaped {total - failed}/{total} graves"
            if cursed:
                note += f", {cursed} cursed"
            if failed:
                note += f", {failed} failed"
            self._status(note + " - select a row to read its artifact")

    # -- drill-in ---------------------------------------------------------------

    @on(DataTable.RowSelected, "#graves")
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        name = event.row_key.value if event.row_key else None
        if name:
            self._row_selected_by_name(name)

    def _row_selected_by_name(self, name: str) -> None:
        if name in self._artifacts:
            self.query_one("#board-preview", TextArea).text = self._artifacts[name]
            self._status(f"reading {name}'s artifact")
        else:
            self._status(f"{name} has no artifact yet - reap the fleet first")

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen(_HELP))

    def _status(self, message: str) -> None:
        self.query_one("#status", Label).update(message)
