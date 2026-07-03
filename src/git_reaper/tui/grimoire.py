"""The Grimoire: compose a recipe visually, watch its incantation form.

Pick a ritual, fill the same option widgets the Altar renders, name the
thing, and the exact CLI twin updates live. Save inscribes it in .reaperrc
via the library (config.save_recipe), so `cast` runs it headless later --
this chamber kills "I never remember the nine flags" at its source.
"""

from __future__ import annotations

import shlex

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widget import AwaitMount
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Select,
    Switch,
)
from textual.widgets.option_list import Option

from git_reaper import config, incant
from git_reaper.config import GrimoireError
from git_reaper.models import Recipe
from git_reaper.tui.widgets import (
    HelpScreen,
    collect_option_values,
    mount_option_widgets,
)
from git_reaper.tui_ops import OPERATIONS, OPERATIONS_BY_KEY, Operation, incantation_argv

_HELP = (
    "[b]the grimoire[/b]\n"
    "compose a recipe: pick a ritual, tune its options, name it. the\n"
    "incantation line shows the exact CLI twin as you edit; save inscribes\n"
    "it in .reaperrc where `reaper cast <name>` (and the Altar) find it.\n\n"
    "  ctrl+s  save        ctrl+d  delete selected\n"
    "  escape  crypt map   ?  this help\n\n"
    "recipes living in pyproject.toml are shown but edited there by hand;\n"
    "saving here writes .reaperrc, which outranks pyproject."
)


class GrimoireScreen(Screen[None]):
    """The recipe builder: visual in, headless out."""

    BINDINGS = [
        ("ctrl+s", "save_recipe", "Save"),
        ("ctrl+d", "delete_recipe", "Delete"),
        ("question_mark", "help", "Help"),
        ("escape", "app.crypt", "Crypt map"),
        ("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.current_op: Operation = OPERATIONS[0]
        self._options_ready: AwaitMount | None = None
        self._recipes: list[Recipe] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body"):
            with Vertical(id="recipe-list"):
                yield Label("recipes", classes="heading")
                yield OptionList(id="recipes")
            with Vertical(id="main"):
                with Vertical(id="recipe-form"):
                    with Horizontal(classes="form-row"):
                        yield Label("name")
                        yield Input(placeholder="nightly-pack", id="recipe-name")
                    with Horizontal(classes="form-row"):
                        yield Label("description")
                        yield Input(placeholder="what this recipe is for", id="recipe-desc")
                    with Horizontal(classes="form-row"):
                        yield Label("ritual")
                        yield Select(
                            [(op.key, op.key) for op in OPERATIONS],
                            value=self.current_op.key,
                            allow_blank=False,
                            id="recipe-command",
                        )
                    with Horizontal(classes="form-row"):
                        yield Label("source")
                        yield Input(value=".", placeholder=". or a repo URL", id="recipe-source")
                yield VerticalScroll(id="options")
                yield Label("", id="incantation")
                with Horizontal(id="grimoire-buttons"):
                    yield Button("save (ctrl+s)", id="save", variant="primary")
                    yield Button("delete (ctrl+d)", id="delete")
                yield Label("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._build_options()
        self._load_recipes()
        self._refresh_incantation()

    def on_screen_resume(self) -> None:
        self.app.sub_title = "the grimoire"
        self._load_recipes()

    # -- the recipe list -----------------------------------------------------

    def _load_recipes(self) -> None:
        try:
            self._recipes = config.load_grimoire().recipes
        except GrimoireError as exc:
            self._recipes = []
            self._status(f"the grimoire is miswritten: {exc}")
        try:
            recipes = self.query_one("#recipes", OptionList)
        except NoMatches:
            return
        recipes.clear_options()
        recipes.add_option(Option("(new recipe)", id="new"))
        for i, recipe in enumerate(self._recipes):
            pin = "" if recipe.source == config.CONFIG_FILE else "  [dim](pyproject)[/dim]"
            recipes.add_option(Option(f"{recipe.name}{pin}", id=f"recipe:{i}"))

    @on(OptionList.OptionSelected, "#recipes")
    async def _recipe_picked(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        if event.option.id == "new":
            await self._fill_form(Recipe(name="", command=self.current_op.key, args=["."]))
            return
        await self._fill_form(self._recipes[int(event.option.id.split(":")[1])])

    async def _fill_form(self, recipe: Recipe) -> None:
        """Load a recipe into the form; its args parse through the same brain
        the console uses, so flags land on the exact widgets they map to."""
        self.query_one("#recipe-name", Input).value = recipe.name
        self.query_one("#recipe-desc", Input).value = recipe.description
        spell = incant.parse(shlex.join(["reaper", recipe.command, *recipe.args]))
        if spell.kind != "ritual" or spell.op is None:
            self._status(f"recipe {recipe.name!r} is not a chamber ritual; edit it by hand")
            return
        self.query_one("#recipe-command", Select).value = spell.op.key
        self.query_one("#recipe-source", Input).value = spell.source
        self._apply_operation(spell.op)
        if self._options_ready is not None:
            await self._options_ready  # the widgets must exist before the flags land
        self._apply_opts(dict(spell.opts))

    def _apply_opts(self, opts: dict[str, object]) -> None:
        for name, value in opts.items():
            try:
                widget = self.query_one(f"#opt-{name}")
            except NoMatches:
                continue
            if value is None:
                continue
            widget.value = value if isinstance(value, bool) else str(value)  # type: ignore[attr-defined]
        self._refresh_incantation()

    # -- the form ------------------------------------------------------------

    def _apply_operation(self, op: Operation) -> None:
        if op is not self.current_op:
            self.current_op = op
            self._build_options()
        self._refresh_incantation()

    def _build_options(self) -> None:
        panel = self.query_one("#options", VerticalScroll)
        self._options_ready = mount_option_widgets(panel, self.current_op)

    @on(Select.Changed, "#recipe-command")
    def _command_changed(self, event: Select.Changed) -> None:
        if event.value in OPERATIONS_BY_KEY:
            self._apply_operation(OPERATIONS_BY_KEY[event.value])

    @on(Input.Changed)
    @on(Select.Changed)
    @on(Switch.Changed)
    def _anything_changed(self) -> None:
        self._refresh_incantation()

    def _assemble(self) -> Recipe:
        """The recipe as the form stands: the ritual's true CLI argv."""
        source = self.query_one("#recipe-source", Input).value.strip() or "."
        opts = collect_option_values(self, self.current_op)
        args = incantation_argv(self.current_op, source, opts)
        return Recipe(
            name=self.query_one("#recipe-name", Input).value.strip(),
            command=self.current_op.key,
            args=args,
            description=self.query_one("#recipe-desc", Input).value.strip(),
        )

    def _refresh_incantation(self) -> None:
        try:
            recipe = self._assemble()
        except NoMatches:  # options panel is mid-rebuild
            return
        line = shlex.join(["reaper", recipe.command, *recipe.args])
        cast = f"reaper cast {recipe.name}" if recipe.name else "name it to cast it"
        self.query_one("#incantation", Label).update(f"{line}\n[dim]{cast}[/dim]")

    # -- save / delete ---------------------------------------------------------

    @on(Button.Pressed, "#save")
    def _save_button(self) -> None:
        self.action_save_recipe()

    @on(Button.Pressed, "#delete")
    def _delete_button(self) -> None:
        self.action_delete_recipe()

    def action_save_recipe(self) -> None:
        recipe = self._assemble()
        try:
            path = config.save_recipe(recipe)
        except GrimoireError as exc:
            self._status(str(exc))
            self.notify(str(exc), severity="error", title="not inscribed")
            return
        self._load_recipes()
        self._status(f"inscribed {recipe.name!r} in {path.name} - reaper cast {recipe.name}")
        self.notify(f"inscribed in {path.name}; cast it headless any time")

    def action_delete_recipe(self) -> None:
        name = self.query_one("#recipe-name", Input).value.strip()
        if not name:
            self._status("pick or name a recipe first")
            return
        try:
            config.delete_recipe(name)
        except GrimoireError as exc:
            self._status(str(exc))
            self.notify(str(exc), severity="error", title="not struck")
            return
        self._load_recipes()
        self._status(f"struck {name!r} from the grimoire")

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen(_HELP))

    def _status(self, message: str) -> None:
        self.query_one("#status", Label).update(message)
