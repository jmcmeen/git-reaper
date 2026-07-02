"""The interactive operation catalog for the TUI.

Deliberately textual-free: this is the thin adapter that maps a chosen ritual
to `core function -> formatter`, and it is where that wiring's correctness
lives (chronicle must render as a chronicle, not as souls). Keeping it out of
tui.py lets the base test suite cover it without the [tui] extra.

Only source-driven, viewable operations appear here -- the ones that take a
repo/folder and produce a report. Commands that need extra arguments
(reanimate, resurrect, autopsy) or are meta (grimoire, banish) stay CLI-only.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass

from git_reaper.core import census as census_core
from git_reaper.core import graveyard as graveyard_core
from git_reaper.core import harvest as harvest_core
from git_reaper.core import history as history_core
from git_reaper.core import hygiene as hygiene_core
from git_reaper.core import pack as pack_core
from git_reaper.core import scan as scan_core
from git_reaper.core import tree as tree_core
from git_reaper.formatters import markdown
from git_reaper.models import RepoRef


@dataclass(frozen=True)
class Operation:
    """One ritual the TUI can perform against a resolved source."""

    key: str  # stable id, used in labels and tests
    label: str  # what the menu shows
    needs_git: bool  # history rituals require a real repo
    run: Callable[[RepoRef], str]  # resolved repo -> rendered markdown


def _invoked(key: str) -> str:
    return f"reaper summon ({key})"


def _harvest(repo: RepoRef) -> str:
    result = harvest_core.harvest(repo, invoked=_invoked("harvest"))
    buf = io.StringIO()
    markdown.write_harvest(result, buf)
    return buf.getvalue()


def _conjure(repo: RepoRef) -> str:
    result = pack_core.conjure(repo, invoked=_invoked("conjure"))
    return "".join(text for _number, text in pack_core.iter_parts(result))


def _limbs(repo: RepoRef) -> str:
    return markdown.render_tree(tree_core.tree(repo, invoked=_invoked("limbs")))


def _census(repo: RepoRef) -> str:
    return markdown.render_census(census_core.census(repo, invoked=_invoked("census")))


def _unfinished(repo: RepoRef) -> str:
    return markdown.render_unfinished(scan_core.unfinished(repo, invoked=_invoked("unfinished")))


def _chronicle(repo: RepoRef) -> str:
    return markdown.render_chronicle(history_core.chronicle(repo, invoked=_invoked("chronicle")))


def _souls(repo: RepoRef) -> str:
    return markdown.render_souls(history_core.souls(repo, heatmap=True, invoked=_invoked("souls")))


def _haunt(repo: RepoRef) -> str:
    return markdown.render_haunt(history_core.haunt(repo, invoked=_invoked("haunt")))


def _tombstone(repo: RepoRef) -> str:
    return markdown.render_tombstone(history_core.tombstone(repo, invoked=_invoked("tombstone")))


def _graveyard(repo: RepoRef) -> str:
    return markdown.render_graveyard(graveyard_core.graveyard(repo, invoked=_invoked("graveyard")))


def _rot(repo: RepoRef) -> str:
    return markdown.render_rot(hygiene_core.rot(repo, invoked=_invoked("rot")))


def _ghosts(repo: RepoRef) -> str:
    return markdown.render_ghosts(hygiene_core.ghosts(repo, invoked=_invoked("ghosts")))


OPERATIONS: list[Operation] = [
    Operation("limbs", "limbs - hierarchical file listing", False, _limbs),
    Operation("harvest", "harvest - gather *.md into one artifact", False, _harvest),
    Operation("conjure", "conjure - bundle the repo for an LLM", False, _conjure),
    Operation("census", "census - file-type census", False, _census),
    Operation("unfinished", "unfinished - TODO/FIXME/HACK/XXX markers", False, _unfinished),
    Operation("chronicle", "chronicle - commit history", True, _chronicle),
    Operation("souls", "souls - contributors + heatmap", True, _souls),
    Operation("haunt", "haunt - churn hotspots", True, _haunt),
    Operation("graveyard", "graveyard - files that lived and died", True, _graveyard),
    Operation("rot", "rot - staleness report", True, _rot),
    Operation("ghosts", "ghosts - branch hygiene", True, _ghosts),
    Operation("tombstone", "tombstone - the stats card", True, _tombstone),
]

OPERATIONS_BY_KEY: dict[str, Operation] = {op.key: op for op in OPERATIONS}
