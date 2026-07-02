"""Branch and file hygiene: ghosts (branches) and rot (staleness).

Both lean on the injectable `now` for age math, the one wall-clock value that
would otherwise make output non-deterministic. rot derives last-touch dates
from a single `git log` pass rather than one git call per file.
"""

from __future__ import annotations

import time

from git_reaper.core.history import _age_days, _require_repo
from git_reaper.core.provenance import make_provenance
from git_reaper.gitio import GitBackend, default_backend
from git_reaper.ignore import IgnoreMatcher, walk_files
from git_reaper.models import Branch, GhostsResult, RepoRef, RotResult, StaleFile
from git_reaper.schemas import artifact_schema


def ghosts(
    repo: RepoRef,
    than_days: int | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper ghosts",
    generated: str | None = None,
    now: float | None = None,
) -> GhostsResult:
    """Rank branches by abandonment; flag merged, gone-upstream, and stale."""
    backend = backend or default_backend()
    root = _require_repo(repo, backend)
    now = time.time() if now is None else now

    branches = []
    for rec in backend.branches(root):
        age = _age_days(rec.last_time, now)
        branches.append(
            Branch(
                name=rec.name,
                last_commit=rec.last_date,
                last_sha="",
                author=rec.author,
                age_days=age,
                merged=rec.merged,
                gone_upstream=rec.gone_upstream,
                stale=than_days is not None and age > than_days,
            )
        )
    branches.sort(key=lambda b: (-b.age_days, b.name))
    result = GhostsResult(
        provenance=make_provenance(artifact_schema("ghosts"), repo, invoked, generated),
        branches=branches,
        threshold_days=than_days,
    )
    result.provenance.files = len(branches)
    return result


def rot(
    repo: RepoRef,
    limit: int | None = None,
    excludes: list[str] | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper rot",
    generated: str | None = None,
    now: float | None = None,
) -> RotResult:
    """Rank surviving files by how long they have gone untouched."""
    backend = backend or default_backend()
    root = _require_repo(repo, backend)
    now = time.time() if now is None else now

    # One pass, newest-first: the first commit that touches a path is its
    # last-touch. Only files still in the working tree can rot.
    last_touch: dict[str, tuple[int, str, str]] = {}
    for commit in backend.log(root, ref=repo.ref):
        for change in commit.files:
            if change.path not in last_touch:
                last_touch[change.path] = (commit.author_time, commit.sha, commit.author_date)

    matcher = IgnoreMatcher(root, extra_excludes=excludes)
    stale: list[StaleFile] = []
    for path in walk_files(root, matcher):
        rel = path.relative_to(root).as_posix()
        touch = last_touch.get(rel)
        if touch is None:
            continue  # tracked-but-never-in-log edge, or untracked; skip
        when, sha, date = touch
        stale.append(
            StaleFile(path=rel, last_commit=date, last_sha=sha, age_days=_age_days(when, now))
        )
    stale.sort(key=lambda s: (-s.age_days, s.path))
    if limit is not None:
        stale = stale[:limit]
    result = RotResult(
        provenance=make_provenance(artifact_schema("rot"), repo, invoked, generated),
        files=stale,
    )
    result.provenance.files = len(stale)
    return result
