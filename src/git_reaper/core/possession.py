"""Possession: the ownership and knowledge map.

The dominant author per file and per top-level directory, measured from one
`git log` pass (commit counts, the same currency the rest of the suite
trades in). A file is *possessed* when one soul holds at least the threshold
share of its commits -- the single points of failure to find before they
leave.
"""

from __future__ import annotations

from collections import Counter

from git_reaper.core.history import _require_repo
from git_reaper.core.provenance import make_provenance
from git_reaper.gitio import GitBackend, default_backend
from git_reaper.models import DirOwnership, FileOwnership, PossessionResult, RepoRef
from git_reaper.schemas import artifact_schema

DEFAULT_THRESHOLD = 0.75


def possession(
    repo: RepoRef,
    threshold: float = DEFAULT_THRESHOLD,
    limit: int | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper possession",
    generated: str | None = None,
) -> PossessionResult:
    """Who holds each surviving file, and where one soul holds it all."""
    backend = backend or default_backend()
    root = _require_repo(repo, backend)
    commits = backend.log(root, ref=repo.ref)

    by_file: dict[str, Counter[str]] = {}
    for commit in commits:
        for change in commit.files:
            by_file.setdefault(change.path, Counter())[commit.author_name] += 1

    files: list[FileOwnership] = []
    dir_tallies: dict[str, Counter[str]] = {}
    dir_files: Counter[str] = Counter()
    for path, tally in by_file.items():
        if not (root / path).is_file():
            continue  # ownership of the dead is graveyard business
        # ties break alphabetically so the owner is deterministic
        owner, owner_commits = min(tally.items(), key=lambda kv: (-kv[1], kv[0]))
        total = sum(tally.values())
        share = round(owner_commits / total, 3)
        files.append(
            FileOwnership(
                path=path,
                owner=owner,
                owner_commits=owner_commits,
                commits=total,
                share=share,
                possessed=share >= threshold,
            )
        )
        top = path.split("/")[0] if "/" in path else "."
        dir_tallies.setdefault(top, Counter()).update(tally)
        dir_files[top] += 1

    files.sort(key=lambda f: (-f.commits, f.path))
    possessed_count = sum(1 for f in files if f.possessed)
    if limit is not None:
        files = files[:limit]

    dirs: list[DirOwnership] = []
    for top in sorted(dir_tallies):
        tally = dir_tallies[top]
        owner, owner_commits = min(tally.items(), key=lambda kv: (-kv[1], kv[0]))
        total = sum(tally.values())
        dirs.append(
            DirOwnership(
                path=top,
                owner=owner,
                owner_commits=owner_commits,
                commits=total,
                share=round(owner_commits / total, 3),
                files=dir_files[top],
            )
        )

    result = PossessionResult(
        provenance=make_provenance(artifact_schema("possession"), repo, invoked, generated),
        threshold=threshold,
        files=files,
        dirs=dirs,
        possessed_count=possessed_count,
    )
    result.provenance.files = len(files)
    return result
