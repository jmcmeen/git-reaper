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

from git_reaper import __version__, art, cache, fsutil, schemas
from git_reaper.core import harvest as harvest_core
from git_reaper.core import pulse as pulse_core
from git_reaper.core import tree as tree_core
from git_reaper.core.source import resolve_source
from git_reaper.formatters import jsonfmt, markdown
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


def _validate_format(fmt: str) -> None:
    if fmt not in ("md", "json"):
        raise _die(f"unknown format {fmt!r}", "use --format md or --format json")


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

    try:
        resolved = resolve_source(source, ref=ref, depth=depth)
    except (FileNotFoundError, ValueError, GitError) as exc:
        raise _die(str(exc), "check the path or URL; `reaper pulse` checks your setup") from exc
    if resolved.cached:
        _say("necro", f"catacombs hit: {resolved.repo.source} already interred, reusing")

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
    try:
        resolved = resolve_source(source, ref=ref)
    except (FileNotFoundError, ValueError, GitError) as exc:
        raise _die(str(exc), "check the path or URL; `reaper pulse` checks your setup") from exc

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
