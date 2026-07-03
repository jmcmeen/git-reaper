"""Shared Sanctum furniture: the theme, the spinner, modals, option panels.

Every chamber borrows from here so the Sanctum feels like one building:
the same Dracula hues, the same scythe while a worker runs, the same save
dialog, and the same option widgets the Altar and the Grimoire both render
from a ritual's textual-free OptSpec tuple.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.timer import Timer
from textual.widget import AwaitMount, Widget
from textual.widgets import Button, DirectoryTree, Input, Label, Select, Static, Switch

from git_reaper import art
from git_reaper.tui_ops import ChoiceOpt, NumberOpt, Operation, ToggleOpt

_SCYTHE = art.SCYTHE_FRAMES

#: Dracula, mapped onto the reaper's semantic tokens (see theme.py's PALETTE:
#: eldritch->primary purple, necro->success green, blood->error red,
#: ember->warning orange, plus Dracula cyan/yellow as accent variables).
REAPER_DRACULA = Theme(
    name="reaper-dracula",
    primary="#BD93F9",  # eldritch
    secondary="#6272A4",
    accent="#FF79C6",  # pink
    success="#50FA7B",  # necro
    warning="#FFB86C",  # ember
    error="#FF5555",  # blood
    foreground="#F8F8F2",  # bone
    background="#282A36",
    surface="#2B2E3B",
    panel="#313442",
    dark=True,
    variables={
        "cursed": "#FF5555",
        "omen": "#F1FA8C",  # dracula yellow
        "scythe": "#8BE9FD",  # dracula cyan
        "block-cursor-foreground": "#282A36",
    },
)


class ScytheSpinner(Static):
    """A tiny reaping animation with a stage caption, shown while a worker runs."""

    _timer: Timer | None = None

    def on_mount(self) -> None:
        self._i = 0
        self._stage = "reaping"
        self._timer = None
        self.display = False

    def start(self, stage: str = "reaping") -> None:
        self._i = 0
        self._stage = stage
        self.display = True
        if self._timer is None:
            self._timer = self.set_interval(0.08, self._tick)

    def stage(self, stage: str) -> None:
        self._stage = stage

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.display = False

    def _tick(self) -> None:
        self._i = (self._i + 1) % len(_SCYTHE)
        self.update(f"[$scythe]{_SCYTHE[self._i]}[/] {self._stage} ...")


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


class BrowseScreen(ModalScreen[str | None]):
    """A directory tree to pick a local source. Returns the path, or None."""

    def __init__(self, start: str = ".") -> None:
        super().__init__()
        self._start = start if Path(start).is_dir() else "."

    def compose(self) -> ComposeResult:
        with Vertical(id="browse"):
            yield Label("choose a crypt to reap:")
            yield DirectoryTree(self._start, id="tree")
            with Horizontal(id="dialog-buttons"):
                yield Button("cancel", id="cancel")

    @on(DirectoryTree.DirectorySelected)
    def _picked(self, event: DirectoryTree.DirectorySelected) -> None:
        self.dismiss(str(event.path))

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    """A chamber's cheatsheet; each chamber brings its own body text."""

    BINDINGS = [("escape,q,question_mark", "dismiss", "Close")]

    def __init__(self, body: str) -> None:
        super().__init__()
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical(id="help"):
            yield Static(self._body, id="help-body")
            yield Button("close", id="close", variant="primary")

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()


# --------------------------------------------------------------------------
# option panels -- the Altar and the Grimoire render the same OptSpec widgets
# --------------------------------------------------------------------------


def mount_option_widgets(panel: VerticalScroll, op: Operation) -> AwaitMount:
    """Rebuild an options panel from a ritual's OptSpec tuple.

    Returns the mount awaitable so callers that must touch the widgets right
    after (the Altar applying a recipe's flags) can await instead of racing.
    """
    panel.remove_children()
    if not op.options:
        return panel.mount(Label("no options for this ritual", classes="opt-row"))
    rows: list[Horizontal] = []
    for spec in op.options:
        if isinstance(spec, ToggleOpt):
            row = Horizontal(
                Switch(value=spec.default, id=f"opt-{spec.name}"),
                Label(spec.label),
                classes="opt-toggle",
            )
        elif isinstance(spec, ChoiceOpt):
            row = Horizontal(
                Label(spec.label),
                Select(
                    [(c, c) for c in spec.choices],
                    value=spec.default,
                    allow_blank=False,
                    id=f"opt-{spec.name}",
                ),
                classes="opt-row",
            )
        else:  # NumberOpt or TextOpt
            default = "" if getattr(spec, "default", None) is None else str(spec.default)
            row = Horizontal(
                Label(spec.label),
                Input(
                    value=default,
                    type="integer" if isinstance(spec, NumberOpt) else "text",
                    id=f"opt-{spec.name}",
                ),
                classes="opt-row",
            )
        rows.append(row)
    return panel.mount(*rows)


def collect_option_values(root: Widget, op: Operation) -> dict[str, Any]:
    """Read the mounted option widgets back into a plain dict for a worker."""
    opts: dict[str, Any] = {}
    for spec in op.options:
        widget = root.query_one(f"#opt-{spec.name}")
        value = widget.value  # type: ignore[attr-defined]
        if isinstance(spec, NumberOpt):
            text = str(value).strip()
            opts[spec.name] = int(text) if text.lstrip("-").isdigit() else None
        else:
            opts[spec.name] = value
    return opts
