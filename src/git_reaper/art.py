"""The skull gallery: banners, tombstones, and spinner frames.

Everything here is decoration. Every caller must honor --plain / NO_COLOR
by simply not calling into this module (see theme.theme_enabled).
"""

from __future__ import annotations

import random

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
    """Render lines of text inside ASCII tombstone art."""
    inner = max(len(line) for line in lines) if lines else 0
    inner = max(inner, 11)
    top = "         " + "_" * inner
    body = [f"        /{' ' * inner}\\"]
    body.extend(f"       | {line.center(inner - 2)} |" for line in ["R I P", "", *lines])
    body.append("    ___|" + "_" * inner + "|___")
    return "\n".join([top, *body])


def boo() -> str:
    """A random piece from the gallery, for the hidden `reaper boo`."""
    return random.choice([HERO_SKULL, NARROW_SKULL, MINI_SKULL, TOMBSTONE_DIVIDER])
