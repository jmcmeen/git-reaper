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
CLI-only. A ritual that also writes (scavenge fills a library directory)
carries `writes=True` so commune can gate it behind --allow-write.

Each ritual declares its options (a textual-free spec the TUI renders into
widgets) and returns a ReapResult carrying the rendered text plus a one-line
summary and a `cursed` flag -- so the TUI can badge exhume/omens/plague
findings without re-parsing the artifact.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from git_reaper import cache, config, fsutil
from git_reaper.core import census as census_core
from git_reaper.core import dedupe as dedupe_core
from git_reaper.core import exorcise as exorcise_core
from git_reaper.core import graveyard as graveyard_core
from git_reaper.core import harvest as harvest_core
from git_reaper.core import history as history_core
from git_reaper.core import hygiene as hygiene_core
from git_reaper.core import lineage as lineage_core
from git_reaper.core import pack as pack_core
from git_reaper.core import plague as plague_core
from git_reaper.core import possession as possession_core
from git_reaper.core import prophecy as prophecy_core
from git_reaper.core import revenant as revenant_core
from git_reaper.core import risk as risk_core
from git_reaper.core import rules as rules_core
from git_reaper.core import scan as scan_core
from git_reaper.core import scavenge as scavenge_core
from git_reaper.core import skeleton as skeleton_core
from git_reaper.core import tree as tree_core
from git_reaper.core import wake as wake_core
from git_reaper.core import ward as ward_core
from git_reaper.core.source import ResolvedSource, resolve_source
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
class FloatOpt:
    """A fractional number, rendered as an Input (possession's --threshold)."""

    name: str
    label: str
    default: float | None = None


@dataclass(frozen=True)
class TextOpt:
    """A short free-text value, rendered as an Input."""

    name: str
    label: str
    default: str = ""


@dataclass(frozen=True)
class ListOpt:
    """A repeatable CLI flag (--exclude, --pattern), rendered as one Input.

    Typed comma- or space-separated; each token becomes its own flag, so
    `*.lock, dist` is the CLI's `--exclude '*.lock' --exclude dist`.
    """

    name: str
    label: str
    default: str = ""


OptSpec = ChoiceOpt | ToggleOpt | NumberOpt | FloatOpt | TextOpt | ListOpt

#: The four artifact formats, and common subsets, as reusable format options.
_ALL_FORMATS = ("md", "json", "csv", "html")


def _format_opt(*formats: str) -> ChoiceOpt:
    return ChoiceOpt("format", "format", formats, formats[0])


#: The two options nearly every ritual in the CLI takes. `--ref` reaches the
#: source resolver (see `resolve`), not the ritual; `--exclude` reaches the
#: cores that walk files -- exactly the ones whose CLI command offers it.
def _ref_opt() -> TextOpt:
    return TextOpt("ref", "ref (branch, tag, or sha)")


def _exclude_opt() -> ListOpt:
    return ListOpt("exclude", "exclude (globs)")


# --------------------------------------------------------------------------
# reading an option panel's values the way the CLI reads its flags
# --------------------------------------------------------------------------


def _texts(opts: dict[str, Any], name: str) -> list[str]:
    """A ListOpt's tokens: `*.lock, dist` -> ['*.lock', 'dist']."""
    raw = str(opts.get(name) or "").strip()
    return [token for token in raw.replace(",", " ").split() if token]


def _text(opts: dict[str, Any], name: str) -> str | None:
    """A TextOpt's value, or None when the field was left empty."""
    value = str(opts.get(name) or "").strip()
    return value or None


def _number(opts: dict[str, Any], name: str) -> int | None:
    """A NumberOpt's value. The widget hands back an int or an empty string."""
    raw = str(opts.get(name) if opts.get(name) is not None else "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else None


def _decimal(opts: dict[str, Any], name: str, default: float) -> float:
    """A FloatOpt's value, with the CLI's default when the field is empty."""
    raw = str(opts.get(name) if opts.get(name) is not None else "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, not {raw!r}") from exc


def _size(opts: dict[str, Any], name: str, default: int | None = None) -> int | None:
    """A size-shaped TextOpt (`4KB`, `1MB`), parsed exactly as the CLI parses it."""
    raw = str(opts.get(name) or "").strip()
    return fsutil.parse_size(raw) if raw else default


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
    #: The option that rides as the CLI's positional argument (autopsy PATH,
    #: lineage NEEDLE, veil FILE) -- None for the source-only rituals.
    positional: str | None = None
    #: How the CLI takes the source: "positional" (reaper KEY SOURCE),
    #: "flag" (reaper KEY POS -s SOURCE), or "none" (veil reads a file; the
    #: TUI's source only anchors relative paths).
    source_arg: str = "positional"
    #: True for rituals that write outside their artifact text (scavenge fills
    #: a library directory). Commune hides these without --allow-write and
    #: guard-checks their "out" option, so a writing op must declare one.
    writes: bool = False

    @property
    def label(self) -> str:
        """Name and description on one line -- the header above the options."""
        return f"{self.key} - {self.description}"

    def defaults(self) -> dict[str, Any]:
        """The default option values -- what a reap uses before the user edits."""
        return {opt.name: opt.default for opt in self.options}


#: Who is running the catalog -- "reaper summon" in the TUI, "reaper commune"
#: over MCP. A context variable so concurrent MCP calls cannot cross streams.
_INVOKER: ContextVar[str] = ContextVar("invoker", default="reaper summon")


@contextmanager
def invoker(name: str) -> Iterator[None]:
    """Attribute provenance to `name` for rituals run inside this context."""
    token = _INVOKER.set(name)
    try:
        yield
    finally:
        _INVOKER.reset(token)


def _invoked(key: str) -> str:
    return f"{_INVOKER.get()} ({key})"


def resolve(source: str, opts: dict[str, Any] | None = None) -> ResolvedSource:
    """Resolve a chamber's source into a readable crypt, honoring its `--ref`.

    Always the whole history (depth=None), never the CLI's shallow default:
    one Sanctum source is reaped by many rituals in a row, and a shallow
    clone would blind every history ritual that came after the first.
    """
    ref = _text(opts or {}, "ref")
    return resolve_source(source, ref=ref, depth=None)


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
    sizes, lines = opts["sizes"], opts["lines"]
    result = tree_core.tree(
        repo,
        max_depth=_number(opts, "depth"),
        dirs_only=opts["dirs_only"],
        with_sizes=sizes,
        with_lines=lines,
        excludes=_texts(opts, "exclude"),
        invoked=_invoked("limbs"),
    )
    text = _dispatch(
        "limbs",
        result,
        opts["format"],
        lambda r: markdown.render_tree(r, with_sizes=sizes, with_lines=lines),
    )
    return ReapResult(text, f"{result.dir_count} crypts, {result.file_count} souls")


def _harvest(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = harvest_core.harvest(
        repo,
        patterns=tuple(_texts(opts, "pattern")) or harvest_core.DEFAULT_PATTERNS,
        excludes=_texts(opts, "exclude"),
        max_file_size=_size(opts, "max_file_size"),
        max_total_size=_size(opts, "max_total_size"),
        include_binary=opts["include_binary"],
        invoked=_invoked("harvest"),
    )
    buf = io.StringIO()
    markdown.write_harvest(result, buf)
    return ReapResult(buf.getvalue(), f"{len(result.files)} files")


def _conjure(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    # the same rules the CLI veils with, and the same rules iter_parts needs --
    # pass them to both or the receipts would count what was never packed.
    veil_rules = rules_core.load_rules(config.custom_rules()) if opts["veil"] else None
    result = pack_core.conjure(
        repo,
        excludes=_texts(opts, "exclude"),
        max_file_size=_size(opts, "max_file_size"),
        max_total_size=_size(opts, "max_total_size"),
        with_sha256=opts["sha256"],
        split_tokens=_number(opts, "split_tokens"),
        veil_rules=veil_rules,
        invoked=_invoked("conjure"),
    )
    text = "".join(part for _number, part in pack_core.iter_parts(result, veil_rules=veil_rules))
    summary = f"{len(result.files)} files, ~{result.token_estimate:,} tokens"
    if result.parts > 1:
        summary += f" in {result.parts} parts"
    return ReapResult(text, summary)


def _scavenge(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    out_dir = Path(str(opts.get("out") or "").strip() or "skill-crypt")
    fmt = opts["format"]
    archive = fmt if fmt in fsutil.ARCHIVE_FORMATS else None
    result = scavenge_core.scavenge(
        repo,
        out_dir,
        excludes=_texts(opts, "exclude"),
        invoked=_invoked("scavenge"),
        archive=archive,
    )
    if not result.skills:
        summary = "the graves were empty"
        text = f"No {scavenge_core.MARKER} anywhere in the source; nothing was written.\n"
    else:
        summary = (
            f"{len(result.skills)} skills packaged into {result.out}"
            if archive
            else f"{len(result.skills)} skills interred in {out_dir}"
        )
        # Rendered straight from result, not re-read from disk, so this still
        # works when the crypt was archived and out_dir no longer exists.
        text = scavenge_core.render_crypt_skill(result, out_dir)
    if fmt == "json":
        text = jsonfmt.render(result)
    return ReapResult(text, summary)


def _census(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = census_core.census(repo, excludes=_texts(opts, "exclude"), invoked=_invoked("census"))
    text = _dispatch("census", result, opts["format"], markdown.render_census)
    return ReapResult(text, f"{result.total_files} souls, {len(result.extensions)} kinds")


def _unfinished(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = scan_core.unfinished(
        repo,
        excludes=_texts(opts, "exclude"),
        with_age=opts["age"],
        invoked=_invoked("unfinished"),
    )
    text = _dispatch("unfinished", result, opts["format"], markdown.render_unfinished)
    return ReapResult(text, f"{len(result.markers)} unfinished things")


def _bones(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = skeleton_core.bones(repo, excludes=_texts(opts, "exclude"), invoked=_invoked("bones"))
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
        repo,
        changelog=opts["changelog"],
        max_count=_number(opts, "max_count"),
        invoked=_invoked("chronicle"),
    )
    text = _dispatch("chronicle", result, opts["format"], markdown.render_chronicle)
    return ReapResult(text, f"{len(result.commits)} commits")


def _souls(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = history_core.souls(repo, heatmap=opts["heatmap"], invoked=_invoked("souls"))
    text = _dispatch("souls", result, opts["format"], markdown.render_souls)
    return ReapResult(text, f"{len(result.souls)} souls, bus factor {result.bus_factor}")


def _haunt(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = history_core.haunt(repo, limit=_number(opts, "limit"), invoked=_invoked("haunt"))
    text = _dispatch("haunt", result, opts["format"], markdown.render_haunt)
    return ReapResult(text, f"{len(result.hotspots)} hotspots")


def _autopsy(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    path = _text(opts, "path") or ""
    if not path:
        raise ValueError("autopsy needs a file: set the path option")
    result = history_core.autopsy(
        repo, path, follow=not opts["no_follow"], invoked=_invoked("autopsy")
    )
    text = _dispatch("autopsy", result, opts["format"], markdown.render_autopsy)
    return ReapResult(text, f"{result.commits} commits, {len(result.authors)} hands")


def _lineage(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    needle = _text(opts, "needle")
    if not needle:
        raise ValueError("lineage needs a needle: the string to trace")
    rel_path = _text(opts, "path")
    result = lineage_core.lineage(
        repo, needle, regex=opts["regex"], rel_path=rel_path, invoked=_invoked("lineage")
    )
    text = _dispatch("lineage", result, opts["format"], markdown.render_lineage)
    if result.origin is not None:
        summary = f"first summoned by {result.origin.author} in {result.origin.sha[:7]}"
    else:
        summary = "no commit ever summoned it"
    return ReapResult(text, summary)


def _graveyard(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = graveyard_core.graveyard(repo, invoked=_invoked("graveyard"))
    text = _dispatch("graveyard", result, opts["format"], markdown.render_graveyard)
    return ReapResult(text, f"{len(result.dead)} dead")


def _rot(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = hygiene_core.rot(
        repo,
        limit=_number(opts, "limit"),
        excludes=_texts(opts, "exclude"),
        invoked=_invoked("rot"),
    )
    text = _dispatch("rot", result, opts["format"], markdown.render_rot)
    return ReapResult(text, f"{len(result.files)} files weighed for rot")


def _ghosts(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    than = _text(opts, "than")
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
    floor = max(1, _size(opts, "min_size", 1) or 1)
    result = dedupe_core.doppelgangers(
        repo,
        excludes=_texts(opts, "exclude"),
        min_size=floor,
        invoked=_invoked("doppelgangers"),
    )
    text = _dispatch("doppelgangers", result, opts["format"], markdown.render_doppelgangers)
    summary = (
        f"{len(result.clusters)} clusters, "
        f"{fsutil.human_size(result.reclaimable_bytes)} reclaimable"
    )
    return ReapResult(text, summary)


def _bloat(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = dedupe_core.bloat(
        repo,
        limit=_number(opts, "limit") or dedupe_core.DEFAULT_LIMIT,
        excludes=_texts(opts, "exclude"),
        invoked=_invoked("bloat"),
    )
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
    baseline_file = _text(opts, "baseline")
    known = rules_core.load_baseline(Path(baseline_file)) if baseline_file else None
    result = rules_core.exhume(
        repo,
        rules=rules,
        with_entropy=not opts["no_entropy"],
        baseline=known,
        since_ref=_text(opts, "since"),
        invoked=_invoked("exhume"),
    )
    text = _dispatch("exhume", result, opts["format"], markdown.render_exhume)
    summary = f"{len(result.findings)} findings, {result.blobs_scanned} blobs scanned"
    if result.suppressed:
        summary += f", {result.suppressed} baselined"
    return ReapResult(text, summary, cursed=bool(result.findings))


def _veil(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    name = _text(opts, "file") or ""
    if not name:
        raise ValueError("veil needs a file: the artifact to scrub")
    path = Path(name)
    if not path.is_absolute():
        path = Path(repo.path) / path  # relative files anchor to the source
    if not path.is_file():
        raise ValueError(f"no such artifact: {name}")
    text = path.read_text(encoding="utf-8", errors="replace")
    rules = rules_core.load_rules(config.custom_rules())
    result, veiled = rules_core.veil(
        text, name, repo, rules=rules, with_entropy=not opts["no_entropy"], invoked=_invoked("veil")
    )
    return ReapResult(veiled, f"{result.total} replacements; what was hidden stays hidden")


def _omens(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = risk_core.omens(
        repo,
        lens=opts["lens"],
        limit=_number(opts, "limit"),
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


def _ward(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    policy, policy_source = config.ward_policy()
    rules = rules_core.load_rules(config.custom_rules())
    result = ward_core.ward(
        repo,
        policy,
        policy_source=policy_source,
        rules=rules,
        weights=config.omens_weights(),
        invoked=_invoked("ward"),
    )
    text = _dispatch("ward", result, opts["format"], markdown.render_ward)
    broken = sum(1 for c in result.checks if not c.ok)
    summary = f"{len(result.checks)} wards, {broken} broken"
    return ReapResult(text, summary, cursed=result.cursed)


def _exorcise(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    floor = _size(opts, "min_size", exorcise_core.DEFAULT_MIN_SIZE) or 0
    rules = rules_core.load_rules(config.custom_rules())
    result = exorcise_core.exorcise(
        repo,
        rules=rules,
        min_size=floor,
        secrets=not opts["no_secrets"],
        invoked=_invoked("exorcise"),
    )
    text = _dispatch("exorcise", result, opts["format"], markdown.render_exorcise)
    summary = (
        f"{len(result.targets)} bodies to expel (plan only)"
        if result.targets
        else "the walls are clean"
    )
    return ReapResult(text, summary, cursed=bool(result.targets))


def _prophecy(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = prophecy_core.prophecy(
        repo,
        horizon_days=_number(opts, "horizon") or prophecy_core.DEFAULT_HORIZON_DAYS,
        limit=_number(opts, "limit"),
        invoked=_invoked("prophecy"),
    )
    text = _dispatch("prophecy", result, opts["format"], markdown.render_prophecy)
    return ReapResult(text, f"{len(result.prophecies)} prophecies read")


# --------------------------------------------------------------------------
# deeper necromancy (Phase 12)
# --------------------------------------------------------------------------


def _wake(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = wake_core.wake(repo, since=_text(opts, "since"), invoked=_invoked("wake"))
    text = _dispatch("wake", result, opts["format"], markdown.render_wake)
    since = f"since {result.since}" if result.since else "whole history"
    return ReapResult(text, f"{result.commits} commits {since}, bump {result.suggested_bump}")


def _possession(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    threshold = _decimal(opts, "threshold", possession_core.DEFAULT_THRESHOLD)
    if not 0 < threshold <= 1:
        raise ValueError("the threshold must be between 0 and 1")
    result = possession_core.possession(
        repo,
        threshold=threshold,
        limit=_number(opts, "limit"),
        invoked=_invoked("possession"),
    )
    text = _dispatch("possession", result, opts["format"], markdown.render_possession)
    return ReapResult(text, f"{len(result.files)} files, {result.possessed_count} possessed")


def _revenant(repo: RepoRef, opts: dict[str, Any]) -> ReapResult:
    result = revenant_core.revenant(
        repo,
        min_fixes=_number(opts, "fixes") or revenant_core.DEFAULT_MIN_FIXES,
        invoked=_invoked("revenant"),
    )
    text = _dispatch("revenant", result, opts["format"], markdown.render_revenant)
    return ReapResult(
        text, f"{len(result.revenants)} revenants, {len(result.offenders)} repeat offenders"
    )


# --------------------------------------------------------------------------
# the registry
# --------------------------------------------------------------------------

#: Every ritual's options mirror its CLI command's flags, with three
#: deliberate omissions: `--out` (the chambers save with `s`), `--schema`
#: (a CLI-only introspection switch), and the CI gates `--fail-on` /
#: `--fail-over` (a chamber badges what it found instead of exiting 3).
#: `--depth` is omitted too: it is the *clone* depth, and one Sanctum source
#: is reaped by ritual after ritual -- a shallow crypt would blind whichever
#: history ritual came next.
OPERATIONS: list[Operation] = [
    Operation(
        "limbs",
        "hierarchical file listing",
        "reaping",
        False,
        _limbs,
        (
            NumberOpt("depth", "depth (levels to descend)"),
            ToggleOpt("dirs_only", "dirs only (crypts, no souls)"),
            ToggleOpt("sizes", "sizes"),
            ToggleOpt("lines", "lines"),
            _exclude_opt(),
            _ref_opt(),
            _format_opt("md", "json"),
        ),
    ),
    Operation(
        "harvest",
        "gather *.md into one artifact",
        "reaping",
        False,
        _harvest,
        (
            ListOpt("pattern", "pattern (globs; *.md)"),
            _exclude_opt(),
            TextOpt("max_file_size", "max file size (e.g. 1MB)"),
            TextOpt("max_total_size", "max total size (e.g. 20MB)"),
            ToggleOpt("include_binary", "include binary"),
            _ref_opt(),
        ),
    ),
    Operation(
        "scavenge",
        "steal skill folders into a library",
        "reaping",
        False,
        _scavenge,
        (
            TextOpt("out", "out (the library directory)", default="skill-crypt"),
            _exclude_opt(),
            _ref_opt(),
            _format_opt("md", "json", *fsutil.ARCHIVE_FORMATS),
        ),
        writes=True,
    ),
    Operation(
        "conjure",
        "bundle the repo for an LLM",
        "packing",
        False,
        _conjure,
        (
            _exclude_opt(),
            TextOpt("max_file_size", "max file size (e.g. 1MB)"),
            TextOpt("max_total_size", "max total size (e.g. 20MB)"),
            ToggleOpt("sha256", "sha256 (hash every soul)"),
            NumberOpt("split_tokens", "split tokens (shard it)"),
            ToggleOpt("veil", "veil (scrub secrets while packing)"),
            _ref_opt(),
        ),
    ),
    Operation(
        "census",
        "file-type census",
        "packing",
        False,
        _census,
        (_exclude_opt(), _ref_opt(), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "unfinished",
        "TODO/FIXME/HACK/XXX",
        "packing",
        False,
        _unfinished,
        (
            ToggleOpt("age", "age (how long it has haunted)"),
            _exclude_opt(),
            _ref_opt(),
            _format_opt(*_ALL_FORMATS),
        ),
    ),
    Operation(
        "bones",
        "structure without the flesh",
        "packing",
        False,
        _bones,
        (_exclude_opt(), _ref_opt(), _format_opt("md", "json")),
    ),
    Operation(
        "chronicle",
        "commit history",
        "necromancy",
        True,
        _chronicle,
        (
            ToggleOpt("changelog", "changelog (group by tag)"),
            NumberOpt("max_count", "max count (newest N commits)"),
            _ref_opt(),
            _format_opt(*_ALL_FORMATS),
        ),
    ),
    Operation(
        "souls",
        "contributors",
        "necromancy",
        True,
        _souls,
        # the heatmap is the chamber's default (the CLI's is off): a screen
        # has room for it, and it is the point of looking at souls at all.
        (ToggleOpt("heatmap", "heatmap", default=True), _ref_opt(), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "haunt",
        "churn hotspots",
        "necromancy",
        True,
        _haunt,
        (NumberOpt("limit", "limit (top N)"), _ref_opt(), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "autopsy",
        "one file's whole story",
        "necromancy",
        True,
        _autopsy,
        (
            TextOpt("path", "path (the file to examine)"),
            ToggleOpt("no_follow", "no follow (do not follow renames)"),
            _ref_opt(),
            _format_opt("md", "json"),
        ),
        positional="path",
        source_arg="flag",
    ),
    Operation(
        "graveyard",
        "files that lived and died",
        "necromancy",
        True,
        _graveyard,
        (_ref_opt(), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "rot",
        "staleness report",
        "necromancy",
        True,
        _rot,
        (
            NumberOpt("limit", "limit (top N)"),
            _exclude_opt(),
            _ref_opt(),
            _format_opt(*_ALL_FORMATS),
        ),
    ),
    Operation(
        "ghosts",
        "branch hygiene",
        "necromancy",
        True,
        _ghosts,
        (TextOpt("than", "than (e.g. 90d)"), _ref_opt(), _format_opt(*_ALL_FORMATS)),
    ),
    Operation(
        "tombstone",
        "the stats card",
        "necromancy",
        True,
        _tombstone,
        (_ref_opt(), _format_opt("md", "json")),
    ),
    Operation(
        "doppelgangers",
        "duplicate files",
        "forensics",
        False,
        _doppelgangers,
        (
            TextOpt("min_size", "min size (e.g. 4KB)"),
            _exclude_opt(),
            _ref_opt(),
            _format_opt(*_ALL_FORMATS),
        ),
    ),
    Operation(
        "bloat",
        "the heaviest bodies",
        "forensics",
        False,
        _bloat,
        (
            NumberOpt("limit", "limit (top N)", default=dedupe_core.DEFAULT_LIMIT),
            _exclude_opt(),
            _ref_opt(),
            _format_opt(*_ALL_FORMATS),
        ),
    ),
    Operation(
        "exhume",
        "secrets in the history",
        "dark arts",
        True,
        _exhume,
        (
            ToggleOpt("no_entropy", "no entropy (signatures only)"),
            TextOpt("since", "since (only newer blobs)"),
            TextOpt("baseline", "baseline (known findings)"),
            _ref_opt(),
            _format_opt(*_ALL_FORMATS),
        ),
    ),
    Operation(
        "veil",
        "scrub an artifact before it leaves",
        "dark arts",
        False,
        _veil,
        (
            TextOpt("file", "file (the artifact to veil)"),
            ToggleOpt("no_entropy", "no entropy (signatures only)"),
        ),
        positional="file",
        source_arg="none",
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
            _ref_opt(),
            _format_opt(*_ALL_FORMATS),
        ),
    ),
    Operation(
        "plague",
        "dependency advisories",
        "dark arts",
        False,
        _plague,
        # offline by default (the CLI's default is online): a chamber must not
        # reach the OSV oracle just because you highlighted the ritual.
        (
            ToggleOpt("offline", "offline (no network)", default=True),
            _ref_opt(),
            _format_opt(*_ALL_FORMATS),
        ),
    ),
    Operation(
        "wake",
        "changelog draft since the last tag",
        "necromancy",
        True,
        _wake,
        (
            TextOpt("since", "since (tag or ref)"),
            _ref_opt(),
            _format_opt("md", "json"),
        ),
    ),
    Operation(
        "possession",
        "who holds each file",
        "necromancy",
        True,
        _possession,
        (
            FloatOpt(
                "threshold",
                "threshold (0-1)",
                default=possession_core.DEFAULT_THRESHOLD,
            ),
            NumberOpt("limit", "limit (top N)"),
            _ref_opt(),
            _format_opt("md", "json"),
        ),
    ),
    Operation(
        "revenant",
        "what will not stay buried",
        "necromancy",
        True,
        _revenant,
        (
            NumberOpt(
                "fixes", "fixes (that make an offender)", default=revenant_core.DEFAULT_MIN_FIXES
            ),
            _ref_opt(),
            _format_opt("md", "json"),
        ),
    ),
    Operation(
        "lineage",
        "who first summoned a line",
        "necromancy",
        True,
        _lineage,
        (
            TextOpt("needle", "needle (the string to trace)"),
            ToggleOpt("regex", "regex (git -G)"),
            TextOpt("path", "path (only trace within)"),
            _ref_opt(),
            _format_opt("md", "json"),
        ),
        positional="needle",
        source_arg="flag",
    ),
    Operation(
        "prophecy",
        "which files demand attention next",
        "dark arts",
        True,
        _prophecy,
        (
            NumberOpt("horizon", "horizon (days)", default=prophecy_core.DEFAULT_HORIZON_DAYS),
            NumberOpt("limit", "limit (top N)"),
            _ref_opt(),
            _format_opt("md", "json"),
        ),
    ),
    Operation(
        "exorcise",
        "the purge plan (never performed)",
        "dark arts",
        True,
        _exorcise,
        (
            TextOpt("min_size", "min size (e.g. 1MB)"),
            ToggleOpt("no_secrets", "no secrets (plan for bloat only)"),
            _ref_opt(),
            _format_opt("md", "json"),
        ),
    ),
    Operation(
        "ward",
        "the composite CI gate",
        "dark arts",
        True,
        _ward,
        (_ref_opt(), _format_opt("md", "json")),
    ),
]

OPERATIONS_BY_KEY: dict[str, Operation] = {op.key: op for op in OPERATIONS}

#: Sidebar section order.
GROUPS: tuple[str, ...] = ("reaping", "packing", "necromancy", "forensics", "dark arts")


# --------------------------------------------------------------------------
# the headless twin -- CLI args equivalent to a chamber's option values
# --------------------------------------------------------------------------


def incantation_args(op: Operation, opts: dict[str, Any]) -> list[str]:
    """The CLI flags equivalent to these option values.

    This is what makes nothing in the Sanctum TUI-trapped: the Grimoire saves
    these args into a recipe `cast` can run, and the console shows them as
    the reproducible invocation. Only non-default values appear, so the
    incantation stays as short as what a human would type. Toggles are the
    CLI's store-true flags: True emits the flag, False emits nothing; a
    ListOpt repeats its flag once per token, as the CLI's `--exclude` does.
    """
    args: list[str] = []
    for spec in op.options:
        if spec.name == op.positional:
            continue  # rides as the CLI positional, not a flag
        value = opts.get(spec.name, spec.default)
        flag = "--" + spec.name.replace("_", "-")
        if isinstance(spec, ToggleOpt):
            if value:
                args.append(flag)
        elif isinstance(spec, ListOpt):
            for token in _texts(opts, spec.name):
                args += [flag, token]
        elif isinstance(spec, NumberOpt):
            number = _number(opts, spec.name)
            if number is not None and number != spec.default:
                args += [flag, str(number)]
        else:  # ChoiceOpt, FloatOpt, or TextOpt
            text = str(value).strip() if value is not None else ""
            if text and text != str(spec.default):
                args += [flag, text]
    return args


def incantation_argv(op: Operation, source: str, opts: dict[str, Any]) -> list[str]:
    """Everything after `reaper <key>`: positional, source, then the flags.

    Shaped by the ritual's real CLI grammar, so the twin stays castable:
    `autopsy PATH -s SOURCE`, `veil FILE` (no source), `limbs SOURCE`.
    The source is dropped when it is the CLI's own default (`.`).
    """
    args: list[str] = []
    if op.positional:
        value = str(opts.get(op.positional) or "").strip()
        if value:
            args.append(value)
    if op.source_arg == "positional":
        args.append(source)
    elif op.source_arg == "flag" and source != ".":
        args += ["-s", source]
    return args + incantation_args(op, opts)


# --------------------------------------------------------------------------
# the Reliquary -- one triage pass unifying the security-and-risk rituals
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TriageRow:
    """One finding on the Reliquary's slab, comparable across rituals."""

    severity: float  # 0..1; the board sorts most-cursed first
    ritual: str  # which ritual surfaced it
    subject: str  # the file or package concerned
    detail: str  # masked preview / score / advisory -- never a raw secret


@dataclass
class TriageReport:
    """Everything the Reliquary found, sorted most-cursed first."""

    rows: list[TriageRow] = field(default_factory=list)
    cursed: bool = False
    summary: str = ""
    errors: list[str] = field(default_factory=list)  # rituals that failed, and why


_EXHUME_SEVERITY = {"high": 1.0, "medium": 0.75, "low": 0.5}


def triage(repo: RepoRef, limit: int = 20) -> TriageReport:
    """Run exhume, omens, plague (offline), and rot; merge onto one slab.

    Each ritual that fails (plain folder, no manifests) contributes an error
    line instead of taking the whole board down -- a triage view that hides a
    failed scan is worse than none.
    """
    report = TriageReport()

    def _attempt(name: str, fn: Callable[[], list[TriageRow]]) -> None:
        try:
            report.rows.extend(fn())
        except Exception as exc:
            report.errors.append(f"{name}: {exc}")

    def _exhume() -> list[TriageRow]:
        rules = rules_core.load_rules(config.custom_rules())
        result = rules_core.exhume(repo, rules=rules, invoked=_invoked("exhume"))
        return [
            TriageRow(
                severity=_EXHUME_SEVERITY.get(f.severity, 0.5),
                ritual="exhume",
                subject=f.path,
                detail=f"{f.rule}: {f.preview}",
            )
            for f in result.findings
        ]

    def _omens() -> list[TriageRow]:
        result = risk_core.omens(
            repo, limit=limit, weights=config.omens_weights(), invoked=_invoked("omens")
        )
        return [
            TriageRow(
                severity=round(0.9 * o.score, 3),  # a prophecy never outranks a found secret
                ritual="omens",
                subject=o.path,
                detail=f"risk {o.score:.2f} ({o.commits} commits, {o.bug_commits} fixes)",
            )
            for o in result.omens
            if o.score >= 0.4
        ]

    def _plague() -> list[TriageRow]:
        result = plague_core.plague(repo, offline=True, invoked=_invoked("plague"))
        return [
            TriageRow(
                severity=0.9,
                ritual="plague",
                subject=f"{a.package} {a.version}",
                detail=f"{a.id}: {a.summary}",
            )
            for a in result.afflictions
        ]

    def _rot() -> list[TriageRow]:
        result = hygiene_core.rot(repo, limit=limit, invoked=_invoked("rot"))
        return [
            TriageRow(
                severity=round(min(0.4, f.age_days / 3650 * 0.4), 3),  # rot is never urgent
                ritual="rot",
                subject=f.path,
                detail=f"untouched {f.age_days} days (since {f.last_commit[:10]})",
            )
            for f in result.files
            if f.age_days >= 180
        ]

    _attempt("exhume", _exhume)
    _attempt("omens", _omens)
    _attempt("plague", _plague)
    _attempt("rot", _rot)

    report.rows.sort(key=lambda r: (-r.severity, r.ritual, r.subject))
    report.cursed = any(r.ritual in ("exhume", "plague") for r in report.rows)
    counts = ", ".join(
        f"{ritual} {n}"
        for ritual in ("exhume", "omens", "plague", "rot")
        if (n := sum(1 for r in report.rows if r.ritual == ritual))
    )
    report.summary = counts or "nothing to triage; the slab is clean"
    return report


def render_triage(report: TriageReport) -> str:
    """The Reliquary's one-key export: the slab as a markdown table."""
    lines = ["# the reliquary", "", "| severity | ritual | subject | detail |"]
    lines.append("| ---: | --- | --- | --- |")
    for row in report.rows:
        subject = row.subject.replace("|", "\\|")
        detail = row.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row.severity:.2f} | {row.ritual} | {subject} | {detail} |")
    lines.append("")
    lines.append(report.summary)
    for error in report.errors:
        lines.append(f"- skipped {error}")
    return "\n".join(lines) + "\n"
