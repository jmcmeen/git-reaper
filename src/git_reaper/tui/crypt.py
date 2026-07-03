"""The crypt map: the Sanctum's home screen, chambers as doors."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, OptionList, Static
from textual.widgets.option_list import Option

from git_reaper import __version__, art


class CryptMapScreen(Screen[None]):
    """Pick a chamber. Everything else is one door away."""

    BINDINGS = [
        ("question_mark", "help", "Help"),
        ("q,escape", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:

        yield Header(show_clock=False)
        with Center(id="crypt-center"), Vertical(id="crypt"):
            yield Static(f"[$primary]{art.piece('mini-skull')}[/]", id="crypt-art")
            yield Label(f"the sanctum - git-reaper {__version__}", id="crypt-title")
            doors = OptionList(id="doors")
            yield doors
            yield Label(
                "enter opens a door - 1-6 jump from anywhere - ctrl+p is the palette",
                id="crypt-hint",
            )
        yield Footer()

    def on_mount(self) -> None:
        from git_reaper.tui.app import CHAMBERS

        doors = self.query_one("#doors", OptionList)
        for i, (name, title, blurb) in enumerate(CHAMBERS, start=1):
            doors.add_option(Option(f"{i}  {title}\n   [dim]{blurb}[/dim]", id=name))
        doors.highlighted = 0
        doors.focus()

    def on_screen_resume(self) -> None:
        self.app.sub_title = "the crypt map"

    @on(OptionList.OptionSelected, "#doors")
    def _enter(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            self.app.push_screen(event.option.id)

    def action_help(self) -> None:
        from git_reaper.tui.app import CHAMBERS
        from git_reaper.tui.widgets import HelpScreen

        rows = "\n".join(
            f"  {i}  {title} - {blurb}" for i, (_n, title, blurb) in enumerate(CHAMBERS, start=1)
        )
        body = (
            "[b]the sanctum[/b]\n"
            "a workbench of chambers over one typed core. nothing here is\n"
            "TUI-trapped: recipes cast headless, incantations are real argv.\n\n"
            f"[b]chambers[/b]\n{rows}\n\n"
            "  escape returns to this map from any chamber\n"
            "  ctrl+p jumps between chambers and switches themes"
        )
        self.app.push_screen(HelpScreen(body))
