"""The interactive operation catalog for the TUI.

Deliberately textual-free: this is the thin adapter that maps a chosen ritual
(and its options) to `core function -> formatter`, and it is where that
wiring's correctness lives (chronicle must render as a chronicle, not as
souls). Keeping it out of tui.py lets the base test suite cover it without the
[tui] extra.

Only source-driven, viewable rituals appear here -- the ones that take a
repo/folder and produce a report. Commands that need extra positional
arguments (scry's two refs, autopsy/resurrect a path, reanimate artifacts,
veil a file) or are meta (grimoire, cast, banish, pulse, necropolis) stay
CLI-only.

Each ritual declares its options (a textual-free spec the TUI renders into
widgets) and returns a ReapResult carrying the rendered text plus a one-line
summary and a `cursed` flag -- so the TUI can badge exhume/omens/plague
findings without re-parsing the artifact.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from git_reaper import cache, config, fsutil
from git_reaper.core import census as census_core
from git_reaper.core import dedupe as dedupe_core
from git_reaper.core import graveyard as graveyard_core
from git_reaper.core import harvest as harvest_core
from git_reaper.core import history as history_core
from git_reaper.core import hygiene as hygiene_core
from git_reaper.core import pack as pack_core
from git_reaper.core import plague as plague_core
from git_reaper.core import risk as risk_core
from git_reaper.core import rules as rules_core
from git_reaper.core import scan as scan_core
from git_reaper.core import skeleton as skeleton_core
from git_reaper.core import tree as tree_core
from git_reaper.formatters import csvfmt, htmlfmt, jsonfmt, markdown
from git_reaper.models import RepoRef

# --------------------------------------------------------------------------
# option specs -- a small textual-free vocabulary the panel renders generically
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ChoiceOpt:
    """One-of-many, rendered as a Select."""

    name: str
    label: str
    choices: tuple[str, ...]
    default: str


@dataclass(frozen=True)
class ToggleOpt:
    """A boolean, rendered as a Switch."""

    name: str
    label: str
    default: bool = False


@dataclass(frozen=True)
class NumberOpt:
    """An optional whole number, rendered as an Input (empty means unset)."""

    name: str
    label: str
    default: int | None = None


@dataclass(frozen=True)
class TextOpt:
    """A short free-text value, rendered as an Input."""

    name: str
    label: str
    default: str = ""


OptSpec = ChoiceOpt | ToggleOpt | NumberOpt | TextOpt

#: The four artifact formats, and common subsets, as reusable format options.
_ALL_FORMATS = ("md", "json", "csv", "html")


def _format_opt(*formats: str) -> ChoiceOpt:
    return ChoiceOpt("format", "format", formats, formats[0])


@dataclass
class ReapResult:
    """What a ritual produced: the artifact text, a summary, and whether the
    scan turned up what you feared (exhume/omens/plague)."""

    text: str
    summary: str
    cursed: bool = False


@dataclass(frozen=True)
class Operation:
    """One ritual the TUI can perform against a resolved source."""

    key: str  # stable id -- also the ritual's name in the menu
    description: str  # one-line summary, shown under the name in the menu
    group: str  # sidebar section
    needs_git: bool  # history rituals require a real repo
    run: Callable[[RepoRef, dict[str, Any]], ReapResult]
    options: tuple[OptSpec, ...] = field(default_factory=tuple)

    @property
    def label(self) -> str:
        """Name and description on one line -- the header above the options."""
        return f"{self.key} - {self.description}"

    def defaults(self) -> dict[str, Any]:
        """The default option values -- what a reap uses before the user edits."""
        return {opt.name: opt.default for opt in self.options}


def _invoked(key: str) -> str:
    return f"reaper summon ({key})"


def _dispatch(key: str, result: Any, fmt: str, md: Callable[[Any], str]) -> str:
    """Render a core result in the chosen format, exactly as the CLI does.

    md/json are universal; csv/html are only ever passed for rituals whose
    format choices include them, so the lookups here cannot miss.
    """
    if fmt == "json":
        return jsonfmt.render(result)
    if fmt == "csv":
        renderer: Callable[[Any], str] = getattr(csvfmt, f"render_{key}")
        return renderer(result)
    if fmt == "html":
        return htmlfmt.render(key, result)
    return md(result)


# --------------------------------------------------------------------------
# reaping and packing
# --------------------------------------------------------------------------


def _limbs(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = tree_core.tree(repo, invoked=_invoked("limbs"))
    text = _dispatch("limbs", result, opts["format"], markdown.render_tree)
    return ReapResult(text, f"{result.dir_count} crypts, {result.file_count} souls")


def _harvest(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = harvest_core.harvest(repo, invoked=_invoked("harvest"))
    buf = io.StringIO()
    markdown.write_harvest(result, buf)
    return ReapResult(buf.getvalue(), f"{len(result.files)} files")


def _conjure(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = pack_core.conjure(repo, invoked=_invoked("conjure"))
    text = "".join(part for _number, part in pack_core.iter_parts(result))
    return ReapResult(text, f"{len(result.files)} files, ~{result.token_estimate:,} tokens")


def _census(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = census_core.census(repo, invoked=_invoked("census"))
    text = _dispatch("census", result, opts["format"], markdown.render_census)
    return ReapResult(text, f"{result.total_files} souls, {len(result.extensions)} kinds")


def _unfinished(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = scan_core.unfinished(repo, with_age=opts["age"], invoked=_invoked("unfinished"))
    text = _dispatch("unfinished", result, opts["format"], markdown.render_unfinished)
    return ReapResult(text, f"{len(result.markers)} unfinished things")


def _bones(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = skeleton_core.bones(repo, invoked=_invoked("bones"))
    text = _dispatch("bones", result, opts["format"], markdown.render_bones)
    summary = f"{result.parsed_files} files mapped"
    if result.skipped_files:
        summary += f", {result.skipped_files} skipped (need [bones])"
    return ReapResult(text, summary)


# --------------------------------------------------------------------------
# git necromancy
# --------------------------------------------------------------------------


def _chronicle(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = history_core.chronicle(
        repo, changelog=opts["changelog"], invoked=_invoked("chronicle")
    )
    text = _dispatch("chronicle", result, opts["format"], markdown.render_chronicle)
    return ReapResult(text, f"{len(result.commits)} commits")


def _souls(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = history_core.souls(repo, heatmap=opts["heatmap"], invoked=_invoked("souls"))
    text = _dispatch("souls", result, opts["format"], markdown.render_souls)
    return ReapResult(text, f"{len(result.souls)} souls, bus factor {result.bus_factor}")


def _haunt(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = history_core.haunt(repo, limit=opts["limit"], invoked=_invoked("haunt"))
    text = _dispatch("haunt", result, opts["format"], markdown.render_haunt)
    return ReapResult(text, f"{len(result.hotspots)} hotspots")


def _graveyard(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = graveyard_core.graveyard(repo, invoked=_invoked("graveyard"))
    text = _dispatch("graveyard", result, opts["format"], markdown.render_graveyard)
    return ReapResult(text, f"{len(result.dead)} dead")


def _rot(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = hygiene_core.rot(repo, limit=opts["limit"], invoked=_invoked("rot"))
    text = _dispatch("rot", result, opts["format"], markdown.render_rot)
    return ReapResult(text, f"{len(result.files)} files weighed for rot")


def _ghosts(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    than = str(opts["than"]).strip()
    than_days = int(cache.parse_age(than) // 86400) if than else None
    result = hygiene_core.ghosts(repo, than_days=than_days, invoked=_invoked("ghosts"))
    text = _dispatch("ghosts", result, opts["format"], markdown.render_ghosts)
    return ReapResult(text, f"{len(result.branches)} branches")


def _tombstone(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = history_core.tombstone(repo, invoked=_invoked("tombstone"))
    text = _dispatch("tombstone", result, opts["format"], markdown.render_tombstone)
    return ReapResult(text, result.name)


# --------------------------------------------------------------------------
# forensics
# --------------------------------------------------------------------------


def _doppelgangers(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    raw = str(opts["min_size"]).strip()
    floor = max(1, fsutil.parse_size(raw)) if raw else 1
    result = dedupe_core.doppelgangers(repo, min_size=floor, invoked=_invoked("doppelgangers"))
    text = _dispatch("doppelgangers", result, opts["format"], markdown.render_doppelgangers)
    summary = (
        f"{len(result.clusters)} clusters, "
        f"{fsutil.human_size(result.reclaimable_bytes)} reclaimable"
    )
    return ReapResult(text, summary)


def _bloat(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = dedupe_core.bloat(repo, limit=opts["limit"] or 20, invoked=_invoked("bloat"))
    text = _dispatch("bloat", result, opts["format"], markdown.render_bloat)
    summary = (
        f"tree {fsutil.human_size(result.tree_bytes)}, "
        f"walls {fsutil.human_size(result.walls_bytes)}"
    )
    return ReapResult(text, summary)


# --------------------------------------------------------------------------
# dark arts
# --------------------------------------------------------------------------


def _exhume(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    rules = rules_core.load_rules(config.custom_rules())
    result = rules_core.exhume(
        repo, rules=rules, with_entropy=not opts["no_entropy"], invoked=_invoked("exhume")
    )
    text = _dispatch("exhume", result, opts["format"], markdown.render_exhume)
    summary = f"{len(result.findings)} findings, {result.blobs_scanned} blobs scanned"
    return ReapResult(text, summary, cursed=bool(result.findings))


def _omens(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = risk_core.omens(
        repo,
        lens=opts["lens"],
        limit=opts["limit"],
        weights=config.omens_weights(),
        invoked=_invoked("omens"),
    )
    text = _dispatch("omens", result, opts["format"], markdown.render_omens)
    cursed = bool(result.omens and result.omens[0].score >= 0.8)
    return ReapResult(text, f"{len(result.omens)} files read", cursed=cursed)


def _plague(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = plague_core.plague(repo, offline=opts["offline"], invoked=_invoked("plague"))
    text = _dispatch("plague", result, opts["format"], markdown.render_plague)
    if result.checked:
        summary = f"{len(result.afflictions)} afflictions / {len(result.dependencies)} deps"
    else:
        summary = f"offline: {len(result.dependencies)} deps parsed"
    return ReapResult(text, summary, cursed=bool(result.afflictions))


# --------------------------------------------------------------------------
# the registry
# --------------------------------------------------------------------------

OPERATIONS: list[Operation] = [
    Operation(
        "limbs",
        "hierarchical file listing",
        "reaping",
        False,
        _limbs,
        (_format_opt("md", "json"),),
    ),
    Operation("harvest", "gather *.md into one artifact", "reaping", False, _harvest),
    Operation("conjure", "bundle the repo for an LLM", "packing", False, _conjure),
    Operation(
        "census",
        "file-type census",
        "packing",
        False,
        _census,
        (_format_opt(*_ALL_FORMATS),),
    ),
    Operation(
        "unfinished",
        "TODO/FIXME/HACK/XXX",
        "packing",
        False,
        _unfinished,
        (ToggleOpt("age", "age (how long it has haunted)"), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "bones",
        "structure without the flesh",
        "packing",
        False,
        _bones,
        (_format_opt("md", "json"),),
    ),
    Operation(
        "chronicle",
        "commit history",
        "necromancy",
        True,
        _chronicle,
        (ToggleOpt("changelog", "changelog (group by tag)"), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "souls",
        "contributors",
        "necromancy",
        True,
        _souls,
        (ToggleOpt("heatmap", "heatmap", default=True), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "haunt",
        "churn hotspots",
        "necromancy",
        True,
        _haunt,
        (NumberOpt("limit", "limit (top N)"), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "graveyard",
        "files that lived and died",
        "necromancy",
        True,
        _graveyard,
        (_format_opt(*_ALL_FORMATS),),
    ),
    Operation(
        "rot",
        "staleness report",
        "necromancy",
        True,
        _rot,
        (NumberOpt("limit", "limit (top N)"), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "ghosts",
        "branch hygiene",
        "necromancy",
        True,
        _ghosts,
        (TextOpt("than", "than (e.g. 90d)"), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "tombstone",
        "the stats card",
        "necromancy",
        True,
        _tombstone,
        (_format_opt("md", "json"),),
    ),
    Operation(
        "doppelgangers",
        "duplicate files",
        "forensics",
        False,
        _doppelgangers,
        (TextOpt("min_size", "min size (e.g. 4KB)"), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "bloat",
        "the heaviest bodies",
        "forensics",
        False,
        _bloat,
        (NumberOpt("limit", "limit (top N)", default=20), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "exhume",
        "secrets in the history",
        "dark arts",
        True,
        _exhume,
        (ToggleOpt("no_entropy", "no entropy (signatures only)"), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "omens",
        "composite risk prophecy",
        "dark arts",
        True,
        _omens,
        (
            ChoiceOpt("lens", "lens", ("all", "churn", "bugs", "age", "size"), "all"),
            NumberOpt("limit", "limit (top N)"),
            _format_opt(*_ALL_FORMATS),
        ),
    ),
    Operation(
        "plague",
        "dependency advisories",
        "dark arts",
        False,
        _plague,
        (ToggleOpt("offline", "offline (no network)", default=True), _format_opt(*_ALL_FORMATS)),
    ),
]

OPERATIONS_BY_KEY: dict[str, Operation] = {op.key: op for op in OPERATIONS}

#: Sidebar section order.
GROUPS: tuple[str, ...] = ("reaping", "packing", "necromancy", "forensics", "dark arts")
