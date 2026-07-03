"""Effigy: the data behind the repo's SVG portrait.

One pass of history (souls, heatmap, vitals) plus a walk of the tree
(top-level directory weights for the treemap strip). The drawing itself
lives in formatters/svgfmt.py; this module only measures.
"""

from __future__ import annotations

from pathlib import Path

from git_reaper.core.history import souls
from git_reaper.core.provenance import make_provenance
from git_reaper.gitio import GitBackend, GitError, default_backend
from git_reaper.ignore import IgnoreMatcher, walk_files
from git_reaper.models import EffigyResult, EffigySlice, RepoRef
from git_reaper.schemas import artifact_schema

DEFAULT_TOP_SOULS = 8
DEFAULT_TOP_SLICES = 10


def effigy(
    repo: RepoRef,
    top_souls: int = DEFAULT_TOP_SOULS,
    top_slices: int = DEFAULT_TOP_SLICES,
    excludes: list[str] | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper effigy",
    generated: str | None = None,
) -> EffigyResult:
    """Measure everything the poster draws."""
    backend = backend or default_backend()
    ledger = souls(repo, heatmap=True, backend=backend, invoked=invoked, generated=generated)
    if not ledger.souls:
        raise GitError(f"no commits to portray in {repo.source}")
    commits = backend.log(Path(repo.path), ref=repo.ref)
    born, last = commits[-1], commits[0]

    root = Path(repo.path)
    matcher = IgnoreMatcher(root, extra_excludes=excludes)
    weights: dict[str, EffigySlice] = {}
    for path in walk_files(root, matcher):
        rel = path.relative_to(root).as_posix()
        top = rel.split("/")[0] if "/" in rel else "."
        piece = weights.get(top)
        if piece is None:
            piece = weights[top] = EffigySlice(name=top)
        piece.size_bytes += path.stat().st_size
        piece.files += 1
    slices = sorted(weights.values(), key=lambda s: (-s.size_bytes, s.name))[:top_slices]

    result = EffigyResult(
        provenance=make_provenance(artifact_schema("effigy"), repo, invoked, generated),
        name=Path(repo.path).name or repo.source,
        born=born.author_date,
        last=last.author_date,
        commits=ledger.total_commits,
        bus_factor=ledger.bus_factor,
        souls=ledger.souls[:top_souls],
        heatmap=ledger.heatmap or [[0] * 24 for _ in range(7)],
        witching_hour=ledger.witching_hour,
        slices=slices,
    )
    result.provenance.files = len(result.souls) + len(slices)
    return result
