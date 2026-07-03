"""The Reliquary: security and risk triage on one slab.

One pass runs exhume, omens, plague (offline), and rot against the source
and lays every finding out most-cursed first -- masked previews, never a raw
secret. One key exports the slab as markdown. The whole security-and-risk
workflow, one screen.
"""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from git_reaper.core.source import resolve_source
from git_reaper.models import RepoRef
from git_reaper.tui.widgets import HelpScreen, SaveScreen, ScytheSpinner
from git_reaper.tui_ops import TriageReport, render_triage, triage

_HELP = (
    "[b]the reliquary[/b]\n"
    "one triage pass: exhume (secrets), omens (risk), plague (advisories,\n"
    "offline), and rot (staleness), merged and sorted most-cursed first.\n"
    "previews are masked; the raw secret never reaches this screen.\n\n"
    "  t  triage the source    e  export the slab as markdown\n"
    "  escape  crypt map       ?  this help"
)


class ReliquaryScreen(Screen[None]):
    """The forensics board."""

    BINDINGS = [
        ("t", "triage", "Triage"),
        ("e", "export", "Export"),
        ("question_mark", "help", "Help"),
        ("escape", "app.crypt", "Crypt map"),
        ("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._report: TriageReport | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="main"):
            with Horizontal(classes="board-controls"):
                yield Input(placeholder="path or repo URL", id="source")
                yield Button("triage (t)", id="triage", variant="primary")
                yield Button("export (e)", id="export")
            yield DataTable(id="slab", cursor_type="row")
            yield ScytheSpinner("", id="spinner")
            with Horizontal(id="statusbar"):
                yield Label("point it at a repo and press t", id="status")
                yield Static("", id="badge")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#source", Input).value = self.app.source  # type: ignore[attr-defined]
        table = self.query_one("#slab", DataTable)
        for column in ("severity", "ritual", "subject", "detail"):
            table.add_column(column, key=column)

    def on_screen_resume(self) -> None:
        self.app.sub_title = "the reliquary"

    @on(Input.Changed, "#source")
    def _source_changed(self, event: Input.Changed) -> None:
        self.app.source = event.value.strip() or "."  # type: ignore[attr-defined]

    @on(Button.Pressed, "#triage")
    def _triage_button(self) -> None:
        self.action_triage()

    @on(Button.Pressed, "#export")
    def _export_button(self) -> None:
        self.action_export()

    def action_triage(self) -> None:
        source = self.query_one("#source", Input).value.strip() or "."
        self.query_one(ScytheSpinner).start(f"triaging {source}")
        self._badge_off()
        self._triage_worker(source)

    @work(thread=True, exclusive=True)
    def _triage_worker(self, source: str) -> None:
        try:
            resolved = resolve_source(source, depth=None)
        except Exception as exc:
            self.app.call_from_thread(self._triage_failed, str(exc))
            return
        report = self._run_triage(resolved.repo)
        self.app.call_from_thread(self._show_report, report)

    @staticmethod
    def _run_triage(repo: RepoRef) -> TriageReport:
        return triage(repo)

    def _triage_failed(self, message: str) -> None:
        self.query_one(ScytheSpinner).stop()
        self._status(f"the triage failed: {message}")
        self.notify(message, severity="error", title="the triage failed")

    def _show_report(self, report: TriageReport) -> None:
        self.query_one(ScytheSpinner).stop()
        self._report = report
        table = self.query_one("#slab", DataTable)
        table.clear()
        for i, row in enumerate(report.rows):
            severity = (
                Text(f"{row.severity:.2f}", style="bold red")
                if row.severity >= 0.75
                else Text(f"{row.severity:.2f}")
            )
            table.add_row(severity, row.ritual, row.subject, row.detail, key=str(i))
        note = report.summary
        if report.errors:
            note += " - skipped: " + "; ".join(report.errors)
        self._status(note + " (e exports the slab)")
        if report.cursed:
            self._badge_on()
        else:
            self._badge_off()

    def action_export(self) -> None:
        if self._report is None:
            self.notify("nothing triaged yet", severity="warning")
            return
        self.app.push_screen(SaveScreen("reliquary.md"), self._write_export)

    def _write_export(self, path: str | None) -> None:
        if not path or self._report is None:
            return
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_triage(self._report), encoding="utf-8")
        self.notify(f"interred at {target}")

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen(_HELP))

    def _status(self, message: str) -> None:
        self.query_one("#status", Label).update(message)

    def _badge_on(self) -> None:
        badge = self.query_one("#badge", Static)
        badge.update("CURSED - found what you feared")
        badge.display = True

    def _badge_off(self) -> None:
        self.query_one("#badge", Static).display = False
