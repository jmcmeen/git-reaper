"""Lineage: trace a line's true origin across history (git's pickaxe).

`-S` finds commits that changed how often the needle appears; `--regex`
switches to `-G` (any diff hunk matching the pattern). The oldest hit is the
origin: who first summoned this line into the crypt.
"""

from __future__ import annotations

from git_reaper.core.history import _commit_entry, _require_repo
from git_reaper.core.provenance import make_provenance
from git_reaper.gitio import GitBackend, default_backend
from git_reaper.models import LineageResult, RepoRef
from git_reaper.schemas import artifact_schema


def lineage(
    repo: RepoRef,
    needle: str,
    regex: bool = False,
    rel_path: str | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper lineage",
    generated: str | None = None,
) -> LineageResult:
    """Every commit that added or removed the needle, newest first."""
    backend = backend or default_backend()
    root = _require_repo(repo, backend)
    commits = backend.pickaxe(root, needle, regex=regex, rel_path=rel_path)
    entries = [_commit_entry(c) for c in commits]
    result = LineageResult(
        provenance=make_provenance(artifact_schema("lineage"), repo, invoked, generated),
        needle=needle,
        regex=regex,
        path=rel_path or "",
        commits=entries,
        origin=entries[-1] if entries else None,
    )
    result.provenance.files = len(entries)
    return result
