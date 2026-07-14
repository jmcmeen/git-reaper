"""The Incantation console: a REPL over the same rituals, `/` summons the menu.

Type `/` and fuzzy-pick a ritual; the help line validates flags as you go;
Enter runs the assembled invocation on a worker thread and the artifact fills
the preview. Every accepted line is a real `reaper` argv (shown with the
result), and the history recalls with up/down -- nothing here is TUI-trapped.

Distinct from Ctrl+P's palette on purpose: the palette fires app actions,
this constructs reproducible invocations.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from textual import events, on, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from git_reaper import config, incant
from git_reaper.tui.widgets import HelpScreen, SaveScreen, ScytheSpinner
from git_reaper.tui_ops import Operation, resolve

_HELP = (
    "[b]the incantation console[/b]\n"
    "type / for the ritual menu; enter runs the line. every run is a real\n"
    "reaper invocation -- copy the argv above the artifact and it reproduces.\n\n"
    "  up/down  history (or the menu, while it is open)\n"
    "  tab      complete the highlighted suggestion\n"
    "  /help /recipes /theme /clear /save  the console's own commands\n"
    "  escape   crypt map (or close the menu)"
)


class ConsoleScreen(Screen[None]):
    """Assisted CLI: fuzzy menu, live validation, reproducible argv."""

    BINDINGS = [
        ("question_mark", "help", "Help"),
        ("escape", "dismiss_or_crypt", "Crypt map"),
        ("ctrl+s", "save_artifact", "Save"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._artifact = ""
        self._history: list[str] = []
        self._recall = 0  # index from the end while recalling history

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="main"):
            yield TextArea("", id="console-log", read_only=True)
            yield ScytheSpinner("", id="spinner")
            yield Static("type / to summon the menu - /help explains the rest", id="live-help")
            yield OptionList(id="suggestions")
            yield Input(placeholder="/ritual [source] --flags", id="incant")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#incant", Input).focus()

    def on_screen_resume(self) -> None:
        self.app.sub_title = "the incantation console"
        self.query_one("#incant", Input).focus()

    # -- typing: suggestions and live help -----------------------------------

    @on(Input.Changed, "#incant")
    def _typed(self, event: Input.Changed) -> None:
        text = event.value
        menu = self.query_one("#suggestions", OptionList)
        # lstrip, not strip: once a word is finished (the trailing space of a
        # tab-completion), the ritual is chosen and the menu has said its piece.
        first_word = " " not in text.lstrip()
        if text.strip() and first_word:
            suggestions = incant.suggest(text)
            menu.clear_options()
            for s in suggestions[:8]:
                menu.add_option(Option(f"{s.text}  [dim]{s.detail}[/dim]", id=s.text))
            menu.display = bool(suggestions)
            if suggestions:
                menu.highlighted = 0
        else:
            menu.display = False
        self._live_help(text)

    def _live_help(self, text: str) -> None:
        help_line = self.query_one("#live-help", Static)
        spell = incant.parse(text)
        if spell.kind == "ritual" and spell.op is not None:
            help_line.update(incant.flag_help(spell.op))
        elif spell.kind == "meta":
            help_line.update(f"{spell.meta} -- {incant.META_COMMANDS[spell.meta]}")
        elif spell.kind == "error":
            help_line.update(f"[$error]{spell.error}[/]")
        else:
            help_line.update("type / to summon the menu - /help explains the rest")

    def on_key(self, event: events.Key) -> None:
        """Arrows drive the menu while it is open, the history otherwise."""
        if self.app.focused is not self.query_one("#incant", Input):
            return
        menu = self.query_one("#suggestions", OptionList)
        if event.key in ("up", "down") and menu.display:
            delta = -1 if event.key == "up" else 1
            count = menu.option_count
            menu.highlighted = ((menu.highlighted or 0) + delta) % count if count else None
            event.stop()
        elif event.key == "tab" and menu.display and menu.highlighted is not None:
            self._complete(menu.get_option_at_index(menu.highlighted).id or "")
            event.stop()
        elif event.key in ("up", "down") and self._history:
            delta = 1 if event.key == "up" else -1
            self._recall = max(0, min(len(self._history), self._recall + delta))
            box = self.query_one("#incant", Input)
            box.value = self._history[-self._recall] if self._recall else ""
            box.cursor_position = len(box.value)
            event.stop()

    @on(OptionList.OptionSelected, "#suggestions")
    def _suggestion_picked(self, event: OptionList.OptionSelected) -> None:
        self._complete(event.option.id or "")

    def _complete(self, text: str) -> None:
        box = self.query_one("#incant", Input)
        box.value = f"{text} "
        box.cursor_position = len(box.value)
        self.query_one("#suggestions", OptionList).display = False
        box.focus()

    # -- running ---------------------------------------------------------------

    @on(Input.Submitted, "#incant")
    def _submitted(self, event: Input.Submitted) -> None:
        line = event.value.strip()
        if not line:
            return
        spell = incant.parse(line)
        menu = self.query_one("#suggestions", OptionList)
        if (
            spell.kind == "error"
            and menu.display
            and menu.highlighted is not None
            and " " not in line
        ):
            # a half-typed name with the menu open: enter completes it. a
            # fully-typed command runs even if the menu is still showing.
            self._complete(menu.get_option_at_index(menu.highlighted).id or "")
            return
        menu.display = False
        if spell.kind == "error":
            self._log(f"! {spell.error}")
            return
        self._history.append(line)
        self._recall = 0
        self.query_one("#incant", Input).value = ""
        if spell.kind == "meta":
            self._meta(spell.meta, spell.meta_arg)
            return
        assert spell.op is not None
        self.query_one(ScytheSpinner).start(f"casting {spell.op.key}")
        self._cast_worker(spell.op, spell.source, dict(spell.opts), " ".join(spell.argv))

    @work(thread=True, exclusive=True)
    def _cast_worker(self, op: Operation, source: str, opts: dict[str, Any], argv: str) -> None:
        try:
            resolved = resolve(source, opts)  # the line's --ref rides along
            result = op.run(resolved.repo, opts)
            self.app.call_from_thread(self._cast_done, argv, result.text, result.summary)
        except Exception as exc:
            self.app.call_from_thread(self._cast_failed, argv, str(exc))
        finally:
            # the scythe stops however the cast ended, or the console reads as
            # still casting long after the worker died.
            self.app.call_from_thread(self._stop_scythe)

    def _stop_scythe(self) -> None:
        with contextlib.suppress(NoMatches):  # a modal is up, or the app is gone
            self.query_one(ScytheSpinner).stop()

    def _cast_done(self, argv: str, artifact: str, summary: str) -> None:
        self._artifact = artifact
        self._log(f"$ {argv}\n{artifact}")
        self.notify(f"{summary} (ctrl+s or /save to inter it)")

    def _cast_failed(self, argv: str, message: str) -> None:
        self._log(f"$ {argv}\n! the ritual failed: {message}")

    # -- meta commands -----------------------------------------------------------

    def _meta(self, meta: str, arg: str) -> None:
        if meta == "/help":
            self._log(incant.render_help())
        elif meta == "/clear":
            self.query_one("#console-log", TextArea).text = ""
        elif meta == "/recipes":
            self._log(self._recipes_listing())
        elif meta == "/theme":
            self._switch_theme(arg)
        elif meta == "/save":
            self.action_save_artifact(arg or None)

    def _recipes_listing(self) -> str:
        try:
            recipes = config.load_grimoire().recipes
        except config.GrimoireError as exc:
            return f"! the grimoire is miswritten: {exc}"
        if not recipes:
            return "(no recipes inscribed - the Grimoire chamber writes them)"
        lines = ["# recipes", ""]
        for r in recipes:
            line = " ".join(["reaper", r.command, *r.args])
            blurb = f" -- {r.description}" if r.description else ""
            lines.append(f"- {r.name}: `{line}`{blurb}")
        return "\n".join(lines)

    def _switch_theme(self, name: str) -> None:
        themes = sorted(self.app.available_themes)
        if not name:
            self._log("themes: " + ", ".join(themes) + "\nswitch with /theme <name>")
            return
        if name not in themes:
            self._log(f"! no theme {name!r}; /theme lists them")
            return
        self.app.theme = name
        self.notify(f"dressed in {name}")

    def action_save_artifact(self, path: str | None = None) -> None:
        if not self._artifact:
            self.notify("nothing cast yet", severity="warning")
            return
        if path:
            self._write_artifact(path)
            return
        self.app.push_screen(SaveScreen("artifact.md"), self._write_artifact)

    def _write_artifact(self, path: str | None) -> None:
        if not path:
            return
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._artifact, encoding="utf-8")
        self.notify(f"interred at {target}")

    # -- misc ---------------------------------------------------------------------

    def action_dismiss_or_crypt(self) -> None:
        menu = self.query_one("#suggestions", OptionList)
        if menu.display:
            menu.display = False
            return
        self.app.goto_chamber("crypt")  # type: ignore[attr-defined]

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen(_HELP))

    def _log(self, text: str) -> None:
        self.query_one("#console-log", TextArea).text = text
