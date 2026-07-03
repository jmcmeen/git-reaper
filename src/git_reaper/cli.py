"""The CLI face of the reaper: a thin Typer adapter over git_reaper.core.

Rules of the house:
- Artifacts go to --out or stdout. Narration goes to stderr, always.
- Every themed message still carries the plain cause and a next step.
- Exit codes: 0 rest in peace, 1 the ritual failed, 2 bad incantation,
  3 cursed (the scan succeeded and found what you feared).
"""

from __future__ import annotations

import json
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from git_reaper import __version__, art, cache, config, fsutil, schemas
from git_reaper.core import census as census_core
from git_reaper.core import dedupe as dedupe_core
from git_reaper.core import fleet as fleet_core
from git_reaper.core import graveyard as graveyard_core
from git_reaper.core import harvest as harvest_core
from git_reaper.core import history as history_core
from git_reaper.core import hygiene as hygiene_core
from git_reaper.core import pack as pack_core
from git_reaper.core import plague as plague_core
from git_reaper.core import pulse as pulse_core
from git_reaper.core import risk as risk_core
from git_reaper.core import rules as rules_core
from git_reaper.core import scan as scan_core
from git_reaper.core import scry as scry_core
from git_reaper.core import skeleton as skeleton_core
from git_reaper.core import tree as tree_core
from git_reaper.core import unpack as unpack_core
from git_reaper.core.source import ResolvedSource, resolve_source
from git_reaper.formatters import csvfmt, htmlfmt, jsonfmt, markdown
from git_reaper.gitio import GitError
from git_reaper.models import RepoRef
from git_reaper.theme import make_console, theme_enabled


def _seasonal_footer(*_args: object, **_kwargs: object) -> None:
    """The Friday-the-13th one-liner, after any successful command."""
    if theme_enabled(state.plain) and state.verbosity >= 0:
        dread = art.seasonal_footer()
        if dread:
            state.console.print(f"[ember]{escape(dread)}[/ember]")


app = typer.Typer(
    name="reaper",
    help="A spooky utility for data mining git repositories.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    result_callback=_seasonal_footer,
)

#: Exit code 3: the scan succeeded and found what you feared.
CURSED = 3


@dataclass
class State:
    plain: bool = False
    verbosity: int = 0  # -1 whisper, 0 default, 1 moan, 2 shriek
    console: Console = None  # type: ignore[assignment]


state = State()


def _say(style: str, message: str, level: int = 0) -> None:
    """Narrate to stderr if the current verbosity allows it."""
    if state.verbosity >= level:
        state.console.print(f"[{style}]\\[{style}][/{style}] {escape(message)}")


def _die(message: str, hint: str | None = None) -> typer.Exit:
    _say("blood", f"the ritual failed: {message}")
    if hint:
        _say("ash", f"next step: {hint}")
    return typer.Exit(code=1)


def _invocation() -> str:
    return "reaper " + " ".join(shlex.quote(a) for a in sys.argv[1:])


def _parse_days(text: str) -> int:
    """A haunting threshold like '90d' or '12h', floored to whole days."""
    return int(cache.parse_age(text) // 86400)


def _emit(text: str, out: Path | None) -> None:
    """Write an artifact to --out or stdout. Chatter never comes here."""
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def _print_schema(command: str) -> None:
    schema = schemas.schema_for(schemas.COMMAND_MODELS[command])
    sys.stdout.write(json.dumps(schema, indent=2) + "\n")


def _validate_format(fmt: str, allowed: tuple[str, ...] = ("md", "json")) -> None:
    if fmt not in allowed:
        choices = " or ".join(f"--format {a}" for a in allowed)
        raise _die(f"unknown format {fmt!r}", f"use {choices}")


def _resolve(source: str, ref: str | None = None, depth: int | None = 1) -> ResolvedSource:
    try:
        resolved = resolve_source(source, ref=ref, depth=depth)
    except (FileNotFoundError, ValueError, GitError) as exc:
        raise _die(str(exc), "check the path or URL; `reaper pulse` checks your setup") from exc
    if resolved.cached:
        _say("necro", f"catacombs hit: {resolved.repo.source} already interred, reusing")
    return resolved


def _version_callback(value: bool) -> None:
    if value:
        sys.stdout.write(f"git-reaper {__version__}\n")
        raise typer.Exit()


@app.callback()
def main(
    plain: bool = typer.Option(
        False, "--plain", "--no-theme", help="Clean ASCII output; no color, no art."
    ),
    whisper: bool = typer.Option(False, "-q", "--whisper", help="Only errors."),
    verbose: int = typer.Option(
        0, "-v", "--moan", count=True, help="More narration; -vv (--shriek) for debug."
    ),
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Print version."
    ),
) -> None:
    state.plain = plain
    state.verbosity = -1 if whisper else verbose
    state.console = make_console(plain=plain, quiet=False)


def _banner() -> None:
    if theme_enabled(state.plain) and state.verbosity >= 0:
        special = art.seasonal_banner()
        if special:
            state.console.print(f"[ember]{special}[/ember]", highlight=False)
        else:
            state.console.print(f"[eldritch]{art.piece('mini-skull')}[/eldritch]", highlight=False)


def _grimoire_rules() -> list[rules_core.Rule]:
    """The shared engine's rules: built-ins plus the grimoire's additions."""
    try:
        return rules_core.load_rules(config.custom_rules())
    except (config.GrimoireError, rules_core.RuleError) as exc:
        raise _die(str(exc), "`reaper grimoire` shows where rules come from") from exc


# --------------------------------------------------------------------------
# harvest (reap)
# --------------------------------------------------------------------------


def _harvest_impl(
    source: str,
    pattern: list[str],
    exclude: list[str],
    out: Path | None,
    ref: str | None,
    depth: int,
    max_file_size: str | None,
    max_total_size: str | None,
    include_binary: bool,
) -> None:
    """Gather files matching a pattern and concatenate them into one artifact."""
    _banner()
    try:
        file_cap = fsutil.parse_size(max_file_size) if max_file_size else None
        total_cap = fsutil.parse_size(max_total_size) if max_total_size else None
    except ValueError as exc:
        raise _die(str(exc)) from exc

    resolved = _resolve(source, ref=ref, depth=depth)
    patterns = tuple(pattern) if pattern else harvest_core.DEFAULT_PATTERNS
    try:
        result = harvest_core.harvest(
            resolved.repo,
            patterns=patterns,
            excludes=exclude,
            max_file_size=file_cap,
            max_total_size=total_cap,
            include_binary=include_binary,
            invoked=_invocation(),
        )
    except harvest_core.CapExceeded as exc:
        raise _die(str(exc)) from exc

    _say(
        "necro",
        f"gathered {len(result.files)} souls ({', '.join(patterns)}) ... "
        f"{result.total_lines:,} lines, {fsutil.human_size(result.total_bytes)}",
    )
    for skipped in result.skipped:
        _say("ember", f"skipped {skipped.path}: {skipped.skip_reason}", level=0)

    if out:
        with out.open("w", encoding="utf-8") as fh:
            markdown.write_harvest(result, fh)
        _say(
            "bone",
            f"wrote {out}  ({len(result.files)} files, ~{result.token_estimate:,} tokens)",
        )
    else:
        markdown.write_harvest(result, sys.stdout)
    _say("ash", "the reaping is complete.")


@app.command("harvest")
def harvest_cmd(
    source: str | None = typer.Argument(None, help="Local path or repo URL."),
    pattern: list[str] = typer.Option(
        [], "--pattern", "--glob", "-p", help="Glob(s) to gather (default: *.md)."
    ),
    exclude: list[str] = typer.Option([], "--exclude", "-x", help="Glob(s) to skip."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha (remote sources)."),
    depth: int = typer.Option(1, "--depth", help="Clone depth for remote sources."),
    max_file_size: str | None = typer.Option(
        None, "--max-file-size", help="Skip files larger than this (e.g. 1MB)."
    ),
    max_total_size: str | None = typer.Option(
        None, "--max-total-size", help="Abort past this total (e.g. 100MB)."
    ),
    include_binary: bool = typer.Option(False, "--include-binary", help="Do not skip binaries."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Gather files matching a pattern into one flat artifact."""
    if schema:
        _print_schema("harvest")
        return
    if source is None:
        raise _die("no source given", "pass a local path or a repo URL")
    _harvest_impl(
        source,
        pattern,
        exclude,
        out,
        ref,
        depth,
        max_file_size,
        max_total_size,
        include_binary,
    )


# --------------------------------------------------------------------------
# limbs (the file tree)
# --------------------------------------------------------------------------


@app.command("limbs")
def limbs_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    depth: int | None = typer.Option(None, "--depth", "-d", help="Max depth."),
    dirs_only: bool = typer.Option(False, "--dirs-only", help="Directories only."),
    sizes: bool = typer.Option(False, "--sizes", help="Show file sizes."),
    lines: bool = typer.Option(False, "--lines", help="Show line counts."),
    exclude: list[str] = typer.Option([], "--exclude", "-x", help="Glob(s) to skip."),
    fmt: str = typer.Option("md", "--format", "-f", help="md or json."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha (remote sources)."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Emit a hierarchical file listing (the tree, limb by limb)."""
    if schema:
        _print_schema("limbs")
        return
    _validate_format(fmt)
    _banner()
    resolved = _resolve(source, ref=ref)
    result = tree_core.tree(
        resolved.repo,
        max_depth=depth,
        dirs_only=dirs_only,
        with_sizes=sizes,
        with_lines=lines,
        excludes=exclude,
        invoked=_invocation(),
    )
    _say("necro", f"mapped {result.dir_count} crypts, {result.file_count} souls")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    else:
        _emit(markdown.render_tree(result, with_sizes=sizes, with_lines=lines), out)


# --------------------------------------------------------------------------
# conjure / reanimate (the round trip)
# --------------------------------------------------------------------------


def _part_path(out: Path, number: int) -> Path:
    return out.with_name(f"{out.stem}.part{number:02d}{out.suffix}")


@app.command("conjure")
def conjure_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    exclude: list[str] = typer.Option([], "--exclude", "-x", help="Glob(s) to skip."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha (remote sources)."),
    depth: int = typer.Option(1, "--depth", help="Clone depth for remote sources."),
    max_file_size: str | None = typer.Option(
        None, "--max-file-size", help="Skip files larger than this (e.g. 1MB)."
    ),
    max_total_size: str | None = typer.Option(
        None, "--max-total-size", help="Abort past this total (e.g. 100MB)."
    ),
    sha256: bool = typer.Option(
        False, "--sha256", help="Record per-file hashes (enables reanimate --verify)."
    ),
    split_tokens: int | None = typer.Option(
        None, "--split-tokens", help="Shard into parts of at most this many tokens."
    ),
    veil: bool = typer.Option(
        False, "--veil", help="Scrub secrets and configured patterns from packed content."
    ),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Bundle a repo into a single LLM-ingestible artifact."""
    if schema:
        _print_schema("conjure")
        return
    _banner()
    try:
        file_cap = fsutil.parse_size(max_file_size) if max_file_size else None
        total_cap = fsutil.parse_size(max_total_size) if max_total_size else None
    except ValueError as exc:
        raise _die(str(exc)) from exc
    veil_rules = _grimoire_rules() if veil else None
    resolved = _resolve(source, ref=ref, depth=depth)
    try:
        result = pack_core.conjure(
            resolved.repo,
            excludes=exclude,
            max_file_size=file_cap,
            max_total_size=total_cap,
            with_sha256=sha256,
            split_tokens=split_tokens,
            veil_rules=veil_rules,
            invoked=_invocation(),
        )
    except harvest_core.CapExceeded as exc:
        raise _die(str(exc)) from exc

    _say(
        "necro",
        f"conjured {len(result.files)} souls ... ~{result.token_estimate:,} tokens"
        + (f" in {result.parts} parts" if result.parts > 1 else ""),
    )
    for skipped in result.skipped:
        _say("ember", f"skipped {skipped.path}: {skipped.skip_reason}")
    if result.veiled:
        _say("ember", f"veiled {result.veiled} matches before packing")

    for number, text in pack_core.iter_parts(result, veil_rules=veil_rules):
        if out is None:
            sys.stdout.write(text)
        else:
            target = _part_path(out, number) if result.parts > 1 else out
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            _say("bone", f"wrote {target}")
    _say("ash", "the conjuring is complete.")


@app.command("reanimate")
def reanimate_cmd(
    artifacts: list[Path] = typer.Argument(None, help="Conjured artifact file(s), parts welcome."),
    out: Path = typer.Option(
        Path("."), "--out", "-o", help="Directory to raise the tree in (must be empty)."
    ),
    force: bool = typer.Option(False, "--force", help="Write into a non-empty directory."),
    verify: bool = typer.Option(False, "--verify", help="Check per-file sha256 meta."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Reconstruct a directory tree from a conjured artifact."""
    if schema:
        _print_schema("reanimate")
        return
    if not artifacts:
        raise _die("no artifact given", "pass one or more conjured artifact files")
    _banner()
    texts = []
    for artifact in artifacts:
        if not artifact.is_file():
            raise _die(f"no such artifact: {artifact}")
        with artifact.open("r", encoding="utf-8", newline="") as fh:
            texts.append(fh.read())
    try:
        result = unpack_core.reanimate("\n".join(texts), out, force=force, verify=verify)
    except unpack_core.ReanimateError as exc:
        raise _die(str(exc)) from exc

    _say("necro", f"reanimated {len(result.files)} souls into {result.out}")
    if verify:
        for path in result.verify_failures:
            _say("blood", f"hash mismatch: {path}")
        if result.verify_failures:
            raise _die(f"{len(result.verify_failures)} corpses failed verification")
        checked = sum(1 for f in result.files if f.verified)
        _say("necro", f"verified {checked} of {len(result.files)} hashes")
    _say("ash", "what was written is risen.")


# --------------------------------------------------------------------------
# census / unfinished (analysis)
# --------------------------------------------------------------------------


@app.command("census")
def census_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    exclude: list[str] = typer.Option([], "--exclude", "-x", help="Glob(s) to skip."),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha (remote sources)."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """File-type census: counts, sizes, lines, languages, token estimate."""
    if schema:
        _print_schema("census")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    _banner()
    resolved = _resolve(source, ref=ref)
    result = census_core.census(resolved.repo, excludes=exclude, invoked=_invocation())
    _say("necro", f"counted {result.total_files} souls across {len(result.extensions)} kinds")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_census(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("census", result), out)
    else:
        _emit(markdown.render_census(result), out)


@app.command("unfinished")
def unfinished_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    exclude: list[str] = typer.Option([], "--exclude", "-x", help="Glob(s) to skip."),
    age: bool = typer.Option(False, "--age", help="Add how long each marker has haunted."),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha (remote sources)."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Scan for TODO / FIXME / HACK / XXX markers."""
    if schema:
        _print_schema("unfinished")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    _banner()
    resolved = _resolve(source, ref=ref)
    result = scan_core.unfinished(
        resolved.repo, excludes=exclude, with_age=age, invoked=_invocation()
    )
    _say("necro", f"found {len(result.markers)} unfinished things")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_unfinished(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("unfinished", result), out)
    else:
        _emit(markdown.render_unfinished(result), out)


# --------------------------------------------------------------------------
# grimoire / cast (config and recipes)
# --------------------------------------------------------------------------


@app.command("grimoire")
def grimoire_cmd(
    fmt: str = typer.Option("md", "--format", "-f", help="md or json."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Show effective configuration, where it came from, and stored recipes."""
    if schema:
        _print_schema("grimoire")
        return
    _validate_format(fmt)
    try:
        result = config.load_grimoire()
    except config.GrimoireError as exc:
        raise _die(str(exc)) from exc
    if fmt == "json":
        _emit(jsonfmt.render(result), None)
        return
    table = Table(title="the grimoire", title_style="eldritch", border_style="grave")
    table.add_column("setting", style="bone")
    table.add_column("value", style="ash")
    table.add_column("from", style="ash")
    for value in result.settings:
        table.add_row(value.key, escape(value.value), value.source)
    state.console.print(table)
    if result.recipes:
        recipes = Table(title="recipes", title_style="eldritch", border_style="grave")
        recipes.add_column("name", style="bone")
        recipes.add_column("incantation", style="ash")
        recipes.add_column("from", style="ash")
        for recipe in result.recipes:
            incantation = " ".join([recipe.command, *recipe.args])
            recipes.add_row(recipe.name, escape(incantation), recipe.source)
        state.console.print(recipes)
    else:
        _say("ash", "no recipes inscribed; add [recipes.<name>] to .reaperrc")


@app.command(
    "cast",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def cast_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Recipe name from the grimoire."),
) -> None:
    """Run a saved recipe; extra arguments are passed through as overrides."""
    try:
        recipe = config.find_recipe(name)
    except config.GrimoireError as exc:
        raise _die(str(exc)) from exc
    if recipe is None:
        raise _die(f"no recipe named {name!r}", "`reaper grimoire` lists what is inscribed")
    if recipe.command == "cast":
        raise _die("a recipe cannot cast cast; the recursion would never rest")
    argv = (["--plain"] if state.plain else []) + [recipe.command, *recipe.args, *ctx.args]
    _say("necro", f"casting {name}: reaper {' '.join(argv)}")
    command = typer.main.get_command(app)
    try:
        # standalone mode prints usage errors itself and always leaves via
        # SystemExit (0 on success); translate the code, never swallow it.
        command.main(args=argv, prog_name="reaper")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code:
            _say("blood", f"recipe {name!r} failed (exit {code})")
            raise typer.Exit(code=code) from exc


# --------------------------------------------------------------------------
# git necromancy: chronicle, souls, haunt, autopsy, graveyard, resurrect,
# ghosts, rot, tombstone. History needs a full clone, so remote sources are
# fetched deep (depth=None), not shallow.
# --------------------------------------------------------------------------


def _resolve_history(source: str, ref: str | None) -> ResolvedSource:
    return _resolve(source, ref=ref, depth=None)


def _history_die(exc: GitError) -> typer.Exit:
    return _die(str(exc), "`reaper pulse` checks git; history needs a real repo")


@app.command("chronicle")
def chronicle_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    changelog: bool = typer.Option(False, "--changelog", help="Group commits by tag."),
    max_count: int | None = typer.Option(
        None, "--max-count", "-n", help="Only the newest N commits."
    ),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Extract commit history to markdown, JSON, or CSV."""
    if schema:
        _print_schema("chronicle")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    _banner()
    resolved = _resolve_history(source, ref)
    try:
        result = history_core.chronicle(
            resolved.repo, changelog=changelog, max_count=max_count, invoked=_invocation()
        )
    except GitError as exc:
        raise _history_die(exc) from exc
    _say("necro", f"transcribed {len(result.commits)} commits")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_chronicle(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("chronicle", result), out)
    else:
        _emit(markdown.render_chronicle(result), out)


@app.command("souls")
def souls_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    heatmap: bool = typer.Option(False, "--heatmap", help="Add the activity heatmap."),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Contributor stats, bus factor, and the witching hour."""
    if schema:
        _print_schema("souls")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    _banner()
    resolved = _resolve_history(source, ref)
    try:
        result = history_core.souls(resolved.repo, heatmap=heatmap, invoked=_invocation())
    except GitError as exc:
        raise _history_die(exc) from exc
    _say("necro", f"counted {len(result.souls)} souls, bus factor {result.bus_factor}")
    if result.witching_hour:
        _say("eldritch", f"the witching hour is {result.witching_hour}")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_souls(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("souls", result), out)
    else:
        _emit(markdown.render_souls(result), out)


@app.command("haunt")
def haunt_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    limit: int | None = typer.Option(None, "--limit", "-n", help="Only the top N hotspots."),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Code churn and hotspots: the classic bug-risk proxy."""
    if schema:
        _print_schema("haunt")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    _banner()
    resolved = _resolve_history(source, ref)
    try:
        result = history_core.haunt(resolved.repo, limit=limit, invoked=_invocation())
    except GitError as exc:
        raise _history_die(exc) from exc
    _say("necro", f"found {len(result.hotspots)} hotspots")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_haunt(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("haunt", result), out)
    else:
        _emit(markdown.render_haunt(result), out)


@app.command("autopsy")
def autopsy_cmd(
    path: str | None = typer.Argument(None, help="File to examine (relative to the repo)."),
    source: str = typer.Option(".", "--source", "-s", help="Local path or repo URL."),
    no_follow: bool = typer.Option(False, "--no-follow", help="Do not follow renames."),
    fmt: str = typer.Option("md", "--format", "-f", help="md or json."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Deep single-file examination: birth, authors, churn, blame age."""
    if schema:
        _print_schema("autopsy")
        return
    if path is None:
        raise _die("no file given", "pass the path of a file to examine")
    _validate_format(fmt)
    _banner()
    resolved = _resolve_history(source, ref)
    try:
        result = history_core.autopsy(
            resolved.repo, path, follow=not no_follow, invoked=_invocation()
        )
    except GitError as exc:
        raise _history_die(exc) from exc
    _say("necro", f"examined {result.path}: {result.commits} commits, {len(result.authors)} hands")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    else:
        _emit(markdown.render_autopsy(result), out)


@app.command("graveyard")
def graveyard_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """List every file that ever lived and died in the repo."""
    if schema:
        _print_schema("graveyard")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    _banner()
    resolved = _resolve_history(source, ref)
    try:
        result = graveyard_core.graveyard(resolved.repo, invoked=_invocation())
    except GitError as exc:
        raise _history_die(exc) from exc
    _say("necro", f"counted {len(result.dead)} dead")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_graveyard(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("graveyard", result), out)
    else:
        _emit(markdown.render_graveyard(result), out)


@app.command("resurrect")
def resurrect_cmd(
    path: str | None = typer.Argument(None, help="Dead file to raise (its path in the repo)."),
    source: str = typer.Option(".", "--source", "-s", help="Local path or repo URL."),
    out: Path = typer.Option(
        Path("."), "--out", "-o", help="Directory (keeps the path) or exact file target."
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite if the target exists."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Restore a dead file from the graveyard into the working tree."""
    if schema:
        _print_schema("resurrect")
        return
    if path is None:
        raise _die("no file given", "pass the path of a dead file; `reaper graveyard` lists them")
    _banner()
    resolved = _resolve_history(source, ref)
    try:
        result = graveyard_core.resurrect(resolved.repo, path, out, force=force)
    except graveyard_core.ResurrectError as exc:
        raise _die(str(exc), "`reaper graveyard` lists what can be raised") from exc
    except GitError as exc:
        raise _history_die(exc) from exc
    _say("necro", f"raised {result.path} from {result.sha[:7]} into {result.out}")
    _say("ash", "it walks again.")


@app.command("ghosts")
def ghosts_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    than: str | None = typer.Option(
        None, "--than", help="Flag branches idle longer than this (e.g. 90d)."
    ),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Branch hygiene: activity, merged-but-undeleted, gone remotes."""
    if schema:
        _print_schema("ghosts")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    _banner()
    try:
        than_days = _parse_days(than) if than else None
    except ValueError as exc:
        raise _die(str(exc)) from exc
    resolved = _resolve_history(source, ref)
    try:
        result = hygiene_core.ghosts(resolved.repo, than_days=than_days, invoked=_invocation())
    except GitError as exc:
        raise _history_die(exc) from exc
    _say("necro", f"walked {len(result.branches)} branches")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_ghosts(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("ghosts", result), out)
    else:
        _emit(markdown.render_ghosts(result), out)


@app.command("rot")
def rot_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    limit: int | None = typer.Option(None, "--limit", "-n", help="Only the top N stalest."),
    exclude: list[str] = typer.Option([], "--exclude", "-x", help="Glob(s) to skip."),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Staleness report: files untouched the longest."""
    if schema:
        _print_schema("rot")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    _banner()
    resolved = _resolve_history(source, ref)
    try:
        result = hygiene_core.rot(
            resolved.repo, limit=limit, excludes=exclude, invoked=_invocation()
        )
    except GitError as exc:
        raise _history_die(exc) from exc
    _say("necro", f"weighed {len(result.files)} files for rot")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_rot(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("rot", result), out)
    else:
        _emit(markdown.render_rot(result), out)


@app.command("tombstone")
def tombstone_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    fmt: str = typer.Option("md", "--format", "-f", help="md or json."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """A stats card for demos and READMEs, in ASCII tombstone art."""
    if schema:
        _print_schema("tombstone")
        return
    _validate_format(fmt)
    _banner()
    resolved = _resolve_history(source, ref)
    try:
        result = history_core.tombstone(resolved.repo, invoked=_invocation())
    except GitError as exc:
        raise _history_die(exc) from exc
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    else:
        _emit(markdown.render_tombstone(result), out)


# --------------------------------------------------------------------------
# dark arts: exhume, veil, omens (Phase 5)
# --------------------------------------------------------------------------


@app.command("exhume")
def exhume_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    fail_on: str | None = typer.Option(
        None, "--fail-on", help="Exit 3 when findings match: any or high."
    ),
    baseline: Path | None = typer.Option(
        None, "--baseline", help="JSON baseline of known findings to suppress."
    ),
    no_entropy: bool = typer.Option(
        False, "--no-entropy", help="Signatures only; skip the entropy sweep."
    ),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Scan the full history for committed secrets (previews stay masked)."""
    if schema:
        _print_schema("exhume")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    if fail_on is not None and fail_on not in ("any", "high"):
        raise _die(f"unknown --fail-on {fail_on!r}", "use --fail-on any or --fail-on high")
    _banner()
    rules = _grimoire_rules()
    known = set()
    if baseline is not None:
        try:
            known = rules_core.load_baseline(baseline)
        except rules_core.RuleError as exc:
            raise _die(str(exc)) from exc
    resolved = _resolve_history(source, ref)
    try:
        result = rules_core.exhume(
            resolved.repo,
            rules=rules,
            with_entropy=not no_entropy,
            baseline=known,
            invoked=_invocation(),
        )
    except GitError as exc:
        raise _history_die(exc) from exc

    for f in result.findings:
        where = f"{f.path}:{f.line}" + (f" @ {f.sha[:7]}" if f.sha else "")
        _say("blood", f"{f.severity}: {f.rule} in {where} ({f.preview}, masked)")
    _say(
        "necro",
        f"scanned {result.blobs_scanned} blobs: {len(result.findings)} findings"
        + (f", {result.suppressed} baselined" if result.suppressed else ""),
    )
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_exhume(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("exhume", result), out)
    else:
        _emit(markdown.render_exhume(result), out)
    if fail_on and rules_core.cursed(result, fail_on):
        _say("blood", f"the dead had secrets. exit {CURSED}.")
        raise typer.Exit(code=CURSED)


@app.command("veil")
def veil_cmd(
    artifact: str | None = typer.Argument(None, help="Artifact to veil ('-' reads stdin)."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Veiled artifact (default stdout)."),
    no_entropy: bool = typer.Option(
        False, "--no-entropy", help="Signatures only; skip the entropy sweep."
    ),
    report: str | None = typer.Option(
        None, "--report", help="Also emit the receipt: md or json (to stdout; pair with --out)."
    ),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Scrub secrets and configured patterns before an artifact leaves the crypt."""
    if schema:
        _print_schema("veil")
        return
    if artifact is None:
        raise _die("no artifact given", "pass a file to veil, or '-' to read stdin")
    if report is not None and report not in ("md", "json"):
        raise _die(f"unknown --report {report!r}", "use --report md or --report json")
    if report is not None and out is None:
        raise _die("--report needs --out", "the veiled text and the receipt both want stdout")
    rules = _grimoire_rules()
    if artifact == "-":
        text = sys.stdin.read()
        source_name = "-"
        repo = RepoRef(source="stdin", kind="local", path=".")
    else:
        path = Path(artifact)
        if not path.is_file():
            raise _die(f"no such artifact: {artifact}")
        text = path.read_text(encoding="utf-8", errors="replace")
        source_name = str(path)
        repo = RepoRef(source=str(path), kind="local", path=str(path.parent or "."))
    result, veiled = rules_core.veil(
        text, source_name, repo, rules=rules, with_entropy=not no_entropy, invoked=_invocation()
    )
    _emit(veiled, out)
    for count in result.replacements:
        _say("ember", f"veiled {count.count} x {count.rule}")
    _say("necro", f"{result.total} replacements; what was hidden stays hidden")
    if report == "json":
        sys.stdout.write(jsonfmt.render(result))
    elif report == "md":
        sys.stdout.write(markdown.render_veil(result))


@app.command("omens")
def omens_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    lens: str = typer.Option("all", "--lens", help="all, churn, bugs, age, or size."),
    limit: int | None = typer.Option(None, "--limit", "-n", help="Only the top N omens."),
    fail_over: float | None = typer.Option(
        None, "--fail-over", help="Exit 3 when any omen scores at or above this (0..1)."
    ),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Composite risk prophecy per file. Omens are hints, not fate."""
    if schema:
        _print_schema("omens")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    _banner()
    try:
        weights = config.omens_weights()
    except config.GrimoireError as exc:
        raise _die(str(exc), "`reaper grimoire` shows the [omens] table") from exc
    resolved = _resolve_history(source, ref)
    try:
        result = risk_core.omens(
            resolved.repo, lens=lens, weights=weights, limit=limit, invoked=_invocation()
        )
    except ValueError as exc:
        raise _die(str(exc)) from exc
    except GitError as exc:
        raise _history_die(exc) from exc
    _say("necro", f"read {len(result.omens)} omens through the {result.lens} lens")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_omens(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("omens", result), out)
    else:
        _emit(markdown.render_omens(result), out)
    if fail_over is not None:
        doomed = risk_core.doomed(result, fail_over)
        if doomed:
            for omen in doomed:
                _say("blood", f"doomed: {omen.path} scores {omen.score:.3f}")
            _say("blood", f"the omens are dire. exit {CURSED}.")
            raise typer.Exit(code=CURSED)


# --------------------------------------------------------------------------
# doppelgangers / bloat (folder forensics)
# --------------------------------------------------------------------------


@app.command("doppelgangers")
def doppelgangers_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    exclude: list[str] = typer.Option([], "--exclude", "-x", help="Glob(s) to skip."),
    min_size: str = typer.Option(
        "1", "--min-size", help="Ignore files smaller than this (e.g. 4KB)."
    ),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha (remote sources)."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Find duplicate files by content hash."""
    if schema:
        _print_schema("doppelgangers")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    _banner()
    try:
        floor = fsutil.parse_size(min_size)
    except ValueError as exc:
        raise _die(str(exc)) from exc
    resolved = _resolve(source, ref=ref)
    result = dedupe_core.doppelgangers(
        resolved.repo, excludes=exclude, min_size=max(1, floor), invoked=_invocation()
    )
    _say(
        "necro",
        f"found {len(result.clusters)} clusters among {result.files_scanned} files; "
        f"{fsutil.human_size(result.reclaimable_bytes)} reclaimable",
    )
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_doppelgangers(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("doppelgangers", result), out)
    else:
        _emit(markdown.render_doppelgangers(result), out)


@app.command("bloat")
def bloat_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    limit: int = typer.Option(20, "--limit", "-n", help="Top N per section."),
    exclude: list[str] = typer.Option([], "--exclude", "-x", help="Glob(s) to skip."),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Largest files in the tree, and blobs still weighing down .git."""
    if schema:
        _print_schema("bloat")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    _banner()
    resolved = _resolve_history(source, ref)
    try:
        result = dedupe_core.bloat(
            resolved.repo, limit=limit, excludes=exclude, invoked=_invocation()
        )
    except GitError as exc:
        raise _history_die(exc) from exc
    _say(
        "necro",
        f"weighed the tree ({fsutil.human_size(result.tree_bytes)}); "
        f"{fsutil.human_size(result.walls_bytes)} still in the walls",
    )
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_bloat(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("bloat", result), out)
    else:
        _emit(markdown.render_bloat(result), out)


# --------------------------------------------------------------------------
# bones / scry (Phase 6)
# --------------------------------------------------------------------------


@app.command("bones")
def bones_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    exclude: list[str] = typer.Option([], "--exclude", "-x", help="Glob(s) to skip."),
    fmt: str = typer.Option("md", "--format", "-f", help="md or json."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha (remote sources)."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Strip implementation, keep structure: the compact code map."""
    if schema:
        _print_schema("bones")
        return
    _validate_format(fmt)
    _banner()
    resolved = _resolve(source, ref=ref)
    result = skeleton_core.bones(resolved.repo, excludes=exclude, invoked=_invocation())
    _say("necro", f"stripped {result.parsed_files} files to the bone")
    if result.skipped_files:
        _say(
            "ember",
            f"{result.skipped_files} files skipped (non-Python languages need `git-reaper[bones]`)",
        )
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    else:
        _emit(markdown.render_bones(result), out)


@app.command("scry")
def scry_cmd(
    ref_a: str | None = typer.Argument(None, help="The older ref (tag, branch, sha)."),
    ref_b: str = typer.Argument("HEAD", help="The newer ref (default HEAD)."),
    source: str = typer.Option(".", "--source", "-s", help="Local path or repo URL."),
    limit: int | None = typer.Option(None, "--limit", "-n", help="Only the top N files."),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Compare two refs: churn, files, and contributors between releases."""
    if schema:
        _print_schema("scry")
        return
    if ref_a is None:
        raise _die("no ref given", "pass the older ref: `reaper scry v1.0.0 v2.0.0`")
    _validate_format(fmt, ("md", "json", "csv", "html"))
    _banner()
    resolved = _resolve_history(source, None)
    try:
        result = scry_core.scry(resolved.repo, ref_a, ref_b, limit=limit, invoked=_invocation())
    except GitError as exc:
        raise _history_die(exc) from exc
    _say(
        "necro",
        f"the glass shows {result.commits} commits, "
        f"+{result.insertions}/-{result.deletions} between {ref_a} and {ref_b}",
    )
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_scry(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("scry", result), out)
    else:
        _emit(markdown.render_scry(result), out)


# --------------------------------------------------------------------------
# plague (opt-in network: the only command that ever leaves the crypt)
# --------------------------------------------------------------------------


@app.command("plague")
def plague_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    offline: bool = typer.Option(
        False, "--offline", help="Parse manifests only; never touch the network."
    ),
    fail_on: str | None = typer.Option(
        None, "--fail-on", help="Exit 3 when afflictions are found: any."
    ),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, csv, or html."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha (remote sources)."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Check dependency manifests against the OSV database (opt-in network)."""
    if schema:
        _print_schema("plague")
        return
    _validate_format(fmt, ("md", "json", "csv", "html"))
    if fail_on is not None and fail_on != "any":
        raise _die(f"unknown --fail-on {fail_on!r}", "use --fail-on any")
    _banner()
    resolved = _resolve(source, ref=ref)
    if not offline:
        _say("ember", "consulting the OSV oracle (network; --offline stays in the crypt)")
    try:
        result = plague_core.plague(resolved.repo, offline=offline, invoked=_invocation())
    except Exception as exc:  # OsvError, but net/ is only imported when online
        raise _die(str(exc), "try --offline, or check the connection") from exc
    if result.checked:
        _say(
            "necro",
            f"{len(result.afflictions)} afflictions across "
            f"{len(result.dependencies)} dependencies"
            + (f" ({result.unpinned} unpinned, not queried)" if result.unpinned else ""),
        )
    else:
        _say("ash", f"offline: parsed {len(result.dependencies)} dependencies, oracle unconsulted")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_plague(result), out)
    elif fmt == "html":
        _emit(htmlfmt.render("plague", result), out)
    else:
        _emit(markdown.render_plague(result), out)
    if fail_on == "any" and result.afflictions:
        _say("blood", f"the plague is upon us. exit {CURSED}.")
        raise typer.Exit(code=CURSED)


# --------------------------------------------------------------------------
# necropolis (multi-repo fan-out)
# --------------------------------------------------------------------------


@app.command(
    "necropolis",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def necropolis_cmd(
    ctx: typer.Context,
    command: str | None = typer.Argument(
        None, help="The reaper command to fan out; extra args pass through."
    ),
    manifest: Path = typer.Option(
        Path(fleet_core.MANIFEST), "--manifest", "-m", help="The necropolis.toml manifest."
    ),
    org: str | None = typer.Option(
        None, "--org", help="Fan out over a GitHub org instead (needs the gh CLI)."
    ),
    org_limit: int = typer.Option(200, "--org-limit", help="Max repos to list with --org."),
    tag: str | None = typer.Option(None, "--tag", help="Only graves carrying this tag."),
    out_dir: Path = typer.Option(
        Path("necropolis"), "--out-dir", help="Directory for per-grave artifacts + INDEX.md."
    ),
    fmt: str = typer.Option("md", "--format", "-f", help="Index format: md or json."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Fan any reaper command across every grave in the manifest."""
    if schema:
        _print_schema("necropolis")
        return
    if command is None:
        raise _die("no command given", "e.g. `reaper necropolis harvest --tag docs`")
    _validate_format(fmt)
    if command in ("necropolis", "cast", "summon", "veil", "reanimate", "grimoire", "banish"):
        raise _die(
            f"{command!r} cannot be fanned out",
            "necropolis runs source-taking commands like harvest, conjure, or census",
        )
    _banner()
    try:
        graves = (
            fleet_core.org_graves(org, limit=org_limit)
            if org
            else (fleet_core.load_manifest(manifest))
        )
    except fleet_core.FleetError as exc:
        raise _die(str(exc)) from exc

    cli_command = typer.main.get_command(app)

    def _runner(argv: list[str]) -> int:
        full = (["--plain"] if state.plain else []) + argv
        try:
            cli_command.main(args=full, prog_name="reaper", standalone_mode=False)
        except SystemExit as exc:  # usage errors still raise SystemExit(2)
            return exc.code if isinstance(exc.code, int) else 1
        except typer.Exit as exc:
            return exc.exit_code
        except Exception:
            return 1
        return 0

    passthrough = list(ctx.args)
    result = fleet_core.necropolis(command, passthrough, graves, out_dir, _runner, tag=tag)
    for outcome in result.graves:
        if outcome.ok:
            _say("necro", f"reaped {outcome.name}")
        else:
            _say("blood", f"{outcome.name}: {outcome.error}")
    _say(
        "bone",
        f"index written to {result.index} "
        f"({sum(1 for o in result.graves if o.ok)}/{len(result.graves)} reaped)",
    )
    if fmt == "json":
        _emit(jsonfmt.render(result), None)
    code = fleet_core.fleet_exit_code(result)
    if code:
        raise typer.Exit(code=code)


# --------------------------------------------------------------------------
# pulse (doctor)
# --------------------------------------------------------------------------


@app.command("pulse")
def pulse_cmd(
    fmt: str = typer.Option("md", "--format", "-f", help="md or json."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Signs-of-life check: git, extras, cache health."""
    if schema:
        _print_schema("pulse")
        return
    _validate_format(fmt)
    result = pulse_core.pulse()
    if fmt == "json":
        _emit(jsonfmt.render(result), None)
    else:
        table = Table(title="signs of life", title_style="eldritch", border_style="grave")
        table.add_column("check", style="bone")
        table.add_column("", justify="center")
        table.add_column("detail", style="ash")
        for check in result.checks:
            mark = "[necro]ok[/necro]" if check.ok else "[blood]DEAD[/blood]"
            # escape: details like "[git] extra" are text, not Rich markup
            table.add_row(check.name, mark, escape(check.detail))
        state.console.print(table)
    if not result.ok:
        _say("blood", "the patient is unwell; fix the DEAD rows above")
        raise typer.Exit(code=1)
    _say("necro", "there is a pulse. faint, but there.")


# --------------------------------------------------------------------------
# banish (purge)
# --------------------------------------------------------------------------


@app.command("banish")
def banish_cmd(
    older_than: str | None = typer.Option(
        None, "--older-than", help="Only clear graves older than this (e.g. 7d, 12h)."
    ),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Clear the catacombs (the clone cache)."""
    if schema:
        _print_schema("banish")
        return
    _banner()
    try:
        age = cache.parse_age(older_than) if older_than else None
    except ValueError as exc:
        raise _die(str(exc)) from exc
    result = cache.banish(older_than_seconds=age)
    for entry in result.removed:
        _say("ember", f"banished {entry.url or entry.path}", level=1)
    _say(
        "necro",
        f"banished {len(result.removed)} graves, kept {len(result.kept)}, "
        f"reclaimed {fsutil.human_size(result.reclaimed_bytes)}",
    )


# --------------------------------------------------------------------------
# summon (the TUI)
# --------------------------------------------------------------------------


@app.command("summon")
def summon_cmd(
    source: str = typer.Argument(".", help="Prefill the source (path or repo URL)."),
) -> None:
    """Launch the Textual TUI."""
    try:
        from git_reaper.tui import run_tui
    except ImportError as exc:
        raise _die(
            "the TUI needs the extra; install `git-reaper[tui]`",
            "`reaper pulse` shows which extras are present",
        ) from exc
    run_tui(source)


# --------------------------------------------------------------------------
# easter egg
# --------------------------------------------------------------------------


@app.command("boo", hidden=True)
def boo_cmd() -> None:
    """A random piece from the gallery."""
    if not state.plain:
        state.console.print(f"[eldritch]{art.boo()}[/eldritch]", highlight=False)


def attach_rituals() -> None:
    """Mount third-party rituals (the `git_reaper.rituals` entry point group).

    Called by the console-script and `python -m` entrances, not at import
    time, so tests and library users never pay for (or observe) plugins.
    """
    from git_reaper import plugins

    for fate in plugins.attach(app):
        if not fate.ok:
            sys.stderr.write(f"ritual {fate.name!r} failed to load: {fate.error}\n")


def run() -> None:  # pragma: no cover - console-script shim
    attach_rituals()
    app()
