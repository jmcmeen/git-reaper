"""Doppelgangers and bloat: the same bytes twice, and the heavy bytes.

`doppelgangers` finds working-tree files that are byte-for-byte identical
(content sha256), reporting clusters and the space a cleanup would reclaim.

`bloat` ranks the largest working-tree files and, in a repo, the blobs that
were deleted from the tree but still weigh down `.git` - the body is still
in the walls.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from git_reaper.core.provenance import make_provenance
from git_reaper.gitio import GitBackend, default_backend
from git_reaper.ignore import IgnoreMatcher, walk_files
from git_reaper.models import (
    BloatEntry,
    BloatResult,
    CloneCluster,
    DoppelgangersResult,
    RepoRef,
)
from git_reaper.schemas import artifact_schema

_CHUNK = 65536

DEFAULT_LIMIT = 20


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def doppelgangers(
    repo: RepoRef,
    excludes: list[str] | None = None,
    min_size: int = 1,
    invoked: str = "reaper doppelgangers",
    generated: str | None = None,
) -> DoppelgangersResult:
    """Cluster identical files by content hash.

    Size is compared first so only same-sized files get hashed; empty files
    are ignored by default (min_size=1) because a thousand empty __init__.py
    are convention, not waste.
    """
    root = Path(repo.path)
    matcher = IgnoreMatcher(root, extra_excludes=excludes)
    result = DoppelgangersResult(
        provenance=make_provenance(artifact_schema("doppelgangers"), repo, invoked, generated)
    )

    by_size: dict[int, list[Path]] = {}
    for path in walk_files(root, matcher):
        result.files_scanned += 1
        size = path.stat().st_size
        if size >= min_size:
            by_size.setdefault(size, []).append(path)

    for size, paths in sorted(by_size.items()):
        if len(paths) < 2:
            continue
        by_hash: dict[str, list[str]] = {}
        for path in paths:
            rel = path.relative_to(root).as_posix()
            by_hash.setdefault(_sha256(path), []).append(rel)
        for sha, rels in sorted(by_hash.items()):
            if len(rels) < 2:
                continue
            cluster = CloneCluster(
                sha256=sha,
                size_bytes=size,
                paths=sorted(rels),
                reclaimable_bytes=(len(rels) - 1) * size,
            )
            result.clusters.append(cluster)
            result.reclaimable_bytes += cluster.reclaimable_bytes

    result.clusters.sort(key=lambda c: (-c.reclaimable_bytes, c.paths[0]))
    result.provenance.files = sum(len(c.paths) for c in result.clusters)
    return result


def bloat(
    repo: RepoRef,
    limit: int = DEFAULT_LIMIT,
    excludes: list[str] | None = None,
    invoked: str = "reaper bloat",
    generated: str | None = None,
    backend: GitBackend | None = None,
) -> BloatResult:
    """The largest files in the tree, and dead blobs still haunting .git.

    Works on plain folders too - the walls section is simply empty when
    there is no history to hide bodies in.
    """
    backend = backend or default_backend()
    root = Path(repo.path)
    matcher = IgnoreMatcher(root, extra_excludes=excludes)
    result = BloatResult(
        provenance=make_provenance(artifact_schema("bloat"), repo, invoked, generated)
    )

    tree_entries = []
    for path in walk_files(root, matcher):
        size = path.stat().st_size
        tree_entries.append(BloatEntry(path=path.relative_to(root).as_posix(), size_bytes=size))
        result.tree_bytes += size
    tree_entries.sort(key=lambda e: (-e.size_bytes, e.path))
    result.tree = tree_entries[:limit]

    if backend.is_repo(root):
        # A blob is "in the walls" when no working-tree file carries its bytes.
        living = {_blob_sha(path) for path in walk_files(root, matcher)}
        walls = []
        for blob in backend.blobs(root):
            if blob.sha in living:
                continue
            walls.append(
                BloatEntry(path=blob.path, size_bytes=blob.size_bytes, sha=blob.sha, in_tree=False)
            )
            result.walls_bytes += blob.size_bytes
        walls.sort(key=lambda e: (-e.size_bytes, e.path, e.sha))
        result.walls = walls[:limit]

    result.provenance.files = len(result.tree) + len(result.walls)
    return result


def _blob_sha(path: Path) -> str:
    """Git's blob id for a file's current bytes: sha1 of 'blob <len>\\0<data>'."""
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()
