"""The skull gallery: banners, tombstones, and spinner frames.

Everything here is decoration. Every caller must honor --plain / NO_COLOR
by simply not calling into this module (see theme.theme_enabled).
"""

from __future__ import annotations

import random
from datetime import date

HERO_SKULL = r"""
                ______
             .-"      "-.
            /            \
           |,  .-.  .-.  ,|
           | )(_o/  \o_)( |
           |/     /\     \|
           (_     ^^     _)
            \__|IIIIII|__/
             | \IIIIII/ |
             \          /
              `--------`
        g i t - r e a p e r
"""

# Chosen automatically for skinny terminals.
NARROW_SKULL = r"""
      .-.
     (o.o)
      |=|
   git-reaper
"""

MINI_SKULL = ".-.\n|x|\n'-'"

SCYTHE_FRAMES = ["/", "-", "\\", "|"]

TOMBSTONE_DIVIDER = "  _______\n |  RIP  |\n_|_______|_"


def banner(version: str, width: int = 80) -> str:
    """The CLI banner, sized to the terminal."""
    skull = HERO_SKULL if width >= 40 else NARROW_SKULL
    return f"{skull.rstrip()}\n        v{version}\n"


def tombstone(lines: list[str]) -> str:
    """Render lines of text inside ASCII tombstone art.

    The frame is sized to the widest line so the right border always closes
    flush, however long the epitaph runs.
    """
    content = ["R I P", "", *lines]
    inner = max((len(line) for line in content), default=0)
    inner = max(inner, 11)
    top = "         " + "_" * (inner + 2)
    body = [f"        /{' ' * (inner + 2)}\\"]
    body.extend(f"       | {line.center(inner)} |" for line in content)
    body.append("    ___|" + "_" * (inner + 2) + "|___")
    return "\n".join([top, *body])


def boo() -> str:
    """A random piece from the gallery, for the hidden `reaper boo`."""
    return random.choice([HERO_SKULL, NARROW_SKULL, MINI_SKULL, TOMBSTONE_DIVIDER])


# -- easter eggs (tiny, harmless, all bypassed by --plain) -------------------

JACK_O_LANTERN = r'''
   .-~~~~~-.
  /  ^   ^  \
 |  /\   /\  |
  \   d-b   /
   \ \___/ /
    `-----`
'''


def seasonal_banner(today: date | None = None) -> str | None:
    """The special banner for the one night the veil is thin."""
    today = today or date.today()
    if today.month == 10 and today.day == 31:
        return f"{JACK_O_LANTERN.rstrip()}\n  the veil is thin tonight"
    return None


def seasonal_footer(today: date | None = None) -> str | None:
    """One line of dread on any Friday the 13th."""
    today = today or date.today()
    if today.day == 13 and today.weekday() == 4:
        return "beware: it is Friday the 13th."
    return None
