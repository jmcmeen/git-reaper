"""The skull gallery: the reaper, banners, tombstones, and spinner frames.

Everything here is decoration. Every caller must honor --plain / NO_COLOR
by simply not calling into this module (see theme.theme_enabled).

Each piece lives in its own text file next to this module: gallery/ is
the boo() pool, seasonal/ holds the pieces that only appear on their
night. Drop a .txt file into gallery/ and it is discovered, served, and
tested with no code change; retrieve any piece by file name via piece().

The figures follow dev-data/grim-reaper-ascii-brief.md: silhouette first,
hood and scythe legible at a glance, everything else atmosphere.
"""

from __future__ import annotations

import random
from datetime import date
from functools import cache
from importlib import resources

_ROOMS = ("gallery", "seasonal")

SCYTHE_FRAMES = ["/", "-", "\\", "|"]


@cache
def piece(name: str) -> str:
    """Retrieve a piece by name (its file name, sans .txt) from any room."""
    for room in _ROOMS:
        candidate = resources.files(__name__) / room / f"{name}.txt"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").rstrip("\n")
    raise KeyError(f"no piece named {name!r} hangs in the gallery")


@cache
def gallery() -> tuple[str, ...]:
    """Every piece in the boo() pool, by name, alphabetically."""
    room = resources.files(__name__) / "gallery"
    return tuple(sorted(entry.name[:-4] for entry in room.iterdir() if entry.name.endswith(".txt")))


def boo() -> str:
    """A random piece from the gallery, for the hidden `reaper boo`."""
    return piece(random.choice(gallery()))


def banner(version: str, width: int = 80) -> str:
    """The CLI banner, sized to the terminal."""
    skull = piece("hero-skull") if width >= 40 else piece("narrow-skull")
    return f"{skull}\n        v{version}\n"


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


# -- easter eggs (tiny, harmless, all bypassed by --plain) -------------------


def seasonal_banner(today: date | None = None) -> str | None:
    """The special banner for the one night the veil is thin."""
    today = today or date.today()
    if today.month == 10 and today.day == 31:
        return f"{piece('jack-o-lantern')}\n  the veil is thin tonight"
    return None


def seasonal_footer(today: date | None = None) -> str | None:
    """One line of dread on any Friday the 13th."""
    today = today or date.today()
    if today.day == 13 and today.weekday() == 4:
        return "beware: it is Friday the 13th."
    return None
