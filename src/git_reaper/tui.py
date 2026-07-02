"""The Summoning: a Textual TUI over the same core the CLI drives.

Thin adapter, same creed as the CLI: pick a source and a ritual, tune its
options, and the core does the work (on a thread, never blocking the event
loop). The rendered artifact fills the preview; save writes exactly what you
see. Textual is only imported here, so the base install stays lean; `reaper
summon` reports the missing `[tui]` extra clearly.

Dressed in a bespoke `reaper-dracula` theme by default (Dracula hues mapped
onto the reaper's spooky tokens). Ctrl+P opens Textual's command palette to
switch themes live.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.timer import Timer
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    Markdown,
    OptionList,
    Select,
    Static,
    Switch,
    TextArea,
)
from textual.widgets.option_list import Option

from git_reaper import __version__, art
from git_reaper.config import GrimoireError, load_grimoire
from git_reaper.core.source import resolve_source
from git_reaper.gitio import default_backend
from git_reaper.models import Recipe
from git_reaper.tui_ops import (
    GROUPS,
    OPERATIONS,
    OPERATIONS_BY_KEY,
    ChoiceOpt,
    NumberOpt,
    Operation,
    ReapResult,
    ToggleOpt,
)

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
    """The keybinding and ritual-group cheatsheet."""

    BINDINGS = [("escape,q,question_mark", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        groups = "\n".join(
            f"  {g}: " + ", ".join(op.key for op in OPERATIONS if op.group == g) for g in GROUPS
        )
        body = (
            "[b]keys[/b]\n"
            "  r  reap        s  save        c  copy artifact\n"
            "  b  browse      /  focus source\n"
            "  m  raw/rendered markdown\n"
            "  ctrl+p  themes (dracula and friends)\n"
            "  ?  this help   q  quit\n\n"
            "[b]rituals[/b]\n"
            f"{groups}\n\n"
            "rituals marked for git need a real repo; plain folders get a clear error."
        )
        with Vertical(id="help"):
            yield Static(body, id="help-body")
            yield Button("close", id="close", variant="primary")

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()


class ReaperApp(App[None]):
    """The reaper's interactive face."""

    TITLE = "git-reaper"
    CSS = """
    #source-row { dock: top; height: 3; margin: 0 1; }
    #source { width: 1fr; }
    #browse-btn { width: 10; margin-left: 1; }
    #source-hint { dock: top; height: 1; color: $text-muted; padding: 0 2; }
    #body { height: 1fr; }
    #sidebar { width: 42; border-right: solid $primary; }
    #operations { height: 1fr; }
    #recipes { height: 8; }
    #main { height: 1fr; }
    #ritual-name { height: 1; color: $primary; text-style: bold; padding: 0 1; }
    #options { height: auto; max-height: 12; border: round $primary; margin: 0 1; padding: 0 1; }
    .opt-row { height: 3; }
    .opt-row Label { width: 26; padding: 1 0 0 0; }
    .opt-toggle { height: 3; }
    .opt-toggle Label { width: 1fr; padding: 1 0 0 1; }
    #preview { height: 1fr; border: round $primary; }
    #rendered { height: 1fr; border: round $primary; display: none; }
    #spinner { height: 1; color: $warning; padding: 0 1; }
    #statusbar { height: 1; padding: 0 1; }
    #status { width: 1fr; color: $text-muted; }
    #badge { color: $background; background: $error; text-style: bold; padding: 0 1; display: none }
    .heading { text-style: bold; padding: 1 1 0 1; }
    #reap { margin: 1 1; width: 100%; }
    #dialog { padding: 1 2; width: 64; height: auto; border: round $primary; background: $surface; }
    #browse { padding: 1 2; width: 80; height: 30; border: round $primary; background: $surface; }
    #help { padding: 1 2; width: 76; height: auto; border: round $primary; background: $surface; }
    #tree { height: 1fr; }
    """
    BINDINGS = [
        ("r", "reap", "Reap"),
        ("s", "save", "Save"),
        ("c", "copy", "Copy"),
        ("b", "browse", "Browse"),
        ("slash", "focus_source", "Source"),
        ("m", "toggle_rendered", "Raw/rendered"),
        ("question_mark", "help", "Help"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, source: str = ".") -> None:
        super().__init__()
        self._initial_source = source
        self.current_op: Operation = OPERATIONS[0]
        self._artifact: str = ""
        self._last_format: str = "md"
        self._rendered: bool = False
        self._recipes: list[Recipe] = []
        self._inspect_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="source-row"):
            yield Input(value=self._initial_source, placeholder="path or repo URL", id="source")
            yield Button("browse", id="browse-btn")
        yield Label("", id="source-hint")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Label("rituals", classes="heading")
                yield OptionList(id="operations")
                yield Label("recipes", classes="heading")
                yield OptionList(id="recipes")
                yield Button("Reap (r)", id="reap", variant="primary")
            with Vertical(id="main"):
                yield Label(self.current_op.label, id="ritual-name")
                yield VerticalScroll(id="options")
                yield TextArea("", id="preview", read_only=True)
                yield Markdown("", id="rendered")
                # progress and status both report below the output, never above it
                yield ScytheSpinner("", id="spinner")
                with Horizontal(id="statusbar"):
                    yield Label(f"git-reaper {__version__} - pick a ritual and reap", id="status")
                    yield Static("", id="badge")
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(REAPER_DRACULA)
        self.theme = "reaper-dracula"
        self._populate_operations()
        self._build_options()
        self._load_recipes()
        self._inspect_source(self._initial_source)

    # -- ritual list -------------------------------------------------------

    def _populate_operations(self) -> None:
        """Group the rituals under disabled section headers."""
        ops = self.query_one("#operations", OptionList)
        ops.clear_options()
        for group in GROUPS:
            ops.add_option(Option(f"-- {group} --", disabled=True))
            for op in OPERATIONS:
                if op.group == group:
                    mark = " *" if op.needs_git else ""
                    ops.add_option(Option(f"  {op.label}{mark}", id=op.key))

    def _load_recipes(self) -> None:
        try:
            self._recipes = load_grimoire().recipes
        except GrimoireError:
            self._recipes = []
        recipes = self.query_one("#recipes", OptionList)
        recipes.clear_options()
        if not self._recipes:
            recipes.add_option(Option("(no recipes inscribed)", disabled=True))
            return
        for i, recipe in enumerate(self._recipes):
            line = " ".join(["reaper", recipe.command, *recipe.args])
            recipes.add_option(Option(f"{recipe.name}: {line}", id=f"recipe:{i}"))

    # -- options panel -----------------------------------------------------

    def _build_options(self) -> None:
        """Rebuild the options panel for the current ritual."""
        panel = self.query_one("#options", VerticalScroll)
        panel.remove_children()
        if not self.current_op.options:
            panel.mount(Label("no options - reap with r", classes="opt-row"))
            return
        for spec in self.current_op.options:
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
            panel.mount(row)

    def _collect_opts(self) -> dict[str, Any]:
        """Read the current option widgets into a plain dict for the worker."""
        opts: dict[str, Any] = {}
        for spec in self.current_op.options:
            widget = self.query_one(f"#opt-{spec.name}")
            value = widget.value  # type: ignore[attr-defined]
            if isinstance(spec, NumberOpt):
                text = str(value).strip()
                opts[spec.name] = int(text) if text.lstrip("-").isdigit() else None
            else:
                opts[spec.name] = value
        return opts

    # -- selection ---------------------------------------------------------

    def _apply_operation(self, op: Operation) -> None:
        """Make `op` the current ritual and rebuild its options panel. Does not
        move the list highlight (the caller may already be on it)."""
        if op is self.current_op:
            return
        self.current_op = op
        self._build_options()
        self.query_one("#ritual-name", Label).update(op.label)

    def set_operation(self, key: str) -> None:
        """Select a ritual by key, rebuild its options, and move the highlight
        onto it (which itself applies it, via the highlight handler)."""
        ops = self.query_one("#operations", OptionList)
        for index in range(ops.option_count):
            if ops.get_option_at_index(index).id == key:
                ops.highlighted = index
                break
        self._apply_operation(OPERATIONS_BY_KEY[key])

    @on(OptionList.OptionHighlighted, "#operations")
    def _op_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        # Arrow keys move the highlight; that alone selects the ritual -- no
        # Enter required. Group headers carry no id and are skipped.
        if event.option is not None and event.option.id is not None:
            self._apply_operation(OPERATIONS_BY_KEY[event.option.id])

    @on(OptionList.OptionSelected, "#operations")
    def _op_selected(self, event: OptionList.OptionSelected) -> None:
        key = event.option.id
        if key is not None:
            self._apply_operation(OPERATIONS_BY_KEY[key])

    @on(OptionList.OptionSelected, "#recipes")
    def _recipe_selected(self, event: OptionList.OptionSelected) -> None:
        if not self._recipes or event.option.id is None:
            return
        recipe = self._recipes[int(event.option.id.split(":")[1])]
        source = next((a for a in recipe.args if not a.startswith("-")), ".")
        self.query_one("#source", Input).value = source
        if recipe.command in OPERATIONS_BY_KEY:
            self.set_operation(recipe.command)
            # the options panel mounts on the next refresh; apply flags after it.
            self.call_after_refresh(self._apply_recipe_options, recipe)
        incantation = " ".join(["reaper", recipe.command, *recipe.args])
        self._status(f"loaded {recipe.name}: {incantation}  (press r to reap)")

    def _apply_recipe_options(self, recipe: Recipe) -> None:
        """Best-effort: map a recipe's flags onto the options panel widgets."""
        flags = {
            "--limit": "limit",
            "-n": "limit",
            "--lens": "lens",
            "--than": "than",
            "--min-size": "min_size",
            "--format": "format",
            "-f": "format",
        }
        toggles = {
            "--heatmap": "heatmap",
            "--changelog": "changelog",
            "--age": "age",
            "--no-entropy": "no_entropy",
            "--offline": "offline",
        }
        names = {spec.name for spec in self.current_op.options}
        args = recipe.args
        for i, arg in enumerate(args):
            if arg in toggles and toggles[arg] in names:
                self._set_opt_widget(toggles[arg], True)
            elif arg in flags and flags[arg] in names and i + 1 < len(args):
                self._set_opt_widget(flags[arg], args[i + 1])

    def _set_opt_widget(self, name: str, value: Any) -> None:
        # a recipe flag that does not fit its widget (bad value, wrong type) is
        # harmless -- the panel keeps its default and the incantation still shows.
        with contextlib.suppress(Exception):
            self.query_one(f"#opt-{name}").value = value  # type: ignore[attr-defined]

    @on(Button.Pressed, "#reap")
    def _reap_button(self) -> None:
        self.action_reap()

    @on(Button.Pressed, "#browse-btn")
    def _browse_button(self) -> None:
        self.action_browse()

    # -- source inspector --------------------------------------------------

    @on(Input.Changed, "#source")
    def _source_changed(self, event: Input.Changed) -> None:
        if self._inspect_timer is not None:
            self._inspect_timer.stop()
        self._inspect_timer = self.set_timer(0.4, lambda: self._inspect_source(event.value))

    def _inspect_source(self, source: str) -> None:
        source = source.strip()
        try:
            hint = self.query_one("#source-hint", Label)
        except NoMatches:  # a modal is up, or the app is tearing down
            return
        if not source or "://" in source or "@" in source:
            hint.update("remote source - will clone into the catacombs on reap" if source else "")
            self._apply_git_state(True)
            return
        self._inspect_worker(source)

    @work(thread=True, exclusive=True, group="inspect")
    def _inspect_worker(self, source: str) -> None:
        path = Path(source).expanduser()
        if not path.exists():
            self.call_from_thread(self._show_source_state, f"no such path: {source}", False)
            return
        is_repo = default_backend().is_repo(path)
        note = "git repo" if is_repo else "plain folder (history rituals will fail)"
        self.call_from_thread(self._show_source_state, note, is_repo)

    def _show_source_state(self, note: str, is_repo: bool) -> None:
        # a thread callback can land after a modal opens or the app stops;
        # if the base screen's widgets are gone, quietly skip.
        try:
            self.query_one("#source-hint", Label).update(note)
        except NoMatches:
            return
        self._apply_git_state(is_repo)

    def _apply_git_state(self, is_repo: bool) -> None:
        """Gray out git-only rituals when the source is not a repo. Preserves
        the current highlight, so graying never changes the selected ritual."""
        try:
            ops = self.query_one("#operations", OptionList)
        except NoMatches:
            return
        keep = ops.highlighted
        for op in OPERATIONS:
            if not op.needs_git:
                continue
            try:
                if is_repo:
                    ops.enable_option(op.key)
                else:
                    ops.disable_option(op.key)
            except Exception:  # older Textual without per-option enable/disable
                return
        if keep is not None and ops.highlighted != keep:
            ops.highlighted = keep

    # -- actions -----------------------------------------------------------

    def action_reap(self) -> None:
        source = self.query_one("#source", Input).value.strip() or "."
        opts = self._collect_opts()  # read widgets on the main thread
        self.query_one(ScytheSpinner).start(f"summoning from {source}")
        self._badge_off()
        self._status(f"reaping {self.current_op.key} from {source} ...")
        self._reap_worker(source, self.current_op, opts)

    @work(thread=True, exclusive=True)
    def _reap_worker(self, source: str, op: Operation, opts: dict[str, Any]) -> None:
        try:
            resolved = resolve_source(source, depth=None)
            self.call_from_thread(self.query_one(ScytheSpinner).stage, f"reaping {op.key}")
            result = op.run(resolved.repo, opts)
        except Exception as exc:  # surface the plain cause; never hide it
            self.call_from_thread(self._show_error, str(exc))
            return
        self.call_from_thread(self._show_result, op.key, result, opts.get("format", "md"))

    def action_browse(self) -> None:
        current = self.query_one("#source", Input).value.strip() or "."
        self.push_screen(BrowseScreen(current), self._chose_source)

    def _chose_source(self, path: str | None) -> None:
        if path:
            self.query_one("#source", Input).value = path
            self._inspect_source(path)

    def action_focus_source(self) -> None:
        self.query_one("#source", Input).focus()

    def action_copy(self) -> None:
        if not self._artifact:
            self.notify("nothing reaped yet", severity="warning")
            return
        self.copy_to_clipboard(self._artifact)
        self.notify("artifact copied to the clipboard")

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_toggle_rendered(self) -> None:
        if self._last_format != "md":
            self.notify("rendered view is for markdown; this artifact is raw", severity="warning")
            return
        self._rendered = not self._rendered
        self._show_preview()

    def action_save(self) -> None:
        if not self._artifact:
            self.notify("nothing reaped yet", severity="warning")
            return
        ext = {"md": ".md", "json": ".json", "csv": ".csv", "html": ".html"}.get(
            self._last_format, ".md"
        )
        self.push_screen(SaveScreen(f"{self.current_op.key}{ext}"), self._write_artifact)

    def _write_artifact(self, path: str | None) -> None:
        if not path:
            return
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._artifact, encoding="utf-8")
        self._status(f"wrote {target}")
        self.notify(f"interred at {target}")

    # -- worker callbacks (main thread) ------------------------------------

    def _show_result(self, key: str, result: ReapResult, fmt: str) -> None:
        self.query_one(ScytheSpinner).stop()
        self._artifact = result.text
        self._last_format = fmt
        self._rendered = False
        self._show_preview()
        self._status(f"reaped {key} - {result.summary} (s to save)")
        if result.cursed:
            self._badge_on(result.summary)
        else:
            self._badge_off()

    def _show_preview(self) -> None:
        raw = self.query_one("#preview", TextArea)
        rendered = self.query_one("#rendered", Markdown)
        if self._rendered:
            rendered.update(self._artifact)
            rendered.display = True
            raw.display = False
        else:
            raw.text = self._artifact
            raw.display = True
            rendered.display = False

    def _show_error(self, message: str) -> None:
        self.query_one(ScytheSpinner).stop()
        self._badge_off()
        self._status(f"the ritual failed: {message}")
        self.notify(message, severity="error", title="the ritual failed")

    def _status(self, message: str) -> None:
        self.query_one("#status", Label).update(message)

    def _badge_on(self, summary: str) -> None:
        badge = self.query_one("#badge", Static)
        badge.update(f"CURSED - {summary}")
        badge.display = True

    def _badge_off(self) -> None:
        self.query_one("#badge", Static).display = False


def run_tui(source: str = ".") -> None:
    """Launch the TUI. Called by `reaper summon`."""
    ReaperApp(source=source).run()
