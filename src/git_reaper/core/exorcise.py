"""Exorcise: generate a *safe* purge plan for what should leave history.

Composes the dead-blob signal from `bloat` and the secret findings from
`exhume` into a plan of git-filter-repo (and BFG) commands. It plans and
prints; it NEVER rewrites history on its own -- the reaper hands you the
stake, it does not swing it.
"""

from __future__ import annotations

from git_reaper.core import dedupe
from git_reaper.core import rules as rules_core
from git_reaper.core.history import _require_repo
from git_reaper.core.provenance import make_provenance
from git_reaper.fsutil import human_size
from git_reaper.gitio import GitBackend, default_backend
from git_reaper.models import ExorciseResult, ExorciseTarget, RepoRef
from git_reaper.schemas import artifact_schema

DEFAULT_MIN_SIZE = 1024 * 1024  # dead blobs below 1 MB are not worth a rewrite

WARNINGS = [
    "these commands REWRITE HISTORY: every sha after the oldest touched commit changes",
    "rotate any leaked secret first; purging the history does not un-leak it",
    "work on a fresh clone and keep a backup; a botched rewrite has no undo",
    "coordinate the force-push: every fork and clone must rebase or re-clone",
]


def _quote(path: str) -> str:
    """Quote a path for a *displayed* command (portable double quotes)."""
    return f'"{path}"' if " " in path else path


def _filter_repo_size(size: int) -> str:
    """git-filter-repo's size syntax: whole K/M/G when clean, else bytes."""
    for unit, label in ((1024**3, "G"), (1024**2, "M"), (1024, "K")):
        if size % unit == 0:
            return f"{size // unit}{label}"
    return str(size)


def exorcise(
    repo: RepoRef,
    rules: list[rules_core.Rule] | None = None,
    min_size: int = DEFAULT_MIN_SIZE,
    secrets: bool = True,
    backend: GitBackend | None = None,
    invoked: str = "reaper exorcise",
    generated: str | None = None,
) -> ExorciseResult:
    """Plan the purge: what to expel, and the commands that would do it."""
    backend = backend or default_backend()
    _require_repo(repo, backend)

    targets: list[ExorciseTarget] = []
    heavy = dedupe.bloat(repo, limit=10_000, backend=backend, invoked=invoked)
    for entry in heavy.walls:
        if entry.size_bytes >= min_size:
            targets.append(
                ExorciseTarget(
                    path=entry.path,
                    reason=f"dead blob ({human_size(entry.size_bytes)})",
                    sha=entry.sha,
                    size_bytes=entry.size_bytes,
                )
            )

    if secrets:
        loaded = rules if rules is not None else rules_core.load_rules({})
        found = rules_core.exhume(repo, rules=loaded, backend=backend, invoked=invoked)
        seen = {t.path for t in targets}
        for finding in found.findings:
            if finding.path not in seen:
                seen.add(finding.path)
                targets.append(
                    ExorciseTarget(
                        path=finding.path,
                        reason=f"secret: {finding.rule}",
                        sha=finding.sha,
                    )
                )

    targets.sort(key=lambda t: (-t.size_bytes, t.path))
    result = ExorciseResult(
        provenance=make_provenance(artifact_schema("exorcise"), repo, invoked, generated),
        targets=targets,
        warnings=list(WARNINGS) if targets else [],
    )
    if targets:
        result.commands = _commands(targets, min_size)
    result.provenance.files = len(targets)
    return result


def _commands(targets: list[ExorciseTarget], min_size: int) -> list[str]:
    """git-filter-repo first (the maintained tool), BFG as the alternative."""
    paths = sorted({t.path for t in targets})
    commands = ["git filter-repo --invert-paths " + " ".join(f"--path {_quote(p)}" for p in paths)]
    if any(t.size_bytes >= min_size for t in targets):
        commands.append(f"git filter-repo --strip-blobs-bigger-than {_filter_repo_size(min_size)}")
    names = sorted({t.path.rsplit("/", 1)[-1] for t in targets})
    commands.append("bfg " + " ".join(f"--delete-files {_quote(n)}" for n in names))
    return commands
