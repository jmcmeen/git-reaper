"""Third-party dark magic: the `git_reaper.rituals` entry point group.

A ritual package exposes a Typer app (or a zero-arg callable returning one)
under the group, and its commands appear as `reaper <name> ...`:

    [project.entry-points."git_reaper.rituals"]
    ouija = "reaper_ouija:app"

Loading happens once at CLI startup. A broken plugin is reported and
skipped - somebody else's failed ritual must never stop the reaping.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Any

import typer

GROUP = "git_reaper.rituals"


@dataclass
class LoadedRitual:
    """One plugin's fate at load time."""

    name: str
    ok: bool
    error: str = ""


def discover() -> list[tuple[str, EntryPoint]]:
    """(name, entry point) pairs for every installed ritual, sorted by name."""
    return sorted(((ep.name, ep) for ep in entry_points(group=GROUP)), key=lambda p: p[0])


def attach(app: typer.Typer) -> list[LoadedRitual]:
    """Mount every installed ritual onto the app; report each one's fate."""
    fates: list[LoadedRitual] = []
    for name, ep in discover():
        try:
            obj: Any = ep.load()
            if callable(obj) and not isinstance(obj, typer.Typer):
                obj = obj()
            if not isinstance(obj, typer.Typer):
                raise TypeError(f"expected a typer.Typer, got {type(obj).__name__}")
            app.add_typer(obj, name=name)
            fates.append(LoadedRitual(name=name, ok=True))
        except Exception as exc:
            fates.append(LoadedRitual(name=name, ok=False, error=str(exc)))
    return fates
