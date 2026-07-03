"""Revenant: track what will not stay buried.

Two honest, git-only signals (the salvageable slice of the shelved `zombies`
idea): files that were deleted and later re-added, and hotspots that keep
getting "fixed" (the same bug-fix subject signal omens uses).
"""

from __future__ import annotations

from git_reaper.core.history import _require_repo
from git_reaper.core.provenance import make_provenance
from git_reaper.core.risk import BUGFIX
from git_reaper.gitio import GitBackend, default_backend
from git_reaper.models import RepeatOffender, RepoRef, Revenant, RevenantResult
from git_reaper.schemas import artifact_schema

DEFAULT_MIN_FIXES = 3


def revenant(
    repo: RepoRef,
    min_fixes: int = DEFAULT_MIN_FIXES,
    backend: GitBackend | None = None,
    invoked: str = "reaper revenant",
    generated: str | None = None,
) -> RevenantResult:
    """Resurrected files and repeat offenders, most-restless first."""
    backend = backend or default_backend()
    root = _require_repo(repo, backend)

    # Events arrive newest first; replay them oldest first so a rebirth is
    # literally "an add while dead".
    ledger: dict[str, Revenant] = {}
    dead: set[str] = set()
    for event in reversed(backend.file_events(root)):
        entry = ledger.get(event.path)
        if entry is None:
            entry = ledger[event.path] = Revenant(path=event.path)
        if event.status == "D":
            entry.deaths += 1
            entry.last_died = event.date
            entry.alive = False
            dead.add(event.path)
        elif event.status == "A":
            if event.path in dead:
                entry.rebirths += 1
                entry.last_raised = event.date
                dead.discard(event.path)
            entry.alive = True
        else:
            entry.alive = event.path not in dead and entry.alive

    revenants = [r for r in ledger.values() if r.rebirths]
    revenants.sort(key=lambda r: (-r.rebirths, -r.deaths, r.path))

    fixes: dict[str, RepeatOffender] = {}
    for commit in backend.log(root, ref=repo.ref):
        is_fix = bool(BUGFIX.search(commit.subject))
        for change in commit.files:
            offender = fixes.get(change.path)
            if offender is None:
                offender = fixes[change.path] = RepeatOffender(path=change.path)
            offender.commits += 1
            if is_fix:
                offender.bug_commits += 1
                # newest first: the first fix seen is the latest
                if not offender.last_fix:
                    offender.last_fix = commit.author_date
    offenders = [
        o for o in fixes.values() if o.bug_commits >= min_fixes and (root / o.path).is_file()
    ]
    offenders.sort(key=lambda o: (-o.bug_commits, -o.commits, o.path))

    result = RevenantResult(
        provenance=make_provenance(artifact_schema("revenant"), repo, invoked, generated),
        revenants=revenants,
        offenders=offenders,
        min_fixes=min_fixes,
    )
    result.provenance.files = len(revenants) + len(offenders)
    return result
