"""The spooky palette, defined once and reused everywhere.

Chatter (narration, progress, warnings) always goes to stderr so that
artifacts written to stdout stay clean and pipeable.
"""

from __future__ import annotations

import os
import sys

from rich.console import Console
from rich.theme import Theme

# Palette tokens. The CLI and (later) the TUI both draw from this table so
# the two faces of the reaper look identical.
PALETTE: dict[str, str] = {
    "bone": "grey93",  # primary text, headers
    "ash": "grey50",  # secondary text, dividers
    "grave": "slate_blue3",  # panels, borders, table chrome
    "blood": "red3",  # errors, destructive actions
    "necro": "green3",  # success, "reaped" counts
    "eldritch": "medium_purple3",  # accents, highlights, links
    "ember": "dark_orange",  # warnings, progress
}

REAPER_THEME = Theme({name: color for name, color in PALETTE.items()})


def theme_enabled(plain: bool = False) -> bool:
    """Decide whether themed output (color, art) is allowed.

    ``--plain`` wins, then ``NO_COLOR``, then tty detection on stderr.
    """
    if plain:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stderr.isatty()


def make_console(plain: bool = False, quiet: bool = False) -> Console:
    """Build the narration console. Always stderr; artifacts own stdout."""
    enabled = theme_enabled(plain)
    return Console(
        stderr=True,
        theme=REAPER_THEME,
        no_color=not enabled,
        highlight=False,
        quiet=quiet,
    )
