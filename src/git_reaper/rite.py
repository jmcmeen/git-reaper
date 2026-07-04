"""Perform a rite: run its steps, in order, against one or more sources.

A rite is stored recipe-shaped -- each step carries a `command` plus CLI
argument tokens -- so running one reuses the CLI's own argument parsing
instead of duplicating it per command. Each step is invoked in-process
through the Typer app with its output format forced to JSON and both stdout
and stderr captured, then folded into a single RiteResult. A step therefore
needs `--format json` support; see ELIGIBLE_STEP_COMMANDS for which ones
qualify.
"""

from __future__ import annotations

import contextlib
import io
import json
from collections.abc import Sequence

import typer

from git_reaper.models import Rite, RiteResult, RiteStep, StepOutcome

#: Token in a step's args replaced with the source currently being processed.
SOURCE_PLACEHOLDER = "{source}"

#: Commands whose output a rite can capture and combine: each supports both
#: --format json and --out, and returns on its own -- unlike banshee/summon/
#: commune, which block waiting on a terminal, or cast, which recipes are
#: already forbidden from recursing into.
ELIGIBLE_STEP_COMMANDS = frozenset(
    {
        "limbs",
        "census",
        "unfinished",
        "chronicle",
        "souls",
        "haunt",
        "autopsy",
        "graveyard",
        "ghosts",
        "rot",
        "tombstone",
        "exhume",
        "omens",
        "doppelgangers",
        "bloat",
        "bones",
        "scry",
        "plague",
        "distill",
        "scavenge",
        "ward",
        "leech",
        "embalm",
        "wake",
        "lineage",
        "possession",
        "revenant",
        "prophecy",
        "exorcise",
        "effigy",
    }
)


class RiteError(ValueError):
    """A rite is misshapen, or asks for a step that cannot combine output."""


def _check_step(step: RiteStep) -> None:
    if step.command not in ELIGIBLE_STEP_COMMANDS:
        allowed = ", ".join(sorted(ELIGIBLE_STEP_COMMANDS))
        raise RiteError(
            f"rite step {step.command!r} cannot combine output (needs --format json); "
            f"use one of: {allowed}"
        )


def _invoke_step(command: str, args: list[str], *, plain: bool) -> tuple[bool, object, str | None]:
    from git_reaper.cli import app  # deferred: cli imports core modules, not this one

    argv = (["--plain"] if plain else []) + [command, *args, "--format", "json"]
    click_command = typer.main.get_command(app)
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            click_command.main(args=argv, prog_name="reaper")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    if code != 0:
        message = err.getvalue().strip() or out.getvalue().strip() or f"exit code {code}"
        return False, None, message
    text = out.getvalue()
    if not text.strip():
        return True, None, None
    try:
        return True, json.loads(text), None
    except json.JSONDecodeError as exc:
        return False, None, f"could not parse output as JSON: {exc}"


def perform_rite(
    rite: Rite, sources: Sequence[str] | None = None, *, plain: bool = False
) -> RiteResult:
    """Run every step of `rite`, in order, against each source in turn.

    A step's args may use the literal token ``{source}`` to receive the
    source currently being processed. Steps that fail are recorded, not
    raised -- the rite keeps going so one bad source or step doesn't blank
    out the rest; check `RiteResult.ok` or each outcome's `ok`/`error`.
    """
    if not rite.steps:
        raise RiteError(f"rite {rite.name!r} has no steps")
    for step in rite.steps:
        _check_step(step)
    resolved_sources = list(sources) if sources else ["."]
    result = RiteResult(rite=rite.name, sources=resolved_sources)
    for source in resolved_sources:
        for step in rite.steps:
            substituted = [arg.replace(SOURCE_PLACEHOLDER, source) for arg in step.args]
            ok, output, error = _invoke_step(step.command, substituted, plain=plain)
            result.outcomes.append(
                StepOutcome(
                    step=step.name or step.command,
                    command=step.command,
                    source=source,
                    ok=ok,
                    output=output,
                    error=error,
                )
            )
    return result
