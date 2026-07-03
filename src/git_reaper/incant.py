"""The incantation console's brain: suggest, parse, validate. Textual-free.

The console chamber types here, the library thinks. A line like
`/omens . --lens churn --limit 10` becomes a validated ritual + options the
worker can run, plus the normalized argv that makes it reproducible outside
the TUI. CLI semantics on purpose: toggles are store-true flags (absent means
off), so the incantation shown is exactly the incantation `reaper` would run.

Meta commands (`/help`, `/recipes`, ...) are the console's own furniture and
never leave it; everything else has a headless twin.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from typing import Any

from git_reaper.tui_ops import (
    OPERATIONS,
    OPERATIONS_BY_KEY,
    ChoiceOpt,
    NumberOpt,
    Operation,
    ToggleOpt,
    incantation_argv,
)

#: The console's own commands; they act on the chamber, not on a repo.
META_COMMANDS: dict[str, str] = {
    "/help": "how the console works, and every ritual's flags",
    "/recipes": "list the grimoire's recipes; run one by name",
    "/theme": "switch theme: /theme <name> (no name lists them)",
    "/clear": "clear the preview",
    "/save": "inter the last artifact: /save <path>",
}


@dataclass(frozen=True)
class Suggestion:
    """One row in the console's fuzzy menu."""

    text: str  # what completes into the input, e.g. "/omens"
    detail: str  # one-line help beside it


@dataclass
class Incantation:
    """A parsed console line, ready to run or explain."""

    kind: str  # "ritual" | "meta" | "empty" | "error"
    op: Operation | None = None
    source: str = "."
    opts: dict[str, Any] = field(default_factory=dict)
    meta: str = ""  # the meta command, e.g. "/save"
    meta_arg: str = ""  # everything after it, e.g. the path
    error: str = ""
    argv: tuple[str, ...] = ()  # the reproducible twin: ("reaper", key, source, *flags)


def _tokens(line: str) -> list[str]:
    """Split a console line; on Windows keep backslashes in paths intact."""
    if os.name == "nt":
        return [token.strip('"') for token in shlex.split(line, posix=False)]
    return shlex.split(line)


def suggest(text: str) -> list[Suggestion]:
    """Fuzzy-match the first word against rituals and meta commands.

    Ranked: prefix matches, then substring, then subsequence -- typing `/om`
    puts omens first, `/hnt` still finds haunt. Empty input lists everything.
    """
    head = text.strip().split(" ")[0].lstrip("/").lower()
    candidates: list[tuple[int, Suggestion]] = []
    for op in OPERATIONS:
        rank = _match_rank(head, op.key)
        if rank is not None:
            candidates.append((rank, Suggestion(f"/{op.key}", op.description)))
    for meta, detail in META_COMMANDS.items():
        rank = _match_rank(head, meta.lstrip("/"))
        if rank is not None:
            candidates.append((rank, Suggestion(meta, detail)))
    candidates.sort(key=lambda pair: (pair[0], pair[1].text))
    return [suggestion for _rank, suggestion in candidates]


def _match_rank(needle: str, name: str) -> int | None:
    if not needle:
        return 2
    if name.startswith(needle):
        return 0
    if needle in name:
        return 1
    it = iter(name)
    if all(ch in it for ch in needle):  # subsequence
        return 2
    return None


def parse(line: str) -> Incantation:
    """Turn a console line into a validated incantation (or a clear error)."""
    try:
        tokens = _tokens(line)
    except ValueError as exc:  # unbalanced quotes
        return Incantation(kind="error", error=f"unreadable incantation: {exc}")
    if not tokens:
        return Incantation(kind="empty")

    head, *rest = tokens
    if head == "reaper":  # pasted a full CLI line; the twin is welcome here
        if not rest:
            return Incantation(kind="error", error="reaper what? try /help")
        head, *rest = rest

    lowered = f"/{head.lstrip('/').lower()}"
    if lowered in META_COMMANDS:
        return Incantation(kind="meta", meta=lowered, meta_arg=" ".join(rest))

    key = head.lstrip("/").lower()
    op = OPERATIONS_BY_KEY.get(key)
    if op is None:
        near = suggest(key)
        hint = f"; did you mean {near[0].text}?" if near else "; /help lists the rituals"
        return Incantation(kind="error", error=f"unknown ritual {key!r}{hint}")

    # CLI semantics: toggles are off unless the flag appears.
    opts: dict[str, Any] = op.defaults()
    for spec in op.options:
        if isinstance(spec, ToggleOpt):
            opts[spec.name] = False
    specs = {("--" + spec.name.replace("_", "-")): spec for spec in op.options}

    source = "."
    seen_source = False
    i = 0
    while i < len(rest):
        token = rest[i]
        if not token.startswith("--"):
            # bare tokens fill the CLI grammar in order: the positional
            # (autopsy PATH, lineage NEEDLE, veil FILE) first, then the source.
            if op.positional and not str(opts.get(op.positional) or "").strip():
                opts[op.positional] = token
            elif op.source_arg != "none" and not seen_source:
                source, seen_source = token, True
            else:
                return Incantation(
                    kind="error", error=f"{usage(op)} -- {token!r} is one too many"
                )
            i += 1
            continue
        flag = specs.get(token)
        if flag is None:
            flags = " ".join(sorted(specs)) or "(none)"
            return Incantation(kind="error", error=f"{key} takes no {token}; flags: {flags}")
        if isinstance(flag, ToggleOpt):
            opts[flag.name] = True
            i += 1
            continue
        if i + 1 >= len(rest):
            return Incantation(kind="error", error=f"{token} needs a value")
        value = rest[i + 1]
        if isinstance(flag, NumberOpt):
            if not value.lstrip("-").isdigit():
                return Incantation(kind="error", error=f"{token} needs a whole number")
            opts[flag.name] = int(value)
        elif isinstance(flag, ChoiceOpt):
            if value not in flag.choices:
                choices = ", ".join(flag.choices)
                return Incantation(kind="error", error=f"{token} must be one of: {choices}")
            opts[flag.name] = value
        else:
            opts[flag.name] = value
        i += 2

    if op.positional and not str(opts.get(op.positional) or "").strip():
        return Incantation(
            kind="error", error=f"{key} needs a {op.positional}: {usage(op)}"
        )

    argv = ("reaper", key, *incantation_argv(op, source, opts))
    return Incantation(kind="ritual", op=op, source=source, opts=opts, argv=argv)


def usage(op: Operation) -> str:
    """The ritual's bare-argument shape, e.g. `autopsy PATH [SOURCE]`."""
    head = f"{op.key} {op.positional.upper()}" if op.positional else op.key
    return head if op.source_arg == "none" else f"{head} [SOURCE]"


def flag_help(op: Operation) -> str:
    """One line of live help for a ritual: its flags and their shapes."""
    parts: list[str] = []
    for spec in op.options:
        if spec.name == op.positional:
            continue  # already in the usage head
        flag = "--" + spec.name.replace("_", "-")
        if isinstance(spec, ToggleOpt):
            parts.append(flag)
        elif isinstance(spec, ChoiceOpt):
            parts.append(f"{flag} {{{'|'.join(spec.choices)}}}")
        elif isinstance(spec, NumberOpt):
            parts.append(f"{flag} N")
        else:
            parts.append(f"{flag} TEXT")
    flags = "  ".join(parts) if parts else "no flags"
    return f"{usage(op)} -- {op.description}. {flags}"


def render_help() -> str:
    """The `/help` artifact: meta commands, then every ritual's flag line."""
    lines = ["# the incantation console", ""]
    lines.append("Type `/` to summon the menu; Enter runs the assembled incantation.")
    lines.append("Everything you run here is a real `reaper` invocation -- the argv")
    lines.append("shown beside the result reproduces it headless.")
    lines += ["", "## meta", ""]
    for meta, detail in META_COMMANDS.items():
        lines.append(f"- `{meta}` -- {detail}")
    lines += ["", "## rituals", ""]
    for op in OPERATIONS:
        lines.append(f"- `{flag_help(op)}`")
    return "\n".join(lines) + "\n"
