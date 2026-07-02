"""The CLI face of the reaper: a thin Typer adapter over git_reaper.core.

Rules of the house:
- Artifacts go to --out or stdout. Narration goes to stderr, always.
- Every themed message still carries the plain cause and a next step.
- Exit codes: 0 rest in peace, 1 the ritual failed, 2 bad incantation.
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
from git_reaper.core import graveyard as graveyard_core
from git_reaper.core import harvest as harvest_core
from git_reaper.core import history as history_core
from git_reaper.core import hygiene as hygiene_core
from git_reaper.core import pack as pack_core
from git_reaper.core import pulse as pulse_core
from git_reaper.core import scan as scan_core
from git_reaper.core import tree as tree_core
from git_reaper.core import unpack as unpack_core
from git_reaper.core.source import ResolvedSource, resolve_source
from git_reaper.formatters import csvfmt, jsonfmt, markdown
from git_reaper.gitio import GitError
from git_reaper.theme import make_console, theme_enabled

app = typer.Typer(
    name="reaper",
    help="A spooky utility for data mining git repositories.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


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
        state.console.print(f"[eldritch]{art.MINI_SKULL}[/eldritch]", highlight=False)


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
# tree (map)
# --------------------------------------------------------------------------


@app.command("tree")
def tree_cmd(
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
    """Emit a hierarchical file listing."""
    if schema:
        _print_schema("tree")
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
    resolved = _resolve(source, ref=ref, depth=depth)
    try:
        result = pack_core.conjure(
            resolved.repo,
            excludes=exclude,
            max_file_size=file_cap,
            max_total_size=total_cap,
            with_sha256=sha256,
            split_tokens=split_tokens,
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

    for number, text in pack_core.iter_parts(result):
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
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, or csv."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha (remote sources)."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """File-type census: counts, sizes, lines, languages, token estimate."""
    if schema:
        _print_schema("census")
        return
    _validate_format(fmt, ("md", "json", "csv"))
    _banner()
    resolved = _resolve(source, ref=ref)
    result = census_core.census(resolved.repo, excludes=exclude, invoked=_invocation())
    _say("necro", f"counted {result.total_files} souls across {len(result.extensions)} kinds")
    if fmt == "json":
        _emit(jsonfmt.render(result), out)
    elif fmt == "csv":
        _emit(csvfmt.render_census(result), out)
    else:
        _emit(markdown.render_census(result), out)


@app.command("unfinished")
def unfinished_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    exclude: list[str] = typer.Option([], "--exclude", "-x", help="Glob(s) to skip."),
    age: bool = typer.Option(False, "--age", help="Add how long each marker has haunted."),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, or csv."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha (remote sources)."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Scan for TODO / FIXME / HACK / XXX markers."""
    if schema:
        _print_schema("unfinished")
        return
    _validate_format(fmt, ("md", "json", "csv"))
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
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, or csv."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Extract commit history to markdown, JSON, or CSV."""
    if schema:
        _print_schema("chronicle")
        return
    _validate_format(fmt, ("md", "json", "csv"))
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
    else:
        _emit(markdown.render_chronicle(result), out)


@app.command("souls")
def souls_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    heatmap: bool = typer.Option(False, "--heatmap", help="Add the activity heatmap."),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, or csv."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Contributor stats, bus factor, and the witching hour."""
    if schema:
        _print_schema("souls")
        return
    _validate_format(fmt, ("md", "json", "csv"))
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
    else:
        _emit(markdown.render_souls(result), out)


@app.command("haunt")
def haunt_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    limit: int | None = typer.Option(None, "--limit", "-n", help="Only the top N hotspots."),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, or csv."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Code churn and hotspots: the classic bug-risk proxy."""
    if schema:
        _print_schema("haunt")
        return
    _validate_format(fmt, ("md", "json", "csv"))
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
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, or csv."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """List every file that ever lived and died in the repo."""
    if schema:
        _print_schema("graveyard")
        return
    _validate_format(fmt, ("md", "json", "csv"))
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
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, or csv."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Branch hygiene: activity, merged-but-undeleted, gone remotes."""
    if schema:
        _print_schema("ghosts")
        return
    _validate_format(fmt, ("md", "json", "csv"))
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
    else:
        _emit(markdown.render_ghosts(result), out)


@app.command("rot")
def rot_cmd(
    source: str = typer.Argument(".", help="Local path or repo URL."),
    limit: int | None = typer.Option(None, "--limit", "-n", help="Only the top N stalest."),
    exclude: list[str] = typer.Option([], "--exclude", "-x", help="Glob(s) to skip."),
    fmt: str = typer.Option("md", "--format", "-f", help="md, json, or csv."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default stdout)."),
    ref: str | None = typer.Option(None, "--ref", help="Branch, tag, or sha."),
    schema: bool = typer.Option(False, "--schema", help="Print the JSON schema and exit."),
) -> None:
    """Staleness report: files untouched the longest."""
    if schema:
        _print_schema("rot")
        return
    _validate_format(fmt, ("md", "json", "csv"))
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
# easter egg
# --------------------------------------------------------------------------


@app.command("boo", hidden=True)
def boo_cmd() -> None:
    """A random piece from the gallery."""
    if not state.plain:
        state.console.print(f"[eldritch]{art.boo()}[/eldritch]", highlight=False)


def run() -> None:  # pragma: no cover - console-script shim
    app()
