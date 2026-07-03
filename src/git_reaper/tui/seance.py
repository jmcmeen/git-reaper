"""The Seance table: the repo's history, explorable.

Three instruments on one table: the souls heatmap (pick an hour, see that
hour's commits), the chronicle beneath it, and a scry picker for ref-versus-
ref deltas. All three drive the same history core the CLI uses.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, TextArea

from git_reaper.core import history as history_core
from git_reaper.core import scry as scry_core
from git_reaper.core.source import resolve_source
from git_reaper.formatters import markdown
from git_reaper.models import CommitEntry
from git_reaper.tui.widgets import HelpScreen, ScytheSpinner
from git_reaper.tui_ops import invoker

_HELP = (
    "[b]the seance table[/b]\n"
    "the heatmap counts commits by weekday and hour (as recorded, never\n"
    "your machine's clock). select a cell to see that hour's commits;\n"
    "select the weekday column to see the whole chronicle again.\n"
    "scry two refs (tags, branches, shas) for the delta between them.\n\n"
    "  l  load the history    s  scry the two refs\n"
    "  escape  crypt map      ?  this help"
)

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class SeanceScreen(Screen[None]):
    """The history explorer."""

    BINDINGS = [
        ("l", "load", "Load"),
        ("s", "scry", "Scry"),
        ("question_mark", "help", "Help"),
        ("escape", "app.crypt", "Crypt map"),
        ("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._commits: list[CommitEntry] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="main"):
            with Horizontal(classes="board-controls"):
                yield Input(placeholder="path or repo URL", id="source")
                yield Button("load (l)", id="load", variant="primary")
            with Horizontal(id="scry-row"):
                yield Input(placeholder="ref A (e.g. v1.0.0)", id="ref-a")
                yield Input(placeholder="ref B (e.g. HEAD)", id="ref-b")
                yield Button("scry (s)", id="scry-btn")
            yield DataTable(id="heatmap", cursor_type="cell")
            yield DataTable(id="hour-commits", cursor_type="row")
            yield TextArea("", id="board-preview", read_only=True)
            yield ScytheSpinner("", id="spinner")
            yield Label("load a repo to raise its history", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#source", Input).value = self.app.source  # type: ignore[attr-defined]
        heatmap = self.query_one("#heatmap", DataTable)
        heatmap.add_column("day", key="day")
        for hour in range(24):
            heatmap.add_column(f"{hour:02d}", key=str(hour))
        commits = self.query_one("#hour-commits", DataTable)
        for column in ("when", "author", "message"):
            commits.add_column(column, key=column)
        self.action_load()

    def on_screen_resume(self) -> None:
        self.app.sub_title = "the seance table"

    @on(Input.Changed, "#source")
    def _source_changed(self, event: Input.Changed) -> None:
        self.app.source = event.value.strip() or "."  # type: ignore[attr-defined]

    # -- loading ----------------------------------------------------------------

    @on(Button.Pressed, "#load")
    def _load_button(self) -> None:
        self.action_load()

    def action_load(self) -> None:
        source = self.query_one("#source", Input).value.strip() or "."
        self.query_one(ScytheSpinner).start(f"raising {source}")
        self._load_worker(source)

    @work(thread=True, exclusive=True, group="load")
    def _load_worker(self, source: str) -> None:
        try:
            resolved = resolve_source(source, depth=None)
            with invoker("reaper summon"):
                souls = history_core.souls(resolved.repo, heatmap=True)
                chronicle = history_core.chronicle(resolved.repo)
        except Exception as exc:
            self.app.call_from_thread(self._load_failed, str(exc))
            return
        self.app.call_from_thread(self._show_history, souls.heatmap or [], chronicle.commits)

    def _load_failed(self, message: str) -> None:
        self.query_one(ScytheSpinner).stop()
        self._status(f"the seance failed: {message}")
        self.notify(message, severity="error", title="the seance failed")

    def _show_history(self, grid: list[list[int]], commits: list[CommitEntry]) -> None:
        self.query_one(ScytheSpinner).stop()
        self._commits = commits
        heatmap = self.query_one("#heatmap", DataTable)
        heatmap.clear()
        peak = max((cell for row in grid for cell in row), default=0)
        for weekday, row in enumerate(grid):
            cells: list[Any] = [Text(_WEEKDAYS[weekday], style="bold")]
            for count in row:
                if count == 0:
                    cells.append(Text(".", style="dim"))
                elif peak and count == peak:
                    cells.append(Text(str(count), style="bold red"))
                else:
                    cells.append(Text(str(count)))
            heatmap.add_row(*cells, key=str(weekday))
        self._show_commits(commits)
        self._status(
            f"{len(commits)} commits on the table - select an hour to hold it to the light"
        )

    def _show_commits(self, commits: list[CommitEntry]) -> None:
        table = self.query_one("#hour-commits", DataTable)
        table.clear()
        for entry in commits[:200]:
            message = entry.message.splitlines()[0] if entry.message else ""
            table.add_row(entry.date[:16], entry.author, message, key=entry.sha)

    # -- the heatmap answers ------------------------------------------------------

    @on(DataTable.CellSelected, "#heatmap")
    def _cell_selected(self, event: DataTable.CellSelected) -> None:
        if event.coordinate.column == 0:  # the weekday label: back to everything
            self._show_commits(self._commits)
            self._status(f"{len(self._commits)} commits on the table")
            return
        self._filter_hour(event.coordinate.row, event.coordinate.column - 1)

    def _filter_hour(self, weekday: int, hour: int) -> None:
        chosen = [
            entry
            for entry in self._commits
            if history_core.weekday_hour(entry.date) == (weekday, hour)
        ]
        self._show_commits(chosen)
        self._status(f"{_WEEKDAYS[weekday]} {hour:02d}:00 - {len(chosen)} commits in that hour")

    @on(DataTable.RowSelected, "#hour-commits")
    def _commit_selected(self, event: DataTable.RowSelected) -> None:
        sha = event.row_key.value if event.row_key else None
        entry = next((c for c in self._commits if c.sha == sha), None)
        if entry is None:
            return
        detail = (
            f"commit {entry.sha}\nauthor: {entry.author} <{entry.email}>\n"
            f"date:   {entry.date}\n\n{entry.message}\n\n"
            f"{entry.files_changed} files, +{entry.insertions}/-{entry.deletions}"
        )
        self.query_one("#board-preview", TextArea).text = detail

    # -- scrying --------------------------------------------------------------------

    @on(Button.Pressed, "#scry-btn")
    def _scry_button(self) -> None:
        self.action_scry()

    def action_scry(self) -> None:
        ref_a = self.query_one("#ref-a", Input).value.strip()
        ref_b = self.query_one("#ref-b", Input).value.strip() or "HEAD"
        if not ref_a:
            self.notify("scrying needs two refs; fill ref A", severity="warning")
            return
        source = self.query_one("#source", Input).value.strip() or "."
        self.query_one(ScytheSpinner).start(f"scrying {ref_a}..{ref_b}")
        self._scry_worker(source, ref_a, ref_b)

    @work(thread=True, exclusive=True, group="scry")
    def _scry_worker(self, source: str, ref_a: str, ref_b: str) -> None:
        try:
            resolved = resolve_source(source, depth=None)
            with invoker("reaper summon"):
                result = scry_core.scry(resolved.repo, ref_a, ref_b)
        except Exception as exc:
            self.app.call_from_thread(self._load_failed, str(exc))
            return
        text = markdown.render_scry(result)
        self.app.call_from_thread(self._show_scry, ref_a, ref_b, text)

    def _show_scry(self, ref_a: str, ref_b: str, text: str) -> None:
        self.query_one(ScytheSpinner).stop()
        self.query_one("#board-preview", TextArea).text = text
        self._status(f"the vision of {ref_a}..{ref_b} is below")

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen(_HELP))

    def _status(self, message: str) -> None:
        self.query_one("#status", Label).update(message)
