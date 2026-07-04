"""The Coven: compose a rite visually, step by step, and run the whole chain.

Where the Grimoire composes one recipe, the Coven composes a rite: an
ordered list of steps, each a ritual tuned with the same option widgets the
Altar and Grimoire render. Save inscribes it in .reaperrc via the library
(config.save_rite), so `reaper perform <name>` runs it headless later --
just like a recipe and `cast`, one dimension wider.

Running here does *not* go through `reaper perform` -- that shells each step
through the Typer app with stdout/stderr swapped process-wide, which would
race a live Textual render. Instead each step runs the same way the Altar
runs one ritual: op.run(resolved_repo, opts), straight in a worker thread.
A saved step's args still carry the literal `{source}` token (via
incantation_argv), so the *headless* twin (`reaper perform`) works exactly
as composed; the "run" button here just substitutes the real source before
resolving, per source, and never touches the CLI's stdout capture at all.
"""

from __future__ import annotations

import contextlib
import shlex

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widget import AwaitMount
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Select,
    Switch,
    TextArea,
)
from textual.widgets.option_list import Option

from git_reaper import config, incant
from git_reaper.config import GrimoireError
from git_reaper.core.source import resolve_source
from git_reaper.models import Rite, RiteStep
from git_reaper.rite import ELIGIBLE_STEP_COMMANDS, SOURCE_PLACEHOLDER
from git_reaper.tui.widgets import (
    HelpScreen,
    ScytheSpinner,
    collect_option_values,
    mount_option_widgets,
)
from git_reaper.tui_ops import OPERATIONS, Operation, incantation_argv

#: Only rituals whose CLI output a rite step can capture (--format json,
#: --out) can join a chain -- the same gate `reaper perform` enforces.
RITE_OPERATIONS: list[Operation] = [op for op in OPERATIONS if op.key in ELIGIBLE_STEP_COMMANDS]
RITE_OPERATIONS_BY_KEY: dict[str, Operation] = {op.key: op for op in RITE_OPERATIONS}

_HELP = (
    "[b]the coven[/b]\n"
    "compose a rite: an ordered chain of rituals. add steps, tune each\n"
    "one's options, name the rite, and run it against one or more sources\n"
    "(comma or space separated) to see the whole chain's outcome.\n\n"
    "  ctrl+s  save        ctrl+d  delete selected\n"
    "  ctrl+r  run         ?  this help\n"
    "  escape  crypt map   q  quit\n\n"
    "rites living in pyproject.toml are shown but edited there by hand;\n"
    "saving here writes .reaperrc, which outranks pyproject. running here\n"
    "previews live; `reaper perform <name>` is the headless twin."
)


def _default_step(op: Operation) -> RiteStep:
    """A fresh step: the ritual's defaults, source baked as the placeholder
    so the stored step is immediately valid for `reaper perform`."""
    return RiteStep(command=op.key, args=incantation_argv(op, SOURCE_PLACEHOLDER, op.defaults()))


class CovenScreen(Screen[None]):
    """The rite builder: visual in, headless out, previewable in place."""

    BINDINGS = [
        ("ctrl+s", "save_rite", "Save"),
        ("ctrl+d", "delete_rite", "Delete"),
        ("ctrl+r", "run", "Run"),
        ("question_mark", "help", "Help"),
        ("escape", "app.crypt", "Crypt map"),
        ("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.current_op: Operation = RITE_OPERATIONS[0]
        self._options_ready: AwaitMount | None = None
        self._rites: list[Rite] = []
        self._steps: list[RiteStep] = []
        self._step_index: int | None = None
        self._rite_running = False
        self._artifacts: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body"):
            with Vertical(id="rite-list"):
                yield Label("rites", classes="heading")
                yield OptionList(id="rites")
            with VerticalScroll(id="main"):
                with Horizontal(classes="form-row"):
                    yield Label("name")
                    yield Input(placeholder="audit", id="rite-name")
                with Horizontal(classes="form-row"):
                    yield Label("description")
                    yield Input(placeholder="what this rite is for", id="rite-desc")
                with Horizontal(classes="form-row"):
                    yield Label("sources")
                    yield Input(
                        value=".", placeholder=". or repo-a, repo-b (run only)", id="rite-sources"
                    )
                with Horizontal(id="steps-row"):
                    with Vertical(id="steps-panel"):
                        yield Label("steps", classes="heading")
                        yield OptionList(id="steps")
                        with Horizontal(id="step-buttons"):
                            yield Button("+ add", id="step-add")
                            yield Button("remove", id="step-remove")
                            yield Button("up", id="step-up")
                            yield Button("down", id="step-down")
                    with Vertical(id="step-form"):
                        with Horizontal(classes="form-row"):
                            yield Label("ritual")
                            yield Select(
                                [(op.key, op.key) for op in RITE_OPERATIONS],
                                value=self.current_op.key,
                                allow_blank=False,
                                id="step-command",
                            )
                        with Horizontal(classes="form-row"):
                            yield Label("step name")
                            yield Input(placeholder="optional label", id="step-name")
                        yield VerticalScroll(id="options")
                yield Label("", id="rite-incantation")
                with Horizontal(id="coven-buttons"):
                    yield Button("save (ctrl+s)", id="save", variant="primary")
                    yield Button("delete (ctrl+d)", id="delete")
                    yield Button("run (ctrl+r)", id="run")
                yield ScytheSpinner("", id="spinner")
                yield Label("", id="status")
                yield DataTable(id="results", cursor_type="row")
                yield TextArea("", id="results-preview", read_only=True)
        yield Footer()

    async def on_mount(self) -> None:
        table = self.query_one("#results", DataTable)
        for column in ("source", "step", "fate", "summary"):
            table.add_column(column, key=column)
        self._load_rites()
        if self._rites:
            await self._load_rite(self._rites[0])
        else:
            await self._new_rite()

    def on_screen_resume(self) -> None:
        self.app.sub_title = "the coven"
        self._load_rites()

    # -- the rite list ---------------------------------------------------------

    def _load_rites(self) -> None:
        try:
            self._rites = config.load_grimoire().rites
        except GrimoireError as exc:
            self._rites = []
            self._status(f"the grimoire is miswritten: {exc}")
        try:
            rites = self.query_one("#rites", OptionList)
        except NoMatches:
            return
        rites.clear_options()
        rites.add_option(Option("(new rite)", id="new"))
        for i, r in enumerate(self._rites):
            pin = "" if r.source == config.CONFIG_FILE else "  [dim](pyproject)[/dim]"
            rites.add_option(Option(f"{r.name}{pin}", id=f"rite:{i}"))

    @on(OptionList.OptionSelected, "#rites")
    async def _rite_picked(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        if event.option.id == "new":
            await self._new_rite()
            return
        await self._load_rite(self._rites[int(event.option.id.split(":")[1])])

    async def _new_rite(self) -> None:
        self.query_one("#rite-name", Input).value = ""
        self.query_one("#rite-desc", Input).value = ""
        self.query_one("#rite-sources", Input).value = "."
        self._steps = [_default_step(RITE_OPERATIONS[0])]
        await self._load_steps(select=0)

    async def _load_rite(self, a_rite: Rite) -> None:
        self.query_one("#rite-name", Input).value = a_rite.name
        self.query_one("#rite-desc", Input).value = a_rite.description
        self.query_one("#rite-sources", Input).value = "."
        self._steps = list(a_rite.steps)
        await self._load_steps(select=0 if a_rite.steps else None)

    async def _load_steps(self, select: int | None) -> None:
        self._step_index = None
        self._refresh_steps_list()
        if select is not None and self._steps:
            await self._select_step(select)
        else:
            self._clear_step_form()
        self._refresh_incantation()

    # -- the step list -----------------------------------------------------

    def _refresh_steps_list(self) -> None:
        steps = self.query_one("#steps", OptionList)
        steps.clear_options()
        for i, step in enumerate(self._steps):
            steps.add_option(Option(f"{i + 1}. {step.name or step.command}", id=f"step:{i}"))
        if self._step_index is not None and 0 <= self._step_index < len(self._steps):
            steps.highlighted = self._step_index

    @on(OptionList.OptionSelected, "#steps")
    async def _step_picked(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        self._sync_current_step()
        await self._select_step(int(event.option.id.split(":")[1]))

    async def _select_step(self, index: int) -> None:
        self._step_index = index
        with contextlib.suppress(NoMatches):
            self.query_one("#steps", OptionList).highlighted = index
        await self._apply_step(self._steps[index])

    async def _apply_step(self, step: RiteStep) -> None:
        """Load a step into the form; its args parse through the same brain
        the console uses, so flags land on the exact widgets they map to."""
        op = RITE_OPERATIONS_BY_KEY.get(step.command, RITE_OPERATIONS[0])
        self.current_op = op
        self.query_one("#step-command", Select).value = op.key
        self.query_one("#step-name", Input).value = step.name
        self._build_step_options()
        if self._options_ready is not None:
            await self._options_ready  # the widgets must exist before the flags land
        spell = incant.parse(shlex.join(["reaper", step.command, *step.args]))
        if spell.kind == "ritual":
            self._apply_opts(dict(spell.opts))
        else:
            self._refresh_incantation()

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

    def _clear_step_form(self) -> None:
        self.query_one("#step-name", Input).value = ""
        self.query_one("#options", VerticalScroll).remove_children()

    @on(Button.Pressed, "#step-add")
    async def _add_step_button(self) -> None:
        self._sync_current_step()
        self._steps.append(_default_step(RITE_OPERATIONS[0]))
        self._refresh_steps_list()
        await self._select_step(len(self._steps) - 1)

    @on(Button.Pressed, "#step-remove")
    async def _remove_step_button(self) -> None:
        if self._step_index is None or not self._steps:
            return
        del self._steps[self._step_index]
        if self._steps:
            await self._load_steps(select=min(self._step_index, len(self._steps) - 1))
        else:
            await self._load_steps(select=None)

    @on(Button.Pressed, "#step-up")
    def _move_step_up(self) -> None:
        self._swap_step(-1)

    @on(Button.Pressed, "#step-down")
    def _move_step_down(self) -> None:
        self._swap_step(1)

    def _swap_step(self, delta: int) -> None:
        if self._step_index is None:
            return
        self._sync_current_step()
        target = self._step_index + delta
        if not (0 <= target < len(self._steps)):
            return
        self._steps[self._step_index], self._steps[target] = (
            self._steps[target],
            self._steps[self._step_index],
        )
        self._step_index = target
        self._refresh_steps_list()
        self._refresh_incantation()

    # -- the step form -------------------------------------------------------

    def _build_step_options(self) -> None:
        panel = self.query_one("#options", VerticalScroll)
        self._options_ready = mount_option_widgets(panel, self.current_op)

    @on(Select.Changed, "#step-command")
    async def _step_command_changed(self, event: Select.Changed) -> None:
        if event.value in RITE_OPERATIONS_BY_KEY and self._step_index is not None:
            op = RITE_OPERATIONS_BY_KEY[event.value]
            if op is not self.current_op:
                self.current_op = op
                self._build_step_options()
                if self._options_ready is not None:
                    await self._options_ready  # sync below must see the new op's widgets
            self._refresh_incantation()

    @on(Input.Changed)
    @on(Select.Changed)
    @on(Switch.Changed)
    def _anything_changed(self) -> None:
        self._refresh_incantation()

    def _sync_current_step(self) -> None:
        """Write the form's current state back into the step list, so
        switching steps (or saving) never loses an in-progress edit."""
        if self._step_index is None or self._step_index >= len(self._steps):
            return
        try:
            opts = collect_option_values(self, self.current_op)
        except NoMatches:  # the options panel is mid-rebuild
            return
        args = incantation_argv(self.current_op, SOURCE_PLACEHOLDER, opts)
        name = self.query_one("#step-name", Input).value.strip()
        self._steps[self._step_index] = RiteStep(command=self.current_op.key, args=args, name=name)

    def _parse_sources(self) -> list[str]:
        raw = self.query_one("#rite-sources", Input).value.strip()
        if not raw:
            return ["."]
        return [token for token in raw.replace(",", " ").split() if token]

    def _assemble_rite(self) -> Rite:
        self._sync_current_step()
        return Rite(
            name=self.query_one("#rite-name", Input).value.strip(),
            steps=list(self._steps),
            description=self.query_one("#rite-desc", Input).value.strip(),
        )

    def _refresh_incantation(self) -> None:
        self._sync_current_step()
        self._refresh_steps_list()  # the step's label may have changed (ritual or name)
        try:
            label = self.query_one("#rite-incantation", Label)
        except NoMatches:  # the form is mid-rebuild
            return
        if not self._steps:
            label.update("(no steps yet)")
            return
        lines = [shlex.join(["reaper", s.command, *s.args]) for s in self._steps]
        name = self.query_one("#rite-name", Input).value.strip()
        sources = " ".join(self._parse_sources())
        hint = f"reaper perform {name} {sources}" if name else "name it to perform it"
        label.update("\n".join(lines) + f"\n[dim]{hint}[/dim]")

    # -- save / delete ---------------------------------------------------------

    @on(Button.Pressed, "#save")
    def _save_button(self) -> None:
        self.action_save_rite()

    @on(Button.Pressed, "#delete")
    def _delete_button(self) -> None:
        self.action_delete_rite()

    def action_save_rite(self) -> None:
        a_rite = self._assemble_rite()
        try:
            path = config.save_rite(a_rite)
        except GrimoireError as exc:
            self._status(str(exc))
            self.notify(str(exc), severity="error", title="not inscribed")
            return
        self._load_rites()
        self._status(f"inscribed {a_rite.name!r} in {path.name} - reaper perform {a_rite.name}")
        self.notify(f"inscribed in {path.name}; perform it headless any time")

    def action_delete_rite(self) -> None:
        name = self.query_one("#rite-name", Input).value.strip()
        if not name:
            self._status("pick or name a rite first")
            return
        try:
            config.delete_rite(name)
        except GrimoireError as exc:
            self._status(str(exc))
            self.notify(str(exc), severity="error", title="not struck")
            return
        self._load_rites()
        self._status(f"struck {name!r} from the grimoire")

    # -- running (a live preview, not the CLI's own capture) -----------------

    @on(Button.Pressed, "#run")
    def _run_button(self) -> None:
        self.action_run()

    def action_run(self) -> None:
        if self._rite_running:
            self.notify("the rite is already running", severity="warning")
            return
        self._sync_current_step()
        steps = list(self._steps)
        if not steps:
            self.notify("add a step first", severity="warning")
            return
        sources = self._parse_sources()
        self._rite_running = True
        self._artifacts.clear()
        self.query_one("#results", DataTable).clear()
        self.query_one(ScytheSpinner).start(f"performing across {len(sources)} source(s)")
        self._status(f"running {len(steps)} step(s) x {len(sources)} source(s) ...")
        self._run_worker(steps, sources)

    @work(thread=True, exclusive=True)
    def _run_worker(self, steps: list[RiteStep], sources: list[str]) -> None:
        total = len(steps) * len(sources)
        ok = 0
        failed = 0
        for source in sources:
            try:
                resolved = resolve_source(source, depth=None)
            except Exception as exc:  # a bad source must not take the run down
                for i, step in enumerate(steps):
                    failed += 1
                    label = step.name or step.command
                    self.app.call_from_thread(self._add_row, source, i, label, "failed", str(exc))
                continue
            for i, step in enumerate(steps):
                label = step.name or step.command
                self.app.call_from_thread(
                    self.query_one(ScytheSpinner).stage, f"{step.command} @ {source}"
                )
                spell = incant.parse(shlex.join(["reaper", step.command, *step.args]))
                if spell.kind != "ritual" or spell.op is None:
                    failed += 1
                    message = spell.error or "not a runnable step"
                    self.app.call_from_thread(self._add_row, source, i, label, "failed", message)
                    continue
                try:
                    result = spell.op.run(resolved.repo, dict(spell.opts))
                except Exception as exc:
                    failed += 1
                    self.app.call_from_thread(self._add_row, source, i, label, "failed", str(exc))
                    continue
                ok += 1
                fate = "CURSED" if result.cursed else "ok"
                self.app.call_from_thread(
                    self._add_row, source, i, label, fate, result.summary, result.text
                )
        self.app.call_from_thread(self._run_done, total, ok, failed)

    def _add_row(
        self,
        source: str,
        index: int,
        label: str,
        fate: str,
        summary: str,
        artifact: str | None = None,
    ) -> None:
        table = self.query_one("#results", DataTable)
        key = f"{source}::{index}"
        styled = Text(fate, style="bold red") if fate in ("failed", "CURSED") else Text(fate)
        table.add_row(source, label, styled, summary, key=key)
        if artifact is not None:
            self._artifacts[key] = artifact

    def _run_done(self, total: int, ok: int, failed: int) -> None:
        self._rite_running = False
        self.query_one(ScytheSpinner).stop()
        note = f"performed {ok}/{total} step-runs"
        if failed:
            note += f", {failed} failed"
        self._status(note + " - select a row to read its artifact")

    @on(DataTable.RowSelected, "#results")
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value if event.row_key else None
        if key and key in self._artifacts:
            self.query_one("#results-preview", TextArea).text = self._artifacts[key]

    # -- chrome --------------------------------------------------------------

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen(_HELP))

    def _status(self, message: str) -> None:
        self.query_one("#status", Label).update(message)
