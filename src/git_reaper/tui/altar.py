"""The Altar: run a ritual against one source. The original screen, kept.

The roomy ritual list, the option panel, the preview, the cursed badge --
one chamber among several now, but the same creed: pick, tune, reap on a
worker thread, save exactly what you see.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.timer import Timer
from textual.widget import AwaitMount
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Markdown,
    OptionList,
    Static,
    TextArea,
)
from textual.widgets.option_list import Option

from git_reaper import __version__
from git_reaper.config import GrimoireError, load_grimoire
from git_reaper.core.source import resolve_source
from git_reaper.gitio import default_backend
from git_reaper.models import Recipe
from git_reaper.tui.widgets import (
    BrowseScreen,
    HelpScreen,
    SaveScreen,
    ScytheSpinner,
    collect_option_values,
    mount_option_widgets,
)
from git_reaper.tui_ops import GROUPS, OPERATIONS, OPERATIONS_BY_KEY, Operation, ReapResult

_HELP = (
    "[b]the altar[/b]\n"
    "  r  reap        s  save        c  copy artifact\n"
    "  b  browse      /  focus source\n"
    "  m  raw/rendered markdown\n"
    "  d  ritual descriptions on/off\n"
    "  ctrl+p  palette (themes and chambers)\n"
    "  escape  crypt map\n"
    "  ?  this help   q  quit\n\n"
    "[b]rituals[/b]\n"
    "{groups}\n\n"
    "rituals marked * need a real repo; plain folders get a clear error."
)


class AltarScreen(Screen[None]):
    """Run-a-ritual: the Sanctum's original chamber."""

    BINDINGS = [
        ("r", "reap", "Reap"),
        ("s", "save", "Save"),
        ("c", "copy", "Copy"),
        ("b", "browse", "Browse"),
        ("slash", "focus_source", "Source"),
        ("m", "toggle_rendered", "Raw/rendered"),
        ("d", "toggle_descriptions", "Descriptions"),
        ("question_mark", "help", "Help"),
        ("escape", "app.crypt", "Crypt map"),
        ("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.current_op: Operation = OPERATIONS[0]
        self._artifact: str = ""
        self._last_format: str = "md"
        self._rendered: bool = False
        self._recipes: list[Recipe] = []
        self._inspect_timer: Timer | None = None
        self._show_descriptions: bool = False
        self._options_ready: AwaitMount | None = None
        self._is_repo: bool = True  # last inspected source; repopulating regrays from this

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="source-row"):
            yield Input(placeholder="path or repo URL", id="source")
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
        self.query_one("#source", Input).value = self.app.source  # type: ignore[attr-defined]
        self._populate_operations()
        self._build_options()
        self._load_recipes()
        self._inspect_source(self.query_one("#source", Input).value)

    def on_screen_resume(self) -> None:
        self.app.sub_title = "the altar"
        self._load_recipes()  # the Grimoire may have inscribed new ones

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
                    # name on one line, dimmed description beneath -- room to breathe.
                    # `d` collapses the list back to names only.
                    prompt = f"  {op.key}{mark}"
                    if self._show_descriptions:
                        prompt += f"\n  [dim]{op.description}[/dim]"
                    ops.add_option(Option(prompt, id=op.key))

    def _load_recipes(self) -> None:
        try:
            self._recipes = load_grimoire().recipes
        except GrimoireError:
            self._recipes = []
        try:
            recipes = self.query_one("#recipes", OptionList)
        except NoMatches:  # resume can fire before compose settles
            return
        recipes.clear_options()
        if not self._recipes:
            recipes.add_option(Option("(no recipes inscribed)", disabled=True))
            return
        for i, recipe in enumerate(self._recipes):
            line = " ".join(["reaper", recipe.command, *recipe.args])
            recipes.add_option(Option(f"{recipe.name}: {line}", id=f"recipe:{i}"))

    # -- options panel -----------------------------------------------------

    def _build_options(self) -> None:
        panel = self.query_one("#options", VerticalScroll)
        self._options_ready = mount_option_widgets(panel, self.current_op)

    def _collect_opts(self) -> dict[str, Any]:
        return collect_option_values(self, self.current_op)

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
    async def _recipe_selected(self, event: OptionList.OptionSelected) -> None:
        if not self._recipes or event.option.id is None:
            return
        recipe = self._recipes[int(event.option.id.split(":")[1])]
        source = next((a for a in recipe.args if not a.startswith("-")), ".")
        self.query_one("#source", Input).value = source
        if recipe.command in OPERATIONS_BY_KEY:
            self.set_operation(recipe.command)
            if self._options_ready is not None:
                await self._options_ready  # the panel must exist before the flags land
            self._apply_recipe_options(recipe)
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
        self.app.source = event.value.strip() or "."  # type: ignore[attr-defined]
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
            self.app.call_from_thread(self._show_source_state, f"no such path: {source}", False)
            return
        is_repo = default_backend().is_repo(path)
        note = "git repo" if is_repo else "plain folder (history rituals will fail)"
        self.app.call_from_thread(self._show_source_state, note, is_repo)

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
        self._is_repo = is_repo
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

    def action_toggle_descriptions(self) -> None:
        """Flip the rituals list between roomy (name + description) and compact."""
        self._show_descriptions = not self._show_descriptions
        current = self.current_op.key
        self._populate_operations()
        ops = self.query_one("#operations", OptionList)
        for index in range(ops.option_count):
            if ops.get_option_at_index(index).id == current:
                ops.highlighted = index
                break
        self._apply_git_state(self._is_repo)

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
            self.app.call_from_thread(self.query_one(ScytheSpinner).stage, f"reaping {op.key}")
            result = op.run(resolved.repo, opts)
        except Exception as exc:  # surface the plain cause; never hide it
            self.app.call_from_thread(self._show_error, str(exc))
            return
        self.app.call_from_thread(self._show_result, op.key, result, opts.get("format", "md"))

    def action_browse(self) -> None:
        current = self.query_one("#source", Input).value.strip() or "."
        self.app.push_screen(BrowseScreen(current), self._chose_source)

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
        self.app.copy_to_clipboard(self._artifact)
        self.notify("artifact copied to the clipboard")

    def action_help(self) -> None:
        groups = "\n".join(
            f"  {g}: " + ", ".join(op.key for op in OPERATIONS if op.group == g) for g in GROUPS
        )
        self.app.push_screen(HelpScreen(_HELP.format(groups=groups)))

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
        self.app.push_screen(SaveScreen(f"{self.current_op.key}{ext}"), self._write_artifact)

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
