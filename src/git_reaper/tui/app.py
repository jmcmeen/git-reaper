"""The Sanctum: the reaper's interactive face, a workbench of chambers.

One App, many Screens (Textual's Screen API): the crypt map is home, each
chamber is a door. Chambers keep their state while you roam -- the Altar's
artifact survives a trip to the Seance. Navigation is uniform: number keys
jump, escape returns to the map, and Ctrl+P's palette knows every door.
"""

from __future__ import annotations

from functools import partial

from textual.app import App
from textual.binding import Binding
from textual.command import DiscoveryHit, Hit, Hits, Provider

from git_reaper.tui.altar import AltarScreen
from git_reaper.tui.console import ConsoleScreen
from git_reaper.tui.coven import CovenScreen
from git_reaper.tui.crypt import CryptMapScreen
from git_reaper.tui.grimoire import GrimoireScreen
from git_reaper.tui.necropolis import NecropolisScreen
from git_reaper.tui.reliquary import ReliquaryScreen
from git_reaper.tui.seance import SeanceScreen
from git_reaper.tui.widgets import REAPER_DRACULA

#: The chambers, in door order: (screen name, title, one-line blurb).
CHAMBERS: tuple[tuple[str, str, str], ...] = (
    ("altar", "the altar", "run a ritual against one source"),
    ("grimoire", "the grimoire", "compose and inscribe recipes visually"),
    ("coven", "the coven", "compose multi-step rites and run the chain"),
    ("console", "the incantation console", "assisted CLI with / commands"),
    ("necropolis", "the necropolis board", "the fleet, grave by grave"),
    ("reliquary", "the reliquary", "security and risk triage on one slab"),
    ("seance", "the seance table", "heatmap, chronicle, and scrying in one view"),
)


class ChamberCommands(Provider):
    """The global palette's doors: `enter the altar` from anywhere."""

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for name, title, blurb in CHAMBERS:
            command = f"enter {title}"
            score = matcher.match(command)
            if score > 0:
                app = self.app
                assert isinstance(app, ReaperApp)
                yield Hit(
                    score,
                    matcher.highlight(command),
                    partial(app.goto_chamber, name),
                    help=blurb,
                )

    async def discover(self) -> Hits:
        for name, title, blurb in CHAMBERS:
            app = self.app
            assert isinstance(app, ReaperApp)
            yield DiscoveryHit(f"enter {title}", partial(app.goto_chamber, name), help=blurb)


class ReaperApp(App[None]):
    """The Sanctum's shell: theme, shared source, and the doors."""

    TITLE = "git-reaper"
    COMMANDS = App.COMMANDS | {ChamberCommands}
    SCREENS = {
        "crypt": CryptMapScreen,
        "altar": AltarScreen,
        "grimoire": GrimoireScreen,
        "coven": CovenScreen,
        "console": ConsoleScreen,
        "necropolis": NecropolisScreen,
        "reliquary": ReliquaryScreen,
        "seance": SeanceScreen,
    }
    # Hidden from the Footer, which would otherwise wrap on binding-heavy
    # chambers; the crypt map and the palette carry the doors instead.
    BINDINGS = [
        Binding(str(i), f"chamber('{name}')", title, show=False)
        for i, (name, title, _b) in enumerate(CHAMBERS, start=1)
    ]
    CSS = """
    /* the crypt map */
    #crypt-center { height: 1fr; align: center middle; }
    #crypt { width: 72; height: auto; }
    #crypt-art { text-align: center; }
    #crypt-title { width: 100%; text-align: center; text-style: bold; color: $primary; }
    #doors { height: auto; max-height: 24; }
    #crypt-hint { width: 100%; text-align: center; color: $text-muted; padding: 1 0 0 0; }

    /* shared chamber furniture. Same-edge docks superimpose (each starts at
       the edge), so the top stack is spelled out in margins: header on row 0,
       the source row below it, the hint below that. */
    #source-row { dock: top; height: 3; margin: 1 1 0 1; }
    #source { width: 1fr; }
    #browse-btn { width: 10; margin-left: 1; }
    #source-hint { dock: top; height: 1; margin: 4 0 0 0; color: $text-muted; padding: 0 2; }
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

    /* the grimoire */
    #recipe-list { width: 36; border-right: solid $primary; }
    #recipe-form { height: auto; }
    .form-row { height: 3; margin: 0 1; }
    .form-row Label { width: 14; padding: 1 0 0 0; }
    #incantation { height: 2; color: $success; padding: 0 1; text-style: bold; }
    #grimoire-buttons { height: 3; margin: 0 1; }
    #grimoire-buttons Button { margin-right: 2; }

    /* the coven */
    #rite-list { width: 36; border-right: solid $primary; }
    #steps-row { height: 14; }
    #steps-panel { width: 30; border-right: solid $secondary; padding-right: 1; }
    #steps { height: 1fr; }
    #step-buttons { height: 3; }
    #step-buttons Button { margin-right: 1; min-width: 6; }
    #step-form { height: 1fr; padding-left: 1; }
    #rite-incantation { height: 5; color: $success; padding: 0 1; }
    #coven-buttons { height: 3; margin: 0 1; }
    #coven-buttons Button { margin-right: 2; }
    #results { height: 10; }
    #results-preview { height: 8; border: round $primary; }

    /* the incantation console */
    #console-log { height: 1fr; border: round $primary; }
    #live-help { height: 1; color: $text-muted; padding: 0 1; }
    #suggestions { height: auto; max-height: 9; border: round $secondary; display: none; }
    #incant { dock: bottom; }

    /* boards (necropolis, reliquary, seance) */
    .board-controls { dock: top; height: 3; margin: 0 1; }
    .board-controls Input { width: 1fr; }
    .board-controls Select { width: 24; }
    .board-controls Button { margin-left: 1; }
    #graves, #slab, #heatmap, #hour-commits { height: 1fr; }
    #board-split { height: 1fr; }
    #board-preview { height: 12; border: round $primary; }
    #seance-top { height: 12; }
    #scry-row { dock: top; height: 3; margin: 0 1; }
    #scry-row Input { width: 20; margin-right: 1; }
    """

    def __init__(self, source: str = ".") -> None:
        super().__init__()
        #: The shared source: chambers prefill from it and write back to it,
        #: so roaming the Sanctum never loses the crypt you were reaping.
        self.source = source

    def on_mount(self) -> None:
        self.register_theme(REAPER_DRACULA)
        self.theme = "reaper-dracula"
        self.push_screen("crypt")

    def action_chamber(self, name: str) -> None:
        self.goto_chamber(name)

    def action_crypt(self) -> None:
        self.goto_chamber("crypt")

    def goto_chamber(self, name: str) -> None:
        """Walk to a chamber: pop back to the map, then through its door."""
        while len(self.screen_stack) > 2:  # [_default, crypt, ...]
            self.pop_screen()
        if name != "crypt":
            self.push_screen(name)


def run_tui(source: str = ".") -> None:
    """Launch the Sanctum. Called by `reaper summon`."""
    ReaperApp(source=source).run()
