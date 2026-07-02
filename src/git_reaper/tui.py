"""The Summoning: a Textual TUI over the same core the CLI drives.

Thin adapter, same creed as the CLI: pick a source and a ritual, the core
does the work (on a thread, never blocking the event loop), and the rendered
artifact fills the preview. Save writes exactly what you see. Textual is only
imported here, so the base install stays lean; `reaper summon` reports the
missing `[tui]` extra clearly.
"""

from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Static,
    TextArea,
)
from textual.widgets.option_list import Option

from git_reaper import __version__, art
from git_reaper.config import GrimoireError, load_grimoire
from git_reaper.core.source import resolve_source
from git_reaper.models import Recipe
from git_reaper.tui_ops import OPERATIONS, OPERATIONS_BY_KEY, Operation

_SCYTHE = art.SCYTHE_FRAMES


class ScytheSpinner(Static):
    """A tiny reaping animation shown while a worker runs."""

    _timer: Timer | None = None

    def on_mount(self) -> None:
        self._i = 0
        self._timer = None
        self.display = False

    def start(self) -> None:
        self._i = 0
        self.display = True
        self._timer = self.set_interval(0.08, self._tick)

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.display = False

    def _tick(self) -> None:
        self._i = (self._i + 1) % len(_SCYTHE)
        self.update(f"reaping {_SCYTHE[self._i]}")


class SplashScreen(Screen[None]):
    """The skull, dismissed by any key so tests (and users) can move on."""

    def compose(self) -> ComposeResult:
        yield Static(f"{art.HERO_SKULL}\n\n  press any key to begin", id="splash")

    def on_key(self) -> None:
        self.dismiss()


class SaveScreen(ModalScreen[str | None]):
    """Ask where to write the artifact. Returns the path, or None on cancel."""

    def __init__(self, default: str) -> None:
        super().__init__()
        self._default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("inter the artifact at:")
            yield Input(value=self._default, id="path")
            with Horizontal(id="dialog-buttons"):
                yield Button("save", id="ok", variant="primary")
                yield Button("cancel", id="cancel")

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        self.dismiss(self.query_one("#path", Input).value.strip() or None)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted, "#path")
    def _submit(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)


class ReaperApp(App[None]):
    """The reaper's interactive face."""

    TITLE = "git-reaper"
    CSS = """
    #source { dock: top; margin: 0 1; }
    #body { height: 1fr; }
    #sidebar { width: 46; border-right: solid $primary; }
    #main { height: 1fr; }
    #preview { height: 1fr; border: round $primary; }
    #spinner { height: 1; color: $warning; padding: 0 1; }
    #status { height: 1; color: $text-muted; padding: 0 1; }
    .heading { text-style: bold; padding: 1 1 0 1; }
    #reap { margin: 1 1; width: 100%; }
    SplashScreen { align: center middle; }
    #dialog { padding: 1 2; width: 64; height: auto; border: round $primary; background: $surface; }
    """
    BINDINGS = [
        ("r", "reap", "Reap"),
        ("s", "save", "Save"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, source: str = ".") -> None:
        super().__init__()
        self._initial_source = source
        self.current_op: Operation = OPERATIONS[0]
        self._artifact: str = ""
        self._recipes: list[Recipe] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Input(value=self._initial_source, placeholder="path or repo URL", id="source")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Label("rituals", classes="heading")
                yield OptionList(
                    *(Option(op.label, id=op.key) for op in OPERATIONS), id="operations"
                )
                yield Label("recipes", classes="heading")
                yield OptionList(id="recipes")
                yield Button("Reap (r)", id="reap", variant="primary")
            with Vertical(id="main"):
                yield ScytheSpinner("", id="spinner")
                yield Label(f"git-reaper {__version__} - pick a ritual and reap", id="status")
                yield TextArea("", id="preview", read_only=True)
        yield Footer()

    def on_mount(self) -> None:
        self._load_recipes()
        self.push_screen(SplashScreen())

    def _load_recipes(self) -> None:
        try:
            self._recipes = load_grimoire().recipes
        except GrimoireError:
            self._recipes = []
        recipes = self.query_one("#recipes", OptionList)
        if not self._recipes:
            recipes.add_option(Option("(no recipes inscribed)", disabled=True))
            return
        for i, recipe in enumerate(self._recipes):
            line = " ".join(["reaper", recipe.command, *recipe.args])
            recipes.add_option(Option(f"{recipe.name}: {line}", id=f"recipe:{i}"))

    # -- selection ---------------------------------------------------------

    @on(OptionList.OptionSelected, "#operations")
    def _op_selected(self, event: OptionList.OptionSelected) -> None:
        self.current_op = OPERATIONS[event.option_index]
        self._status(f"ritual: {self.current_op.key}")

    @on(OptionList.OptionSelected, "#recipes")
    def _recipe_selected(self, event: OptionList.OptionSelected) -> None:
        if not self._recipes:
            return
        recipe = self._recipes[event.option_index]
        source = next((a for a in recipe.args if not a.startswith("-")), ".")
        self.query_one("#source", Input).value = source
        if recipe.command in OPERATIONS_BY_KEY:
            self.current_op = OPERATIONS_BY_KEY[recipe.command]
            self.query_one("#operations", OptionList).highlighted = OPERATIONS.index(
                self.current_op
            )
        incantation = " ".join(["reaper", recipe.command, *recipe.args])
        # Honest: we prefill and show the full incantation; extra flags are the
        # CLI's job, so we don't pretend to have applied them.
        self._status(f"loaded {recipe.name}: {incantation}  (press r to reap the source)")

    @on(Button.Pressed, "#reap")
    def _reap_button(self) -> None:
        self.action_reap()

    # -- actions -----------------------------------------------------------

    def action_reap(self) -> None:
        source = self.query_one("#source", Input).value.strip() or "."
        self.query_one(ScytheSpinner).start()
        self._status(f"reaping {self.current_op.key} from {source} ...")
        self._reap_worker(source, self.current_op)

    @work(thread=True, exclusive=True)
    def _reap_worker(self, source: str, op: Operation) -> None:
        try:
            resolved = resolve_source(source, depth=None)
            text = op.run(resolved.repo)
        except Exception as exc:  # surface the plain cause; never hide it
            self.call_from_thread(self._show_error, str(exc))
            return
        self.call_from_thread(self._show_result, op.key, text)

    def action_save(self) -> None:
        if not self._artifact:
            self.notify("nothing reaped yet", severity="warning")
            return
        self.push_screen(SaveScreen(f"{self.current_op.key}.md"), self._write_artifact)

    def _write_artifact(self, path: str | None) -> None:
        if not path:
            return
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._artifact, encoding="utf-8")
        self._status(f"wrote {target}")
        self.notify(f"interred at {target}")

    # -- worker callbacks (main thread) ------------------------------------

    def _show_result(self, key: str, text: str) -> None:
        self.query_one(ScytheSpinner).stop()
        self._artifact = text
        self.query_one("#preview", TextArea).text = text
        self._status(f"reaped {key} - {len(text.splitlines())} lines (s to save)")

    def _show_error(self, message: str) -> None:
        self.query_one(ScytheSpinner).stop()
        self._status(f"the ritual failed: {message}")
        self.notify(message, severity="error", title="the ritual failed")

    def _status(self, message: str) -> None:
        self.query_one("#status", Label).update(message)


def run_tui(source: str = ".") -> None:
    """Launch the TUI. Called by `reaper summon`."""
    ReaperApp(source=source).run()
