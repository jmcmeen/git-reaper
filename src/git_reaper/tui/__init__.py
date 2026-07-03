"""The Sanctum: git-reaper's Textual TUI, a workbench of chambers.

Textual is only imported under this package, so the base install stays
lean; `reaper summon` reports the missing `[tui]` extra clearly when this
import fails.
"""

from git_reaper.tui.altar import AltarScreen
from git_reaper.tui.app import CHAMBERS, ReaperApp, run_tui
from git_reaper.tui.console import ConsoleScreen
from git_reaper.tui.crypt import CryptMapScreen
from git_reaper.tui.grimoire import GrimoireScreen
from git_reaper.tui.necropolis import NecropolisScreen
from git_reaper.tui.reliquary import ReliquaryScreen
from git_reaper.tui.seance import SeanceScreen
from git_reaper.tui.widgets import (
    REAPER_DRACULA,
    BrowseScreen,
    HelpScreen,
    SaveScreen,
    ScytheSpinner,
)

__all__ = [
    "CHAMBERS",
    "REAPER_DRACULA",
    "AltarScreen",
    "BrowseScreen",
    "ConsoleScreen",
    "CryptMapScreen",
    "GrimoireScreen",
    "HelpScreen",
    "NecropolisScreen",
    "ReaperApp",
    "ReliquaryScreen",
    "SaveScreen",
    "ScytheSpinner",
    "SeanceScreen",
    "run_tui",
]
