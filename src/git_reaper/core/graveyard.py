"""The graveyard and its resurrections.

`graveyard` lists every file that lived and died; `resurrect` reads a dead
file's last living bytes (from the parent of the commit that removed it) and
brings it back. Restores refuse absolute and traversal paths, same as
reanimate -- the zip-slip lesson does not care that the source is git.
"""

from __future__ import annotations

from pathlib import Path

from git_reaper.core.history import _require_repo
from git_reaper.core.provenance import make_provenance
from git_reaper.core.unpack import _unsafe
from git_reaper.gitio import DeadFileRecord, GitBackend, GitError, default_backend
from git_reaper.models import DeadFile, GraveyardResult, RepoRef, ResurrectResult
from git_reaper.schemas import artifact_schema


class ResurrectError(ValueError):
    """A file could not be raised: absent, or an unsafe restore path."""


def graveyard(
    repo: RepoRef,
    backend: GitBackend | None = None,
    invoked: str = "reaper graveyard",
    generated: str | None = None,
) -> GraveyardResult:
    """List files a commit removed that are not back in the working tree."""
    backend = backend or default_backend()
    root = _require_repo(repo, backend)
    dead = [
        DeadFile(path=rec.path, last_sha=rec.sha, died=rec.date, author=rec.author)
        for rec in backend.deleted_files(root)
        if not (root / rec.path).exists()
    ]
    result = GraveyardResult(
        provenance=make_provenance(artifact_schema("graveyard"), repo, invoked, generated),
        dead=dead,
    )
    result.provenance.files = len(dead)
    return result


def _find_death(backend: GitBackend, root: Path, rel_path: str) -> DeadFileRecord | None:
    for rec in backend.deleted_files(root):
        if rec.path == rel_path:
            return rec
    return None


def resurrect(
    repo: RepoRef,
    rel_path: str,
    out: Path,
    force: bool = False,
    backend: GitBackend | None = None,
) -> ResurrectResult:
    """Restore a dead file. `out` is a directory (the file keeps its path) or,
    if it looks like a file target, the exact destination."""
    backend = backend or default_backend()
    root = _require_repo(repo, backend)

    reason = _unsafe(rel_path)
    if reason:
        raise ResurrectError(f"refusing to resurrect {rel_path!r}: {reason}")

    death = _find_death(backend, root, rel_path)
    if death is None:
        raise ResurrectError(f"{rel_path!r} is not in the graveyard (never deleted, or wrong path)")

    # The fatal commit removed the file; its content still lives in the parent.
    try:
        content = backend.show_file(root, f"{death.sha}~1", rel_path)
    except GitError as exc:
        raise ResurrectError(str(exc)) from exc
    if content is None:
        raise ResurrectError(f"could not read {rel_path!r} at {death.sha[:7]}~1")

    target = out / rel_path if out.is_dir() or not out.suffix else out
    if target.exists() and not force:
        raise ResurrectError(f"{target} already exists; use --force to overwrite")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return ResurrectResult(
        path=rel_path, sha=f"{death.sha}~1", out=str(target), size_bytes=len(content)
    )
