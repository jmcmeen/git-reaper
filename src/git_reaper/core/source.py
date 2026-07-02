"""Resolve a source argument: local path, or remote URL via the catacombs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from git_reaper import cache, fsutil
from git_reaper.gitio import GitBackend, GitError, default_backend
from git_reaper.models import RepoRef

_REMOTE_HINTS = ("http://", "https://", "git://", "ssh://", "git@", "file://")


def looks_remote(source: str) -> bool:
    return source.startswith(_REMOTE_HINTS)


@dataclass
class ResolvedSource:
    repo: RepoRef
    cached: bool = False  # True when a catacombs plot was reused


def resolve_source(
    source: str,
    ref: str | None = None,
    depth: int | None = 1,
    backend: GitBackend | None = None,
) -> ResolvedSource:
    """Turn a path or URL into a readable local directory.

    Local paths are used in place. Remote URLs are cloned (shallow by
    default) into the catacombs and reused on repeat visits.
    """
    backend = backend or default_backend()

    if not looks_remote(source):
        path = Path(source).expanduser().resolve()
        if not path.is_dir():
            raise FileNotFoundError(
                f"no such directory: {path} (give a local folder or a repo URL)"
            )
        sha = backend.head_sha(path) if backend.is_repo(path) else None
        branch = backend.current_branch(path) if sha else None
        return ResolvedSource(
            repo=RepoRef(source=source, kind="local", path=str(path), ref=ref or branch, sha=sha)
        )

    plot = cache.grave_path(source)
    cached = (plot / ".git").is_dir()
    if cached:
        try:
            backend.fetch(plot, ref=ref, depth=depth)
            if ref:
                backend.checkout(plot, ref)
        except GitError:
            # A stale grave is better than no grave; reuse what is interred.
            pass
    else:
        if plot.exists():
            fsutil.force_rmtree(plot)
        backend.clone(source, plot, depth=depth, ref=ref)
    cache.mark_grave(plot, source)
    sha = backend.head_sha(plot)
    branch = ref or backend.current_branch(plot)
    return ResolvedSource(
        repo=RepoRef(source=source, kind="remote", path=str(plot), ref=branch, sha=sha),
        cached=cached,
    )
